# Architect Skill

Use this skill when the user asks to improve, refactor, or extend the AI Coder agent itself (agent.py, tools.py, rag.py, lsp.py, ui.py, mcp_server.py). Act as an expert AI systems architect for local autonomous coding agents.

## Core principles
1. **Zero-cloud dependency**: agent must run fully offline on consumer hardware (RTX 3060 12GB).
2. **Prompt-based tool calling**: local models (7B-16B via Ollama) do NOT support native tool_calls. Use JSON-in-markdown extraction with fallback regex parsers.
3. **Defensive by default**: every file operation runs through path traversal checks BEFORE Path.resolve(). Bash uses blacklist + timeout.
4. **Incremental everything**: RAG indexes only changed files (per-file cache with mtime/size fingerprint). Backups version every write (max 50, FIFO). Context auto-summarizes every 3 iterations.
5. **Thread-safe state**: LLM cache and RAG state must be globals guarded properly (global keyword, locks if shared).

## Architecture stack (this project)
- Backend: FastAPI + uvicorn + SSE streaming, OpenAPI at /docs
- LLM: Ollama /api/chat with retry (3 attempts, exponential backoff) + fallback API (DeepSeek-V4-Flash via FLASH_PROVIDER / OpenAI / Claude), LLM cache with TTL (LLM_CACHE_TTL)
- Tools (28): read, write, edit, patch, bash, glob, grep, list, diff, commit, undo, verify, web, websearch, search (RAG), plan, question, skill, task, todo, lsp, testgen, db_query, deps, mcp + 3 plugins (.agent_plugins/*.py)
- RAG: hybrid BM25 (score 0.6*cosine + 0.4*bm25_norm), incremental disk cache (.rag_cache/file_*.json)
- UI: inline HTML + CodeMirror 5 (tabs, Ctrl+S via PUT /api/file), chat autocomplete (@ # /), dark theme, mobile-responsive
- Sessions: JSON CRUD (.agent_sessions/), memory summarization via PLANNER_MODEL
- LSP: JSON-RPC client in lsp.py (definition/references/hover/symbols/rename)
- Desktop: pywebview (desktop.py), MCP server (mcp_server.py)

## Tool calling protocol
Model outputs ONLY ```tool blocks:
```tool
{"tool": "edit", "path": "src/main.py", "old": "def old():", "new": "def new():"}
```
Parser must: extract ALL blocks (re.DOTALL), validate against schemas, execute sequentially feeding results back as user messages, auto-execute pending destructive tools only after explicit user confirmation ("yes"/"да"), halt on no blocks / max_iter / timeout. Aliases python/shell/terminal/cmd → bash.

## Security rules
- Path resolution: resolve() then check workspace in path.parents (prevent traversal).
- Bash: blacklist dangerous commands (rm -rf /, mkfs, dd, curl|sh), timeout, NO_CONFIRM=1 skips confirmations.
- Write/Edit/Patch: backup to .agent_backups/ before modification.
- No eval()/exec() of LLM output.

## RAG spec
- Chunking: split by top-level definitions (def/class/func/struct/pub fn), max 500 chars.
- Embedding: batch POST /api/embed (nomic-embed-text).
- Cache: per-file JSON with (mtime, size, model) fingerprint; re-embed only changed files.
- Search: BM25 (k1=1.5, b=0.75) + cosine, return top-k with [score] file:line.

## Context management
- Keep last 6 messages + summary of older.
- Summarize via PLANNER_MODEL every 3 iterations.
- Track eval_count + estimate fallback.

## UI requirements
- Dark/light via CSS vars + localStorage; diff +/- colors; confirm/question boxes with buttons.
- Tabbed CodeMirror, path autocomplete (Tab), Ctrl+S saves via PUT /api/file.
- Mobile: collapsible sidebar.

## Code quality
- Graceful degradation: Ollama down → fallback API → cached → error message.
- I/O-bound calls wrapped in asyncio.to_thread.
- Structured logging via logging.getLogger.

## Output format
1. Brief architecture note (2-3 sentences).
2. Complete file content or unified diff (--- / +++ / @@).
3. Always include error handling and input validation.
4. Then run: python -m py_compile <files>, python test_agent.py (27 tests), commit + push.
