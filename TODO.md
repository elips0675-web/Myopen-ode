# My OpenCode — Status

## Что сделано (Core)

- [x] FastAPI сервер, SSE streaming, agent loop (12 итераций)
- [x] 25 инструментов: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search, question, skill, patch, task, todo, lsp, testgen, db_query + плагины
- [x] Prompt-based tool calling
- [x] Сессии (.agent_sessions/), экспорт/импорт
- [x] Multi-project (projects.json, переключение из UI)
- [x] UI: файловое дерево, сессии, тёмная тема, drag-and-drop, confirm-диалоги, tab completion
- [x] Бэкапы (50 версий), undo
- [x] RAG: гибридный поиск (BM25 + семантика) с инкрементальным per-file кешем
- [x] LLM кеш с TTL (LLM_CACHE_TTL)
- [x] Multi-agent (PLANNER_MODEL + MODEL)
- [x] Subagents: @explore (read-only), @scout (web), @general (full)
- [x] Fallback OpenAI/Claude API
- [x] DeepSeek-V4-Flash (1M контекст)
- [x] Skills (.agent_skills/)
- [x] Slash-команды (/test, /deploy, /review, /fix, /doc)
- [x] MCP сервер для IDE интеграции
- [x] Agent memory (.agent_memory/)
- [x] LSP интеграция (definition, references, hover, symbols, rename)
- [x] Управление моделями (+Pull/-Del с прогрессом)
- [x] WebSearch (DuckDuckGo)
- [x] Async rewrite
- [x] CI/CD
- [x] 15 smoke-тестов
- [x] Mobile-responsive sidebar
- [x] Desktop App (pywebview)
- [x] Плагины (.agent_plugins/)

## Редактор (добавлено по оценке Kimi 8.8)
- [x] CodeMirror: вкладки, подсветка, folding, Ctrl+S сохранение
- [x] Автодополнение в чате (@файлы, #скиллы, /команды)
- [x] История сообщений (↑/↓)
- [x] testgen — генерация unit-тестов (Python, JS/TS)
- [x] db_query — SQL запросы к SQLite
- [x] Swagger UI (/docs)

## Безопасность
- [x] Directory traversal protection
- [x] Bash sandbox (чёрный список)
- [x] Retry с exponential backoff
- [x] Path validation

## Производительность
- [x] eval_count токенов
- [x] Суммаризация каждые 3 итерации
- [x] Инкрементальный RAG кеш per-file
- [x] Гибридный поиск BM25 + семантика
- [x] LLM кеш TTL
- [x] Настраиваемые лимиты (AGENT_TIMEOUT, AGENT_MAX_ITER, AGENT_MEMORY_LIMIT)
- [x] Configurable bash timeout

## Документация
- [x] README рус + англ
- [x] Все env vars описаны

## Не сделано (низкий приоритет)
- [ ] Native tool calling (когда Ollama поддержит)
- [ ] Desktop App (Tauri — pywebview уже работает)
- [ ] Интерактивный терминал (xterm.js)
- [ ] Docker-изоляция bash
- [ ] Внешние MCP-клиенты
