# My OpenCode — Status

## Что сделано (Core)

- [x] FastAPI сервер, SSE streaming, agent loop (12 итераций)
- [x] 28 инструментов: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search, question, skill, patch, task, todo, lsp, testgen, db_query, deps, mcp + 3 плагина
- [x] Prompt-based tool calling
- [x] Streaming tool execution — live-прогресс тулов в UI (SSE события tool/status по мере исполнения)
- [x] Сессии (.agent_sessions/sessions.db — SQLite, авто-миграция из JSON, JSON-fallback)
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
- [x] LSP интеграция (definition, references, hover, symbols, rename, completion)
- [x] Управление моделями (+Pull/-Del с прогрессом)
- [x] WebSearch (DuckDuckGo)
- [x] Async rewrite (все blocking-вызовы через asyncio.to_thread)
- [x] CI/CD
- [x] 27 smoke-тестов (включая интеграционные с мок-моделью, SQLite-сессии, patch line-aware, bash-фильтр, thread-safety)
- [x] Mobile-responsive sidebar
- [x] Desktop App (pywebview)
- [x] Плагины (.agent_plugins/)
- [x] Action audit (.agent_audit.log)
- [x] MCP-клиенты (mcp_servers.json + инструмент mcp)
- [x] Автодополнение без LSP (fallback по токенам файла + keywords)
- [x] requirements.txt (зависимости проекта)

## Редактор (добавлено по оценке Kimi)
- [x] CodeMirror: вкладки, подсветка, folding, Ctrl+S сохранение, Ctrl+Space автодополнение (LSP)
- [x] Автодополнение в чате (@файлы, #скиллы, /команды)
- [x] История сообщений (↑/↓)
- [x] testgen — генерация unit-тестов (Python, JS/TS)
- [x] db_query — SQL запросы к SQLite
- [x] deps — анализ зависимостей (pip/npm/go/cargo/pipenv)
- [x] Swagger UI (/docs)
- [x] Интерактивный терминал (SSE, история, Ctrl+C kill)

## Безопасность
- [x] Directory traversal protection (read/write/edit/patch вне WORK_DIR заблокированы)
- [x] Bash sandbox (чёрный список + нормализация пробелов/кавычек + вложенные интерпретаторы bash -c / cmd /c / powershell -c)
- [x] Retry с exponential backoff
- [x] Path validation
- [x] Thread-safety: лок на LLM-кеш, todo-список, RAG-индекс (RLock)

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
- [x] Swagger /docs

## Найденные баги при live-проверке кодинга (2026-07-31)

### Исправлены
- [x] `/api/chat` игнорировал выбранную модель: `req.model` не передавался в `run_agent_loop` → всегда работал дефолт. Добавлен параметр `model=None` (agent.py:272, 711)
- [x] Итерация 1 всегда шла через PLANNER_MODEL (deepseek-r1:1.5b), которая НЕ следует tool-формату (выдаёт python-код/фриформат) → цикл обрывался на старте без единого вызова инструмента. Фикс: если итерация 0 (planner) не дала tool-блоков — retry с основной моделью (agent.py:367)
- [x] Модели иногда выдают tool-блоки в yaml-стиле (`tool write\npath "demo.py"\ncontent "..."`), парсер JSON их игнорировал. Добавлен `yaml_tool_pat` fallback-парсер (agent.py:321)

### Не исправлены (критично для кодинга)
- [x] **Подтверждение "yes" не завершало цикл** — ИСПРАВЛЕНО: отложенный tool хранится в `_PENDING_CONFIRM` (session_id → name/args), при "yes" авто-выполняется БЕЗ вызова модели (agent.py:311). Live-проверено: write → CONFIRM → yes → файл создан → verify
- [ ] **deepseek-r1:7b нестабилен в tool-формате**: иногда выдаёт фриформат (`tool block\n define add function`) вместо JSON → лучше рекомендовать qwen2.5-coder:7b как основную модель для кодинга (проверено: стабильные блоки), либо расширить yaml-парсер

## Тесты — сделать
- [x] `test_confirm_yes_autoexec`: write → [CONFIRM] → "yes" → tool выполнен без вызова модели (сделан)
- [x] `test_agent_loop_model_param`: model из запроса доходит до call_ollama, planner пропущен (сделан)
- [x] `test_agent_loop_yaml_style_tool`: yaml-блоки парсятся и выполняются (сделан)
- [x] `test_agent_loop_planner_fallback`: planner без tool-блоков → retry с основной моделью (сделан)
- [x] Live-проверка полного цикла: задача → write (CONFIRM) → "yes" → файл создан → verify (пройдена)

## По оценкам Kimi (7.8) — что осталось

### P0 (критично) — все сделаны
- [x] patch / _apply_diff — переписан на line-aware unified diff parser (был сломан: игнорировал @@, собирал + строки в кучу)
- [x] Bash sandbox — нормализация + рекурсивная проверка вложенных интерпретаторов (blacklist усилен; полный whitelist см. P1)
- [x] Threading.Lock на TODO_LIST, LLM_CACHE, RAG-глобалы

### P1 (важно) — сделать следующими
- [ ] stream=True в call_ollama — парсинг tool blocks «на лету» (сейчас агент ждёт полный ответ модели, десятки секунд тишины в UI)
- [ ] RAG-индексация в фоновом потоке (сейчас запрос к /api/embed блокирует поток запроса)
- [x] Pydantic-модели для аргументов каждого инструмента — сделано расширение validate_tool: типы (str/int), диапазоны (top_k 1-50, max_results 1-20), enum-ы (task.agent, todo.action, lsp.operation, mcp.server/_list)
- [ ] Bash whitelist или shlex.split + валидация аргументов (чёрный список обходится: `rm -rf /tmp/..`, обфускация)
- [x] ensure_safe_path: проверка симлинков до resolve() — уже заблокировано: resolve() раскрывает симлинк, итог проверяется в пределах WORK_DIR (test_symlink_safe_path)

### P2 (улучшение)
- [ ] Graceful cancellation: проверка флага отмены внутри agent loop (сейчас abort ловит только следующий fetch)
- [ ] CodeMirror 6 / Monaco (если готов пожертвовать zero-dep)
- [ ] AST-based multi-file edit (parso для Python, tree-sitter для остального)
- [ ] xterm.js терминал (сейчас свой SSE-терминал — работает, но xterm.js даст полный эмулятор)

## По оценкам DeepSeek (9/10) — что осталось

### P1 (важно)
- [ ] Оптимизация RAG: память (сейчас все чанки в ОЗУ) + FAISS или аналог для эффективного поиска
- [ ] Чанкинг RAG: по размеру (~500 симв.) с перекрытием вместо только def/class-границ (не универсально для всех языков)

### P2 (улучшение)
- [ ] Конкретные типы исключений вместо широких except Exception + лучше логирование
- [ ] Разбить длинные функции в agent.py/tools.py, добавить docstring и тайп-хинты
- [ ] Вынести JS из ui.py в отдельный модуль/файл
- [ ] LSP: поддержка большего числа языков (Rust, C++)
- [ ] Docker-изоляция bash (строгая песочница)

## Собственные идеи (низкий приоритет)
- [ ] Native tool calling (когда Ollama поддержит)
- [ ] Desktop App (Tauri — pywebview уже работает)
- [ ] GPU embeddings (Ollama уже на GPU — фактически не требуется)
- [ ] deepseek-coder-v2:16b — пулл (для стабильного кодинга на 12GB)
- [ ] Полнотекстовый поиск по сессиям в UI
