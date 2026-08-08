"""Tool dispatch for the agent loop: anti-repeat guard, shell aliases,
validation, question/plan stops, CONFIRM flow, per-session stats.
Extracted from agent.py run_agent_loop (one ```tool block at a time)."""
import json
import re

from tools import execute_tool, validate_tool
from tools import _state as _s


def _plan_mark(ctx, result):
    """Stage 31: plan tree UI — after each executed tool, mark the first
    pending plan step as done (or error when the tool failed) and emit an
    updated {type:'plan'} event so the UI can re-render the tree."""
    try:
        with _s.PLAN_LOCK:
            if not _s.PLAN_STEPS:
                return
            failed = isinstance(result, str) and result.startswith("Error")
            for st in _s.PLAN_STEPS:
                if st["status"] == "pending":
                    st["status"] = "error" if failed else "done"
                    break
            else:
                return
            ctx["emit"]({"type": "plan", "steps": list(_s.PLAN_STEPS)})
    except Exception:
        pass


def _sess_record(stats, name, result):
    """Per-session tool stats (calls/errors) used for the dynamic context advice."""
    if stats is None:
        return
    s = stats.setdefault(name, {"calls": 0, "errors": 0})
    s["calls"] += 1
    if isinstance(result, str) and (result.startswith("Error:") or result.startswith("Blocked:")):
        s["errors"] += 1


def _auto_confirm_safe(name, tc):
    """AUTO_CONFIRM_SAFE=1: write to a BRAND-NEW file (does not exist yet) is
    auto-approved; overwrites, edits, bash, commit, undo still require 'yes'."""
    import os as _os
    if name != "write" or _os.environ.get("AUTO_CONFIRM_SAFE") != "1":
        return False
    try:
        from tools import resolve as _resolve
        return not _resolve(tc.get("path", "")).exists()
    except Exception:
        return False
def _empty_or_trivial(steps):
    steps = [s for s in steps if len(str(s).strip()) > 2
             and not re.fullmatch(r"step\s*\d+", str(s).strip(), re.IGNORECASE)
             and not re.fullmatch(r"шаг\s*\d+", str(s).strip(), re.IGNORECASE)]
    return steps


def _rag_over_plan(steps):
    """Stage 33: multi-turn RAG ('RAG over plan'). Once the model proposes a
    plan, pre-load the files it is about to touch: RAG-search each step for
    file names, then read the top files so the execution turns start with
    real content instead of the model guessing paths/text. AI_RAG_OVER_PLAN=0
    disables. Returns a system-prompt block or None (best-effort, never raises)."""
    import os as _os
    if _os.environ.get("AI_RAG_OVER_PLAN") == "0":
        return None
    try:
        from rag import rag_search
        hits, paths = [], []
        for step in list(steps)[:4]:
            res = rag_search(str(step), top_k=3, hybrid=True)
            if not isinstance(res, str) or res.startswith(("RAG not", "No embed", "RAG scoped", "RAG search error")):
                continue
            for line in res.splitlines():
                m = re.match(r"^\[\d+\.\d+\]\s+(.+?):\d+", line.strip())
                if m:
                    p = m.group(1).strip()
                    if p and p not in paths:
                        paths.append(p)
            if len(paths) >= 6:
                break
        if not paths:
            return None
        block = ["[Plan context — files this plan is likely to touch (RAG over plan). "
                 "Use their EXACT current content for edit/old-text.]"]
        total = 0
        for p in paths[:6]:
            fp = _s.WORK_DIR / p
            try:
                if not fp.is_file():
                    continue
                text = fp.read_text("utf-8", errors="ignore")[:2000]
            except Exception:
                continue
            total += len(text)
            if total > 10000:
                break
            block.append(f"### {p}\n{text}")
        if len(block) == 1:
            return None
        return "\n\n".join(block)[:12000]
    except Exception:
        return None


