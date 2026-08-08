"""File versioning (backups), git pre-backup/restore, verify, git helpers."""
import os, re, subprocess, shutil, sys
from pathlib import Path
from datetime import datetime
from ._state import WORK_DIR, BACKUP_DIR, MAX_BACKUPS
from ._state import _sync_register

def init_backup():
    global BACKUP_DIR
    BACKUP_DIR = WORK_DIR / ".agent_backups"
    BACKUP_DIR.mkdir(exist_ok=True)

def backup(path):
    if BACKUP_DIR is None: return
    p = Path(path) if os.path.isabs(path) else WORK_DIR / path
    if p.exists():
        key = str(p).replace("\\", "_").replace("/", "_").replace(":", "")
        b = BACKUP_DIR / key / datetime.now().strftime("%H%M%S_%f")
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, b)
        versions = sorted(b.parent.iterdir())
        for v in versions[:-MAX_BACKUPS]:
            v.unlink()

def undo(path):
    if BACKUP_DIR is None: return f"No backup dir"
    key = str(Path(path) if os.path.isabs(path) else WORK_DIR / path)
    key = key.replace("\\", "_").replace("/", "_").replace(":", "")
    bd = BACKUP_DIR / key
    if not bd.exists(): return f"No backup for {path}"
    versions = sorted(bd.iterdir())
    if not versions: return f"No backup for {path}"
    dst = Path(path) if os.path.isabs(path) else WORK_DIR / path
    shutil.copy2(versions[-1], dst)
    versions[-1].unlink()
    return f"Undone: {path} restored"

# ─── git pre-backup / restore all ─────────────────────────
def git_prebackup():
    """Snapshot the whole working tree into .agent_backups/git_snapshots/<id>:
    `git diff --binary HEAD` (tracked changes) + copies of all untracked files.
    Called automatically before the first mutating tool of a run, and on
    demand via the snapshot tool."""
    if BACKUP_DIR is None: return "No backup dir"
    if not (WORK_DIR / ".git").exists(): return "Not a git repo"
    snap = BACKUP_DIR / "git_snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = snap / sid
    d.mkdir(parents=True, exist_ok=True)
    diff = subprocess.run(["git", "diff", "--binary", "HEAD"], cwd=str(WORK_DIR),
                          capture_output=True, text=True, timeout=60)
    (d / "tracked.patch").write_text(diff.stdout)
    st = subprocess.run(["git", "status", "--short"], cwd=str(WORK_DIR),
                        capture_output=True, text=True, timeout=30)
    untracked = [ln[3:].strip().strip('"') for ln in st.stdout.splitlines()
                 if ln.startswith("??")]
    skip_prefixes = {".git", BACKUP_DIR.name}
    untracked = [rel for rel in untracked
                 if rel and ".." not in rel
                 and not any(rel == p or rel.startswith(p + "/") for p in skip_prefixes)]
    copied = 0
    ut_copy = d / "untracked"
    ut_copy.mkdir(exist_ok=True)
    for rel in untracked:
        src = WORK_DIR / rel
        dst = ut_copy / rel
        try:
            if src.is_dir():
                shutil.copytree(src, dst)
            elif src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            copied += 1
        except OSError:
            continue
    (d / "untracked.txt").write_text("\n".join(untracked))
    return (f"Git snapshot {sid}: {copied} untracked file(s) copied "
            f"({'changes' if diff.stdout.strip() else 'clean tree'})")

