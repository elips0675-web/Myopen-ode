# My OpenCode — Status

## Что сделано (Core)

- [x] FastAPI сервер, SSE streaming, agent loop (12 итераций)
- [x] 22 инструмента: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search, question, skill, patch, task, todo, lsp
- [x] Prompt-based tool calling
- [x] Сессии (.agent_sessions/), экспорт/импорт
- [x] Multi-project (projects.json, переключение из UI)
- [x] UI: файловое дерево, сессии, тёмная тема, drag-and-drop, confirm-диалоги, подсветка синтаксиса, tab completion
- [x] Бэкапы (50 версий), undo
- [x] RAG с дисковым кешем (.rag_cache/)
- [x] Multi-agent (PLANNER_MODEL + MODEL)
- [x] Subagents: @explore (read-only), @scout (web), @general (full)
- [x] Fallback OpenAI/Claude API
- [x] DeepSeek-V4-Flash (1M контекст)
- [x] Skills (.agent_skills/)
- [x] Slash-команды (/test, /deploy, /review, /fix, /doc)
- [x] MCP сервер для IDE интеграции
- [x] Agent memory (.agent_memory/)
- [x] LSP интеграция (definition, references, hover, symbols)
- [x] Управление моделями (+Pull/-Del с прогрессом)
- [x] WebSearch (DuckDuckGo)
- [x] Async rewrite
- [x] CI/CD
- [x] 11 smoke-тестов
- [x] Mobile-responsive sidebar

## Безопасность
- [x] Directory traversal protection
- [x] Bash sandbox (чёрный список)
- [x] Retry с exponential backoff
- [x] Path validation

## Производительность
- [x] eval_count токенов
- [x] Суммаризация каждые 3 итерации
- [x] RAG cache на диск
- [x] Настраиваемые лимиты (AGENT_TIMEOUT, AGENT_MAX_ITER, AGENT_MEMORY_LIMIT)
- [x] Configurable bash timeout

## Документация
- [x] README рус + англ
- [x] Все env vars описаны

## Не сделано (низкий приоритет)
- [ ] Native tool calling (когда Ollama поддержит)
- [ ] Плагины / экосистема расширений
- [ ] Desktop App (Tauri)