def execute_tool_block(idx, tc, ctx):
    """Execute ONE parsed tool block.

    ctx: dict with msgs, content (model output of this iteration), full
    (list-holder, [0] is the running output string), emit, no_confirm,
    session_id, sess_stats, pending_set, state (dict with last_call_key /
    repeats / last_result_name / last_result_text).

    Returns (entries, calls_made, needs_break). Mutates ctx["state"] and
    ctx["full"][0]."""
    name = tc.get("tool", "")
    tc = dict(tc)
    tc.pop("tool", None)
    full = ctx["full"]
    state = ctx["state"]
    msgs = ctx["msgs"]
    content = ctx["content"]
    entries = []
    calls = []

    # anti-repeat: identical tool call twice in a row = model loop, stop it.
    # Must run BEFORE the name check so broken/empty blocks are caught too.
    call_key = (name, json.dumps(tc, ensure_ascii=False, sort_keys=True))
    err_repeat = (name == state["last_result_name"] and state["last_result_text"] and
                  any(w in state["last_result_text"] for w in ("not found", "not installed", "invalid", "не найден")))
    if call_key == state["last_call_key"] or err_repeat:
        state["repeats"] += 1
        if state["repeats"] >= 2:
            full[0] += "[tool: identical call repeated — stop repeating, answer directly]\n"
            return entries, calls, True
    else:
        state["last_call_key"], state["repeats"] = call_key, 1

    # Aliases: models often call python/shell/terminal instead of bash
    if name in ("python", "shell", "terminal", "cmd", "run"):
        tc["cmd"] = tc.get("cmd", tc.get("command", ""))
        name = "bash"
    if not name:
        entries.append(f"[tool: missing 'tool' key in block {idx+1}]")
        return entries, calls, False
    ve = validate_tool({**tc, "tool": name})
    if ve:
        entries.append(f"[tool:{name}] {ve}")
        calls.append(name)
        return entries, calls, False

    DESTRUCTIVE = () if ctx["no_confirm"] else ("write", "edit", "bash", "commit", "undo")

    if name == "edit" and tc.get("old") is not None:
        # inline diff preview (Cursor-style): shown to the user before applying
        try:
            from tools import diff_preview
            d = diff_preview(tc.get("path", ""), tc.get("old", ""), tc.get("new", ""))
            if d:
                ctx["emit"]({"type": "diff", "path": tc.get("path", ""), "diff": d[:4000]})
        except Exception:
            pass

    if name in DESTRUCTIVE and not state.get("git_snap"):
        # git pre-backup: snapshot the tree once before the first mutating tool
        state["git_snap"] = True
        try:
            import os as _os
            import tools as _tools
            if (not ctx["no_confirm"]) or _os.environ.get("AI_GIT_SNAPSHOT") == "1":
                sn = _tools.git_prebackup()
                if sn and "snapshot" in sn:
                    full[0] += f"[tool: pre-backup] {sn}\n"
        except Exception:
            pass

    if name == "question":
        r = execute_tool(name, tc)
        _sess_record(ctx["sess_stats"], name, r)
        ctx["emit"]({"type": "tool", "name": name, "args": tc, "result": r[:200]})
        entries.append(f"[tool:{name}] {r[:2000]}")
        calls.append(name)
        full[0] += f"[tool:question] {r[:2000]}\n"
        msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content": r[:2000]})
        return entries, calls, True

    if name == "plan":
        steps = tc.get("steps", [])
        if isinstance(steps, str):
            steps = [s.strip() for s in re.split(r'[.,;\n]+', steps) if s.strip()]
        steps = _empty_or_trivial(steps)
        if not steps:
            entries.append("[tool:plan] plan is empty or trivial (no real steps) — answer directly, do NOT call plan for questions or chat.")
            calls.append(name)
            return entries, calls, False
        plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
        with _s.PLAN_LOCK:
            _s.PLAN_STEPS = [{"text": s, "status": "pending"} for s in steps]
            ctx["emit"]({"type": "plan", "steps": list(_s.PLAN_STEPS)})
        full[0] += f"\n[PLAN]\n{plan_text}\n\nReply 'yes' to execute plan.\n"
        msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content": f"Plan proposed:\n{plan_text}\nReply 'yes' to execute."})
        rag_ctx = _rag_over_plan(steps)
        if rag_ctx:
            msgs.append({"role": "system", "content": rag_ctx})
            try:
                ctx["emit"]({"type": "status",
                             "msg": f"RAG over plan: pre-loaded context for {rag_ctx.count('###')} file(s)"})
            except Exception:
                pass
        return entries, calls, True

    if name in DESTRUCTIVE:
        last = (msgs[-1]["content"].strip().lower() if msgs else "")[:5]
        if _auto_confirm_safe(name, tc):
            # AUTO_CONFIRM_SAFE=1: brand-new file writes need no confirmation
            r = execute_tool(name, tc)
            _sess_record(ctx["sess_stats"], name, r)
            ctx["emit"]({"type": "tool", "name": name, "args": tc, "result": r[:200]})
            entries.append(f"[tool:{name}] {r[:2000]}")
            calls.append(name)
            state["last_result_name"], state["last_result_text"] = name, r[:2000]
            _plan_mark(ctx, r)
        elif last in ("yes", "y", "go a", "да", "ok", "cont", "proc", "do i"):
            r = execute_tool(name, tc)
            _sess_record(ctx["sess_stats"], name, r)
            ctx["emit"]({"type": "tool", "name": name, "args": tc, "result": r[:200]})
            entries.append(f"[tool:{name}] {r[:2000]}")
            calls.append(name)
            state["last_result_name"], state["last_result_text"] = name, r[:2000]
            _plan_mark(ctx, r)
        else:
            ask = f"Allow {name}?\nArgs: {json.dumps(tc, ensure_ascii=False)[:300]}"
            full[0] += f"\n[CONFIRM] {ask}\nReply 'yes' to proceed.\n"
            msgs.append({"role": "assistant", "content": content})
            hint = f"User must reply 'yes' to execute {name}."
            msgs.append({"role": "system", "content": hint})
            msgs.append({"role": "user", "content": ask})
            ctx["pending_set"](ctx["session_id"], name, tc)
            return entries, calls, True
        return entries, calls, False

    r = execute_tool(name, tc)
    _sess_record(ctx["sess_stats"], name, r)
    ctx["emit"]({"type": "tool", "name": name, "args": tc, "result": r[:200]})
    entries.append(f"[tool:{name}] {r[:2000]}")
    calls.append(name)
    state["last_result_name"], state["last_result_text"] = name, r[:2000]
    _plan_mark(ctx, r)
    return entries, calls, False
