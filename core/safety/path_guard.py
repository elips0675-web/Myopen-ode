"""Path resolution + workspace jail + similar-file hints. Extracted from tools.py."""
import logging
import os
from pathlib import Path

log = logging.getLogger('path_guard')


def resolve(path, work_dir):
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(work_dir) / path


def extra_roots():
    """Additional allowed roots OUTSIDE the workspace (EXTRA_ROOTS env,
    ';' or '|' separated, e.g. EXTRA_ROOTS="E:\\test mycode;D:\\data").
    The agent can then read/write files in those folders too — useful for
    'create an app in folder X' requests without switching the project."""
    raw = os.environ.get("EXTRA_ROOTS", "")
    roots = []
    for r in raw.replace("|", ";").split(";"):
        r = r.strip().strip('"')
        if r:
            try:
                roots.append(Path(r).resolve())
            except Exception:
                pass
    return roots


def allow_outside():
    """ALLOW_OUTSIDE=1 lifts the workspace jail completely (dangerous:
    the model may touch any path the OS user can). Local single-user use
    only."""
    return os.environ.get("ALLOW_OUTSIDE", "") == "1"


def ensure_safe_path(path, work_dir):
    """Resolve path and verify it stays within WORK_DIR to prevent directory
    traversal. EXTRA_ROOTS adds allowed roots outside the workspace;
    ALLOW_OUTSIDE=1 lifts the jail entirely."""
    if not path or not isinstance(path, str):
        return "Error: path must be a non-empty string"
    if path.startswith(("/path/to", "/tmp", "/var", "/usr", "/home",
                        "/etc", "/bin", "/dev", "C:\\Windows", "C:\\Program")):
        return (f"Error: path '{path}' looks invented. Use RELATIVE paths or paths "
                f"inside the workspace (use list/glob to see files). "
                f"Do NOT give tutorials — retry with a correct path.")
    p = resolve(path, work_dir).resolve()
    wk = Path(work_dir).resolve()
    if wk in p.parents or p == wk:
        return None
    if allow_outside():
        return None
    for root in extra_roots():
        if root in p.parents or p == root:
            return None
    hint = (" Set EXTRA_ROOTS='<folder>' (e.g. EXTRA_ROOTS='E:\\test mycode') to allow "
            "working outside the workspace, or switch the project.") if path.startswith(("C:", "D:", "E:", "F:")) else ""
    return (f"Error: path '{path}' is outside workspace '{work_dir}'. "
            f"Use RELATIVE paths inside the workspace (use list/glob to see files)."
            f"{hint} Do NOT give tutorials — retry with a correct path.")


def similar_files(path, work_dir, limit=5):
    """Suggest nearby files when a path was not found — helps the model fix paths."""
    try:
        name = Path(path).name.lower()
        candidates = []
        exts = (".py", ".js", ".ts", ".json", ".md", ".html", ".css", ".txt", ".yaml", ".yml")
        for p in list(Path(work_dir).rglob("*"))[:4000]:
            if not p.is_file() or not p.suffix.lower() in exts:
                continue
            if any(x in p.parts for x in (".git", "__pycache__", ".agent_sessions",
                                          ".rag_cache", ".agent_backups", ".agent_memory", "node_modules")):
                continue
            fn = p.name.lower()
            if fn == name or fn.startswith(name[:6]) or name.startswith(fn[:6]):
                try:
                    candidates.append(str(p.relative_to(work_dir)))
                except Exception:
                    pass
        if candidates:
            return f". Similar files in workspace: {', '.join(sorted(set(candidates))[:limit])}"
    except Exception:
        pass
    return ""
