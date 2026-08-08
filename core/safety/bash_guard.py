"""Bash command safety: blacklist + whitelist + nested-interpreter checks and
the optional Docker sandbox. Extracted from tools.py (check_bash, docker run)."""
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger('bash_guard')

BASH_BLACKLIST = [
    "rm -rf /", "rm -rf --no-preserve-root", "rm -rf ~", "rm -rf /tmp/",
    "rm -rf c:\\", "rm -rf .", "rm -rf *", "rm -rf",
    "mkfs", "format ", "dd if=", "dd of=", ":(){ :|:& };:", "fork bomb",
    "> /dev/sda", "> /dev/sdb", "| sh", "| bash", "curl ", "wget ", "chmod 777",
    "sudo ", "su ", "passwd", "del /f /s", "rmdir /s", "rd /s", "del /q /s",
    "shutdown", "taskkill /f", "net user",
]
# Whitelist of allowed bare commands (first token). Everything else is rejected
# unless it is a path to an existing file inside WORK_DIR (e.g. .\build.py).
BASH_ALLOWED = {
    "python", "python3", "py", "pythonw", "pip", "pip3", "pipenv", "poetry", "uv", "uvx",
    "npm", "npx", "node", "yarn", "pnpm",
    "git", "gh",
    "cd", "pwd", "echo", "type", "cat", "dir", "ls", "where", "findstr", "find", "cls", "clear",
    "mkdir", "rmdir", "del", "copy", "xcopy", "move", "ren", "cp", "mv", "rm",
    "date", "time", "tasklist", "tree", "fc", "comp",
}
# Destructive commands whose args must not contain ".." (path escape / obfuscation)
BASH_NO_DOTDOT = {"rm", "del", "rd", "rmdir", "move", "mv", "copy", "xcopy", "cp", "ren"}


def _segment_token(segment):
    seg = segment.strip().strip('"').strip("'")
    if not seg:
        return None, ""
    tok = seg.split()[0].strip('"').strip("'")
    base = tok.split("\\")[-1].replace(".exe", "").replace(".bat", "").replace(".cmd", "")
    return tok, base.lower()


def check_bash(cmd, work_dir=None):
    """Block dangerous shell commands. Whitelist for bare commands + blacklist
    patterns + recursive check of nested interpreters (bash -c, cmd /c,
    powershell -c, python -c, node -e)."""
    norm = " ".join(cmd.lower().split())
    stripped = norm.replace('"', "").replace("'", "").replace("`", "").replace("\\", "")
    checks = [norm, stripped]
    # recursive interpreter bodies: bash/sh/cmd/powershell AND python/node inline scripts
    for m in re.finditer(r"(?:bash|sh|cmd|powershell|pwsh)\s+(?:-c|-command)\s+[\"']?([^\"']+)", norm):
        checks.append(" ".join(m.group(1).split()))
    for m in re.finditer(r"(?:python|py|node)\s+(?:-c|-e|-m)\s+[\"']?([^\"']+)", norm):
        checks.append(" ".join(m.group(1).split()))
    for c in checks:
        for dangerous in BASH_BLACKLIST:
            if dangerous in c:
                return f"Blocked: command matching blacklist pattern '{dangerous}' is not allowed"
    # whitelist: every pipeline/; /&& segment must start with an allowed command
    for segment in re.split(r"[\|;&]|(?:^| )(?:and|or) ", norm):
        tok, base = _segment_token(segment)
        if not tok:
            continue
        if base in BASH_ALLOWED:
            continue
        # allow project-local scripts: .\x.py, ./x.py, or relative paths that exist in WORK_DIR
        p = Path(tok.replace("/", os.sep))
        if not os.path.isabs(str(p)) and not tok.startswith(".."):
            if work_dir is not None:
                pp = (Path(work_dir) / p).resolve()
                if Path(work_dir).resolve() in pp.parents and pp.exists():
                    continue
        return f"Blocked: '{tok}' is not in the command whitelist"
    # destructive commands must not reference parent dirs (rm -rf /tmp/.. bypass)
    for seg in re.split(r"[\|;&]", norm):
        tok, base = _segment_token(seg)
        if base in BASH_NO_DOTDOT and re.search(r"\.\.[\\/]| \.\.$", seg):
            return f"Blocked: '{base}' with '..' path escape is not allowed"
    return None


def docker_bash(cmd, work_dir, timeout=60):
    """Run a command inside a Docker sandbox when BASH_DOCKER=1 or
    DOCKER_SANDBOX=1 and docker is available. Returns the combined output, or
    None when docker is not in use or the run failed (caller falls back to
    the local shell)."""
    if not (os.environ.get("BASH_DOCKER") or os.environ.get("DOCKER_SANDBOX") == "1"):
        return None
    image = os.environ.get("BASH_DOCKER_IMAGE", "python:3.12-slim")
    mount = f"{Path(work_dir).resolve()}:/workspace"
    if os.environ.get("BASH_DOCKER_READONLY"):
        mount += ":ro"
    dcmd = ["docker", "run", "--rm", "-i",
            "-v", mount,
            "-w", "/workspace", "-e", "PYTHONUTF8=1"]
    if os.environ.get("BASH_DOCKER_MEM"):
        dcmd += ["--memory", os.environ["BASH_DOCKER_MEM"]]
    if os.environ.get("BASH_DOCKER_SWAP"):
        dcmd += ["--memory-swap", os.environ["BASH_DOCKER_SWAP"]]
    if os.environ.get("BASH_DOCKER_USER"):
        dcmd += ["--user", os.environ["BASH_DOCKER_USER"]]
    dcmd += [image, "sh", "-lc", cmd]
    try:
        r = subprocess.run(
            dcmd, capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return ((r.stdout or "")[-3000:]
                + ("\nSTDERR:\n" + (r.stderr or "")[-1000:] if r.stderr else ""))
    except Exception as e:
        log.warning("Docker bash failed (%s), falling back to local shell", e)
        return None
