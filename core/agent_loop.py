"""The agent loop: LLM -> parse tool blocks -> execute -> feed back -> repeat.

Extracted from agent.py. Dependencies (config, sessions, pending/cancel
state) are injected via the `deps` module (the HTTP layer, agent.py) so this
module stays independent of FastAPI and can be reused (CLI, tests, MCP).

AUTHOR NOTE: everything below keeps the exact semantics of the previous
monolithic run_agent_loop — refactoring is pure extraction, no behavior change.
"""
import json
import logging
import os
import re
import time

from core.tool_executor import execute_tool_block
from core.tool_parser import _strip_system_markers, parse_tool_blocks

log = logging.getLogger('agent_loop')

VALID_TOOLS = ("read", "write", "edit", "bash", "glob", "grep", "list", "web",
               "diff", "commit", "undo", "verify", "plan", "search", "websearch",
               "question", "skill", "patch", "task", "todo", "lsp",
               "testgen", "db_query", "deps", "mcp",
               "snapshot", "restore")


def _dynamic_context(tool_name, tool_text, it, sess_stats=None, project="workspace"):
    """Short orientation block for the model: which project, what was the
    last tool action and whether it succeeded, plus per-session tool errors.
    7B models lose track of context after 3-4 iterations — this anchors them."""
    parts = [f"You are working in project: {project} (iteration {it + 1})"]
    if tool_name:
        status = "error" if tool_text.startswith(("Error:", "Blocked:")) else "ok"
        parts.append(f"Last action: {tool_name} (result: {status})")
    if sess_stats:
        errs = {n: s for n, s in sess_stats.items() if s.get("errors", 0) > 0}
        if errs:
            lines = []
            for name, s in sorted(errs.items())[:3]:
                lines.append(f"- {name}: {s['errors']} error(s) of {s['calls']} call(s)")
            parts.append("Tool errors this session:\n" + "\n".join(lines)
                         + "\nAdvice: fix the arguments — use glob or list to find the real path "
                           "before read/edit/write.")
    return "\n".join(parts) + "\n"


def summarize_context(msgs, deps):
    total = sum(len(m.get("content", "")) for m in msgs)
    if total < 4000:
        return msgs
    keep = msgs[:1]
    tail = msgs[-6:] if len(msgs) > 6 else msgs[1:]
    to_summarize = msgs[1:-6] if len(msgs) > 6 else []
    if to_summarize:
        text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in to_summarize)
        prompt = f"Summarize this conversation in 2-3 sentences:\n\n{text[:1500]}"
        try:
            import requests
            r = requests.post(f"{deps.OLLAMA_URL}/api/generate", json={
                "model": deps.PLANNER_MODEL,
                "prompt": prompt, "stream": False,
                "options": {"temperature": 0.1, "num_predict": 256}
            }, timeout=30)
            summary = r.json().get("response", "")
            if summary:
                keep.append({"role": "system", "content": f"[Summary]: {summary[:500]}"})
        except Exception as e:
            log.warning("Summarize failed: %s", e)
    keep.extend(tail)
    return keep


