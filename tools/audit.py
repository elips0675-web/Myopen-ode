"""Audit log and per-tool statistics."""
import json, sys
import logging
from datetime import datetime
from ._state import WORK_DIR, AUDIT_LOG, TOOL_STATS
from ._state import _sync_register

log = logging.getLogger("tools")

def _audit(name, args, result):
    """Log every tool call with timestamp (action audit)."""
    global AUDIT_LOG
    if AUDIT_LOG is None:
        AUDIT_LOG = WORK_DIR / ".agent_audit.log"
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        arg_preview = json.dumps(args, ensure_ascii=False)[:200]
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {name} {arg_preview}\n")
    except Exception:
        pass

def _stats_record(name, result):
    s = TOOL_STATS.setdefault(name, {"calls": 0, "errors": 0})
    s["calls"] += 1
    if isinstance(result, str) and (result.startswith("Error:") or result.startswith("Blocked:")):
        s["errors"] += 1
        if s["errors"] >= 3 and s["errors"] % 3 == 0:
            log.warning("Tool '%s' is failing repeatedly (%d errors of %d calls) — model may be passing bad arguments",
                        name, s["errors"], s["calls"])

_sync_register(sys.modules[__name__])
