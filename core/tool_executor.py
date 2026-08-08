"""Tool dispatch for the agent loop: anti-repeat guard, shell aliases,
validation, question/plan stops, CONFIRM flow, per-session stats.
Extracted from agent.py run_agent_loop (one ```tool block at a time)."""
import json
import re

from tools import execute_tool, validate_tool


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
        full[0] += f"\n[PLAN]\n{plan_text}\n\nReply 'yes' to execute plan.\n"
        msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content": f"Plan proposed:\n{plan_text}\nReply 'yes' to execute."})
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
        elif last in ("yes", "y", "go a", "да", "ok", "cont", "proc", "do i"):
            r = execute_tool(name, tc)
            _sess_record(ctx["sess_stats"], name, r)
            ctx["emit"]({"type": "tool", "name": name, "args": tc, "result": r[:200]})
            entries.append(f"[tool:{name}] {r[:2000]}")
            calls.append(name)
            state["last_result_name"], state["last_result_text"] = name, r[:2000]
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
    return entries, calls, False