def run_agent_loop(msgs, session_id, events=None, model=None, deps=None):
    """Run agent loop. events: optional callback(ev: dict) for live tool progress.
    model: user-selected model overrides MODEL (empty = default).
    deps: module with the HTTP-layer state (config, sessions, pending/cancel);
    falls back to importing agent.py when not provided (CLI/tests)."""
    if deps is None:
        import agent as deps

    def _emit(ev):
        if events:
            try:
                events(ev)
            except Exception:
                pass

    msgs = summarize_context(msgs, deps)
    if session_id:
        was_interrupted = deps.session_interrupted(session_id)
        try:
            deps._state_path(session_id).write_text(
                json.dumps({"running": True, "started_at": deps.datetime.now().isoformat()}))
        except OSError:
            pass
        if was_interrupted:
            msgs.append({"role": "system",
                         "content": "[session was interrupted mid-run earlier — continuing from the last checkpoint]"})
    full = ""
    max_iter = int(os.environ.get("AGENT_MAX_ITER", "12"))
    max_time = float(os.environ.get("AGENT_TIMEOUT", "300"))
    start_time = time.time()
    total_tokens = sum(len(m.get("content", "")) / 4 for m in msgs)
    format_retried = 0
    err_hint_retried = 0
    code_hint_retried = 0
    last_call_key = None
    repeats = 0
    last_result_name = None
    last_result_text = ""
    sess_stats = {}
    no_tool_iterations = 0
    active_model = None
    user_model = model

    for it in range(max_iter):
        if time.time() - start_time > max_time:
            full += f"\n[tool: TIMEOUT — agent loop exceeded {int(max_time)}s]\n"
            break
        if session_id and deps._cancel_pending(session_id):
            full += "\n[cancelled]\n"
            deps._cancel_clear(session_id)
            break

        try:
            import tools as _tools_mod
            _tools_mod.set_json_mode(False)
        except Exception:
            pass

        _emit({"type": "status", "msg": f"iteration {it+1}/{max_iter}"})

        # Summarize context every 3 iterations to keep token usage in check
        if it > 0 and it % 3 == 0:
            msgs = summarize_context(msgs, deps)

        # pending confirmation: user said "yes" — execute the deferred tool without calling the model
        pending = deps._pending_get(session_id)
        if pending:
            name, tc = pending
            last = (msgs[-1]["content"].strip().lower() if msgs else "")[:5]
            if last in ("yes", "y", "go a", "да", "ok", "cont", "proc", "do i"):
                r = deps.execute_tool(name, tc)
                _emit({"type": "tool", "name": name, "args": tc, "result": r[:200]})
                full += f"\n[tool:{name}] {r[:2000]}\n"
                msgs.append({"role": "assistant", "content": f"(confirmed: {name})"})
                msgs.append({"role": "user", "content": r[:2000]})
                continue
            deps._pending_set(session_id, name, tc)  # not confirmed yet, keep waiting

        if active_model is None or it > 0:
            active_model = user_model or (deps.MODEL if it > 0 else deps.PLANNER_MODEL)
        current_model = active_model
        if not model and it == 0 and deps.PLANNER_MODEL not in deps._available_models:
            log.info("PLANNER_MODEL %s not installed, using %s", deps.PLANNER_MODEL, deps.MODEL)
            current_model = deps.MODEL
        if not model and it == 0 and current_model != deps.MODEL:
            first_user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
            if len(first_user.strip()) < 80:
                # short first message = simple question/chat, planner is a waste
                log.info("Short first message — skipping planner, using %s", deps.MODEL)
                current_model = deps.MODEL
        if it > 0:
            active_model = current_model
        project = deps.WORK_DIR.name or str(deps.WORK_DIR)
        dyn = {"role": "system",
               "content": _dynamic_context(last_result_name, last_result_text, it, sess_stats, project)}
        native_on = False
        native_calls = []
        try:
            import tools as _tools_mod
            native_on = _tools_mod.native_supported(current_model)
        except Exception:
            pass
        if native_on:
            try:
                call_msgs = []
                for m in msgs + [dyn]:
                    if (m.get("role") == "system"
                            and "RULES" in (m.get("content") or "")[:4000]):
                        call_msgs.append({"role": "system",
                                          "content": _tools_mod.native_system_prompt()})
                    else:
                        call_msgs.append(m)
                n_content, native_calls, n_tokens = _tools_mod.native_chat(
                    call_msgs, current_model)
                content, tokens_used = n_content, n_tokens
                _emit({"type": "status", "msg": f"native tool call round {it+1}"})
                if not content and not native_calls:
                    raise RuntimeError("empty native response")
            except Exception as e:
                log.warning("native_chat failed (%s), falling back to legacy", e)
                native_on = False
                native_calls = []
        if not native_on:
            if events:
                try:
                    content = deps.stream_ollama(
                        msgs + [dyn], current_model,
                        on_chunk=lambda f: _emit({"type": "text", "text": f}))
                    tokens_used = 0
                except Exception as e:
                    log.warning("stream failed (%s), falling back to call_ollama", e)
                    result = deps.call_ollama(msgs + [dyn], current_model)
                    content, tokens_used = (result if isinstance(result, tuple)
                                            else (result, 0))
            else:
                result = deps.call_ollama(msgs + [dyn], current_model)
                content, tokens_used = (result if isinstance(result, tuple)
                                        else (result, 0))
        if not content and not (native_on and native_calls):
            break
        total_tokens += tokens_used or (len(content) / 4)

        if native_on:
            if not native_calls:
                full += _strip_system_markers(content)
                break
            before = _strip_system_markers(content).strip()
            if before:
                full += before + "\n"
                msgs.append({"role": "assistant", "content": before})
            tool_blocks = [(None, None, {"tool": c["name"], **c["arguments"]})
                           for c in native_calls]
        else:
            tool_blocks = parse_tool_blocks(content, VALID_TOOLS)

        if not tool_blocks:
            no_tool_iterations += 1
            if no_tool_iterations >= 2 and it > 0 and current_model != deps.MODEL:
                # model keeps ignoring tool format — route to the main model
                log.warning("Model %s produced no tool blocks for %d iterations — routing to %s",
                            current_model, no_tool_iterations, deps.MODEL)
                user_model = None
                active_model = deps.MODEL
                full += _strip_system_markers(content) + "\n"
                continue
            if not model and it == 0 and current_model != deps.MODEL:
                # planner model (1.5b) often ignores tool format — retry with main model
                log.info("Planner iteration produced no tool blocks; retrying with %s", deps.MODEL)
                full += _strip_system_markers(content) + "\n"
                continue
            last_content = (msgs[-1].get("content", "") if msgs else "") or ""
            err_markers = ("Error:", "not found", "not installed", "invalid",
                           "looks invented", "outside workspace", "missing")
            if (err_hint_retried < 2 and last_content.startswith("[tool:")
                    and any(m in last_content[:300] for m in err_markers)):
                # previous tool call failed but the model replied with prose —
                # nudge it back into tool format (with a concrete fix example)
                err_hint_retried += 1
                msgs.append({"role": "system", "content":
                             "The previous tool call failed. You MUST respond with a "
                             "corrected ```tool JSON block. Do NOT write explanations or plans.\n"
                             "Example of fixing a tool error:\n"
                             'Model tried: {"tool": "edit", "path": "app.py", "old": "def foo()", "new": "def bar()"}\n'
                             'Error: file not found\n'
                             'Corrected: {"tool": "glob", "pattern": "**/*.py"} — locate the real path, '
                             'then read it and retry the edit with the EXACT text from the read output.'})
                try:
                    import tools as _tools_mod
                    _tools_mod.set_json_mode(True)
                except Exception:
                    pass
                log.info("Tool error, nudging model back to tool format (retry %d)", err_hint_retried)
                continue
            if (code_hint_retried < 2 and len(content.strip()) > 40
                    and re.search(r'^\s*(def |class |import |from |function |const |let |var |if |for |while )',
                                  content, re.M)):
                # model wrote code/prose instead of a tool — nudge it to write the file
                code_hint_retried += 1
                msgs.append({"role": "system", "content":
                             "Do NOT write code in your reply. Put code into a file with the "
                             "`write` or `edit` tool, then verify it with `bash`."})
                try:
                    import tools as _tools_mod
                    _tools_mod.set_json_mode(True)
                except Exception:
                    pass
                log.info("Code detected in reply, nudging to write tool (retry %d)", code_hint_retried)
                continue
            if format_retried < 1 and len(content.strip()) > 20:
                # main model ignored tool format (free-form answer) — one strict retry
                hint = "[Format error: reply ONLY with ```tool JSON blocks. No prose, no code blocks.]"
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content": hint})
                full += _strip_system_markers(content) + "\n"
                format_retried += 1
                try:
                    import tools as _tools_mod
                    _tools_mod.set_json_mode(True)
                except Exception:
                    pass
                continue
            full += _strip_system_markers(content)
            break

        if not native_on:
            before = _strip_system_markers(content[:tool_blocks[0][0].start()].strip())
            if before:
                full += before + "\n"
                msgs.append({"role": "assistant", "content": before})

        all_results = []
        calls_made = []
        needs_break = False
        ctx = {
            "msgs": msgs,
            "content": content,
            "full": [""],
            "emit": _emit,
            "no_confirm": deps.NO_CONFIRM,
            "session_id": session_id,
            "sess_stats": sess_stats,
            "pending_set": deps._pending_set,
            "state": {"last_call_key": last_call_key, "repeats": repeats,
                      "last_result_name": last_result_name, "last_result_text": last_result_text},
        }
        for idx, (match, raw_json, tc) in enumerate(tool_blocks):
            entries, calls, brk = execute_tool_block(idx, tc, ctx)
            all_results += entries
            calls_made += calls
            if brk:
                needs_break = True
                break
        full += ctx["full"][0]
        last_call_key, repeats = ctx["state"]["last_call_key"], ctx["state"]["repeats"]
        last_result_name, last_result_text = ctx["state"]["last_result_name"], ctx["state"]["last_result_text"]

        if calls_made:
            no_tool_iterations = 0
        if needs_break:
            break
        if all_results:
            combined = "\n".join(all_results)
            full += combined + "\n"
            msgs.append({"role": "assistant", "content": f"(called: {', '.join(calls_made)})"})
            msgs.append({"role": "user", "content": combined})
            total_tokens += len(combined) / 4

        if deps.MAX_TOKENS and total_tokens > deps.MAX_TOKENS:
            full += f"\n[tool: TOKEN_LIMIT — estimated {int(total_tokens)} tokens exceeded {deps.MAX_TOKENS}]\n"
            break

        if session_id and (it + 1) % 2 == 0:
            # runtime checkpoint: survive server crashes mid-run
            try:
                old = deps.load_session(session_id) or {}
                deps.save_session(session_id, old.get("title", session_id), msgs[1:])
                deps._state_path(session_id).touch()
            except Exception:
                pass

    if session_id:
        try:
            old = deps.load_session(session_id) or {}
            deps.save_session(session_id, old.get("title", session_id), msgs[1:])
        except Exception as e:
            log.warning("Save session %s: %s", session_id, e)
        try:
            deps._state_path(session_id).unlink(missing_ok=True)
        except OSError:
            pass

    return full
