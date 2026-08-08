"""Path resolution with workspace confinement."""
import sys
from ._state import WORK_DIR
from ._state import _sync_register
from core.safety.path_guard import resolve as _resolve, ensure_safe_path as _ensure_safe_path
from core.safety.path_guard import similar_files as _similar_files_impl

def resolve(path):
    return _resolve(path, WORK_DIR)

def ensure_safe_path(path):
    return _ensure_safe_path(path, WORK_DIR)

def _similar_files(path, limit=5):
    """Suggest nearby files when a path was not found — helps the model fix paths."""
    return _similar_files_impl(path, WORK_DIR, limit)

_sync_register(sys.modules[__name__])