def git_restore_all(sid=None):
    """Restore the working tree to the state captured by git_prebackup(): reverse
    the tracked diff, delete untracked files created after the snapshot and
    bring back the untracked files that existed at snapshot time."""
    if BACKUP_DIR is None: return "No backup dir"
    snap = BACKUP_DIR / "git_snapshots"
    if not snap.exists(): return "No snapshots to restore"
    dirs = sorted(d for d in snap.iterdir() if d.is_dir())
    if sid:
        dirs = [d for d in dirs if d.name == sid]
    if not dirs: return "No snapshots to restore"
    d = dirs[-1]
    msgs = []
    patch = d / "tracked.patch"
    has_patch = (patch.exists() and patch.read_text(encoding="utf-8", errors="replace").strip())
    co = subprocess.run(["git", "checkout", "--", "."], cwd=str(WORK_DIR),
                        capture_output=True, text=True, timeout=60)
    msgs.append("tracked reset to HEAD" if co.returncode == 0
                else f"checkout failed: {co.stderr.strip()[:120]}")
    if has_patch:
        r = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn", str(patch)],
                           cwd=str(WORK_DIR), capture_output=True, text=True, timeout=60)
        msgs.append("snapshot changes re-applied" if r.returncode == 0
                    else f"re-apply failed: {r.stderr.strip()[:120]}")
    else:
        msgs.append("no snapshot changes")
    # current untracked files (gitignored dirs like .agent_backups are excluded)
    st = subprocess.run(["git", "status", "--short"], cwd=str(WORK_DIR),
                        capture_output=True, text=True, timeout=30)
    current_untracked = [ln[3:].strip().strip('"') for ln in st.stdout.splitlines()
                         if ln.startswith("??")]
    skip_prefixes = {".git", BACKUP_DIR.name}
    current_untracked = [rel for rel in current_untracked
                         if rel and ".." not in rel
                         and not any(rel == p or rel.startswith(p + "/") for p in skip_prefixes)]
    kept = []
    untracked_list = d / "untracked.txt"
    if untracked_list.exists():
        kept = [rel for rel in untracked_list.read_text(encoding="utf-8",
                                                        errors="replace").splitlines()
                if rel.strip()]
    removed = 0
    for rel in current_untracked:
        if not rel or ".." in rel:
            continue
        p = WORK_DIR / rel
        if rel in kept:
            continue  # existed at snapshot time; restore it from the copy below
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True); removed += 1
        elif p.exists():
            p.unlink(missing_ok=True); removed += 1
    restored = 0
    ut_copy = d / "untracked"
    if ut_copy.exists():
        for rel in kept:
            src = ut_copy / rel
            dst = WORK_DIR / rel
            try:
                if src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                restored += 1
            except OSError:
                continue
    msgs.append(f"{removed} new untracked item(s) removed, {restored} restored")
    return f"Restored to snapshot {d.name}: " + "; ".join(msgs)

# ─── verify ───────────────────────────────────────────────
def diff_preview(path, old, new, context=3):
    """Unified diff of an upcoming edit — shown to the user before it is
    applied (Cursor-style inline preview)."""
    import difflib
    old_lines = (old or "").splitlines(keepends=True)
    new_lines = (new or "").splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines,
                                fromfile=str(path), tofile=f"{path} (preview)",
                                n=context)
    return "".join(diff).strip()

VERIFY_COMMANDS = {
    ".js,.jsx,.ts,.tsx": "npx tsc --noEmit 2>&1 || true",
    ".py": "python -m py_compile {file} 2>&1 || true",
    ".json": "python -m json.tool {file} > nul 2>&1 && echo OK || echo Invalid JSON",
}

def verify_file(path):
    ext = "".join(Path(path).suffixes)
    for pattern, cmd in VERIFY_COMMANDS.items():
        if any(ext.endswith(e) for e in pattern.split(",")):
            p = Path(path) if os.path.isabs(path) else WORK_DIR / path
            fcmd = cmd.replace("{file}", f'"{p}"')
            r = subprocess.run(fcmd, shell=True, capture_output=True, text=True, timeout=15)
            return r.stdout.strip()[:1000] or r.stderr.strip()[:1000]
    return ""

# ─── git helpers ──────────────────────────────────────────
def git(*args):
    try:
        r = subprocess.run(["git"] + list(args), cwd=str(WORK_DIR), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or r.stderr.strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        return "(git not available)"

_sync_register(sys.modules[__name__])
