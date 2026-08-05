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
- [x] 52 smoke-теста (включая интеграционные с мок-моделью, SQLite-сессии, patch line-aware, bash-фильтр, thread-safety, anti-loop, RAG-чанкинг, поиск по сессиям, гарды против тул-спама, tool-error nudge, invented-пути, FAISS fast path, live-сценарии)
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
- [x] **Агент зацикливался на `question` («Кто ты?» → 12 вызовов вопроса с опциями)** — ИСПРАВЛЕНО: (1) `question` завершает итерацию сразу после выполнения (результат в msgs + break, ждёт ответ пользователя); (2) anti-loop: одинаковый вызов инструмента дважды подряд блокируется (`[tool: identical call repeated...]` + break), теперь покрывает и битые блоки (missing 'tool' key); (3) при явной переданной модели планировщик (planner-retry) больше не вмешивается. Live-проверено: 1 вопрос + ответ модели. Тесты: test_question_stops_loop, test_repeated_tool_blocked, test_missing_tool_key_stops_loop
- [x] **Модель «долго думала» (60+ сек на «Кто ты?», TIMEOUT-галлюцинации)** — ИСПРАВЛЕНО: (1) num_ctx 32768→16384 — KV-кэш вдвое меньше, модель целиком в GPU: 7→50-60 tok/s (~8x); (2) num_predict 4096→2048; (3) AGENT_TIMEOUT 60→300s; (4) сервер запускается с WORK_DIR=E:\My OpenCode1 (раньше файлы/скиллы искались в пустой E:\My OpenCode — «read file.py not found», «Available: none»); (5) системный промпт: запрет выдумывать инструменты/туториалы, ответ на языке пользователя. Live: «Кто ты?» — 5 сек; write→CONFIRM→yes→файл в правильной папке. Тест: test_timeout_env
- [ ] **deepseek-r1:7b нестабилен в tool-формате**: иногда выдаёт фриформат (`tool block\n define add function`) вместо JSON → лучше рекомендовать qwen2.5-coder:7b как основную модель для кодинга (проверено: стабильные блоки), либо расширить yaml-парсер
- [x] **«Кто ты?» → мусор/тул-спам ([PLAN] 1. step1, Reply 'yes', несуществующий skill, копирование истории)** — ИСПРАВЛЕНО тремя гардами: (1) короткое первое сообщение (<80 симв.) идёт сразу на основную модель, минуя планировщик (planner на чате бесполезен); (2) повторный вызов тула после результата "not found" блокируется антилупом даже при разных аргументах; (3) из текста модели вырезаются фейковые маркеры [PLAN]/[CONFIRM]/[tool:...]/[Format error]/"```tool"/"Reply 'yes'" (_strip_system_markers). Плюс: пустой план (нет реальных шагов) не ломает цикл — подсказка «answer directly». Промпт: правила 11-13 (простые вопросы — один короткий ответ без тулов, без копирования результатов; маркеры не писать; plan только для многошаговых задач). Live: «Кто ты?» — 3.6s, 2 итерации, прямой ответ без мусора. Тесты: test_plan_empty_guard, test_skill_notfound_repeat_blocked, test_model_marker_text_stripped, test_short_question_skips_planner

## Тесты — сделать
- [x] `test_confirm_yes_autoexec`: write → [CONFIRM] → "yes" → tool выполнен без вызова модели (сделан)
- [x] `test_agent_loop_model_param`: model из запроса доходит до call_ollama, planner пропущен (сделан)
- [x] `test_agent_loop_yaml_style_tool`: yaml-блоки парсятся и выполняются (сделан)
- [x] `test_agent_loop_planner_fallback`: planner без tool-блоков → retry с основной моделью (сделан)
- [x] `test_question_stops_loop`: question завершает итерацию после 1-го вызова (сделан)
- [x] `test_repeated_tool_blocked`: одинаковый вызов дважды → блокировка (сделан)
- [x] `test_missing_tool_key_stops_loop`: битые блоки дважды → блокировка (сделан)
- [x] `test_timeout_env`: AGENT_TIMEOUT ограничивает цикл (сделан)
- [x] `test_cancel_flag`: флаг отмены останавливает цикл между итерациями (сделан)
- [x] Live-проверка полного цикла: задача → write (CONFIRM) → "yes" → файл создан → verify (пройдена)
- [x] Live-проверка «Кто ты?»: 1 вопрос, цикл не зацикливается (пройдена)
- [x] Live-проверка /api/sessions/search: сессия найдена со сниппетом (пройдена)
- [x] Live-проверка «Кто ты?» после гардов: прямой ответ за 3.6s, без тул-спама и фейковых маркеров (пройдена)

## Live-тесты агента-программиста на Ollama (2026-08-05)

### Найдено и исправлено
- [x] **RAG search падал всегда: `from .rag import rag_search` (относительный импорт в tools.py:746)** — «Error: attempted relative import with no known parent package» на КАЖДЫЙ вызов search. Исправлены ВСЕ 3 относительных импорта (rag, lsp, mcp_client) на абсолютные. Тест: test_rag_search_via_execute
- [x] **Дефолтная модель deepseek-r1:7b не следует tool-формату** (выдумывала тулы «fix», не читала файлы, галлюцинировала пути) — дефолт AI_MODEL сменён на qwen2.5-coder:7b (стабильный tool-формат, проверено live: 1-й же тул-вызов с правильным путём)
- [x] **read/edit «not found» без подсказки** — модель не знала похожие пути → добавлен `_similar_files` (read+edit): «Error: ... not found. Similar files in workspace: ...» (glob не заходит в dot-папки — переписано на rglob). Тест: test_read_notfound_similar_files
- [x] **Модель edit'ит не прочитав файл** (галлюцинирует old-текст) — правило 15 промпта: read перед edit/write, old копировать ТОЧНО из read
- [x] **Модель описывает bash в тексте вместо тула** — правило 14 усилено: bash ТОЛЬКО через ```tool bash блок
- [x] **Потеря tool-событий в SSE при завершении** — drain после task.done() без grace-периода терял последние события → добавлен 2s grace-drain (agent.py /api/chat gen)
- [x] **Unknown tool без списка** — «Unknown tool 'fix'. Available tools: ...» (tools.py validate_tool + _execute_tool_inner)
- [x] **Тривиальные планы («step1/step2»)** — отклоняются как пустые (agent.py plan-ветка, regex step\s*\d+ / шаг\s*\d+). Тест: test_plan_trivial_steps_guard
- [x] **qwen2.5-coder:7b** live: write→файл создан; edit→замена применена; read→правильный путь с 1-го вызова; тривиальный plan отклонён; «Кто ты?» — 3.6s без тул-спама

### Пределы (поведение модели, не кода)
- Полный цикл «исправь баг + прогони тесты» требует follow-up «yes» на CONFIRM (bash) — модель останавливается на подтверждении по дизайну
- Модель иногда пишет JSON-тулы в тексте без ```tool блока — bare-парсер ловит часть, но не гарантированно

## По оценкам Kimi (7.8) — что осталось

### P0 (критично) — все сделаны
- [x] patch / _apply_diff — переписан на line-aware unified diff parser (был сломан: игнорировал @@, собирал + строки в кучу)
- [x] Bash sandbox — нормализация + рекурсивная проверка вложенных интерпретаторов (blacklist усилен; полный whitelist см. P1)
- [x] Threading.Lock на TODO_LIST, LLM_CACHE, RAG-глобалы

### P1 (важно) — сделать следующими
- [x] stream=True в call_ollama — парсинг tool blocks «на лету» (сейчас агент ждёт полный ответ модели, десятки секунд тишины в UI) — сделано: stream_ollama (tools.py) + text-события {type:"text"} в /api/chat gen() → UI печатает текст по мере генерации (тест: text-события в test_agent_loop_tool_call)
- [x] RAG-индексация в фоновом потоке — сделано: после холодного старта реиндексация изменённых файлов идёт в фоновом потоке (rag._schedule_bg_index), поиск отвечает по текущему индексу; cold start остаётся синхронным (rag.py rag_search)
- [x] Pydantic-модели для аргументов каждого инструмента — сделано расширение validate_tool: типы (str/int), диапазоны (top_k 1-50, max_results 1-20), enum-ы (task.agent, todo.action, lsp.operation, mcp.server/_list)
- [x] Bash whitelist вместо чёрного списка — сделано: whitelist команд (BASH_ALLOWED), рекурсивная проверка вложенных интерпретаторов (добавлены python -c/-m, node -e), запрет `..`-обхода для деструктивных команд (rm/del/cp/mv), разрешены только локальные скрипты проекта (test_bash_filter)
- [x] ensure_safe_path: проверка симлинков до resolve() — уже заблокировано: resolve() раскрывает симлинк, итог проверяется в пределах WORK_DIR (test_symlink_safe_path)

### P2 (улучшение)
- [x] Graceful cancellation: флаг отмены по session_id (`_cancel_set/_cancel_clear/_cancel_pending`), проверка между итерациями цикла, POST /api/chat/cancel — клиент получает `[cancelled]` (test_cancel_flag)
- [x] Конкретные типы исключений вместо широких except Exception — сделано: json.JSONDecodeError / sqlite3.Error / OSError / ValueError / subprocess-ошибки в критичных местах (парсинг тул-блоков, сессии, git, confirm-сканер) + тайп-хинты в 6 ключевых сигнатурах (execute_tool, call_ollama, stream_ollama, run_agent_loop, rag_search, validate_tool); остальные ~70 мест — намеренно оставлены как фоллбэки с log (тотальная замена рискованна)
- [x] Вынести JS из ui.py в отдельный файл — сделано: static/app.js (30KB), GET /static/app.js (FileResponse), ui.py тоньше на 30KB
- [ ] Разбить длинные функции в agent.py/tools.py, добавить docstring (частично: тайп-хинты сделаны, монолиты run_agent_loop/_execute_tool_inner остались)
- [x] LSP: поддержка большего числа языков (Rust, C++) — сделано: добавлены clangd (.c/.h/.cpp/.cc/.cxx/.hpp), bash-language-server (.sh), vscode-css/html-language-server (.css/.scss/.html) + KEYWORDS для всех новых; исправлена опечатка CREATE_NO_WINDOW (окно cmd при старте серверов)
- [ ] Docker-изоляция bash (строгая песочница)
- [ ] CodeMirror 6 / Monaco (если готов пожертвовать zero-dep)
- [ ] AST-based multi-file edit (parso для Python, tree-sitter для остального)
- [ ] xterm.js терминал (сейчас свой SSE-терминал — работает, но xterm.js даст полный эмулятор)

## По оценкам DeepSeek (9/10) — что осталось

### P1 (важно)
- [x] Оптимизация RAG: память (сейчас все чанки в ОЗУ) + FAISS или аналог для эффективного поиска — сделано: FAISS IndexFlatIP при наличии faiss-cpu, иначе numpy-матмул, иначе pure-Python cosine; жёсткий лимит памяти RAG_MAX_CHUNKS (env, default 6000) с усечением; установлены numpy 2.5.1 + faiss-cpu 1.15.0 (test_rag_fast_search)
- [x] Чанкинг RAG: по размеру (~500 симв.) с перекрытием вместо только def/class-границ — сделано: _split_chunk (500 симв., overlap 80) + def/class-границы (rag.py)

### P2 (улучшение)
- [ ] Конкретные типы исключений вместо широких except Exception + лучше логирование — ЧАСТИЧНО: сделано, см. выше
- [ ] Разбить длинные функции в agent.py/tools.py, добавить docstring и тайп-хинты — ЧАСТИЧНО: тайп-хинты в ключевых сигнатурах сделаны
- [ ] Вынести JS из ui.py в отдельный модуль/файл — СДЕЛАНО, см. выше
- [x] LSP: поддержка большего числа языков (Rust, C++) — сделано: добавлены clangd (.c/.h/.cpp/.cc/.cxx/.hpp), bash-language-server (.sh), vscode-css/html-language-server (.css/.scss/.html) + KEYWORDS для всех новых; исправлена опечатка CREATE_NO_WINDOW (окно cmd при старте серверов)
- [x] Docker-изоляция bash (строгая песочница) — сделано: env BASH_DOCKER=1 → docker run --rm -i -v WORK_DIR:/workspace -w /workspace -e PYTHONUTF8=1 <image> sh -lc "<cmd>" (image из BASH_DOCKER_IMAGE, default python:3.12-slim); whitelist check_bash применяется до запуска; при недоступности docker — fallback на локальный shell с warning. Тесты: test_bash_docker_mode, test_bash_docker_fallback

## По оценке DeepSeek 2 (8.5/10, 2026-08-05) — рекомендации
### Промпт (быстрые победы)
- [x] Few-shot примеры в system prompt (read→answer, edit-воркфлоу, исправление неверного пути) + правила 17-19 (один тул за раз; финальный ответ — plain text/[DONE]; код ТОЛЬКО через write/edit)
- [x] Маркер завершения: [DONE] или просто текст без ```tool (правило 18)
- [x] Напоминание «один тул за раз» (правило 17)
- [ ] Few-shot в момент ошибки тула — вставлять корректный пример вместо голого nudge
- [x] Статистика ошибок по тулам — TOOL_STATS (calls/errors per tool) в tools.py + GET /api/stats; warning в логе при 3+ ошибках подряд (test_tool_stats)
- [x] Пост-обработка JSON: _parse_tool_json (эвристики: одинарные кавычки → двойные, unquoted keys, trailing comma перед }, мусор после блока → truncation at last '}') (test_parse_tool_json_lenient)
- [ ] Динамический контекст в промпте: «ты в проекте X, последнее действие Y»
### Инфраструктура
- [ ] xterm.js + WebSocket для долгих процессов (серверы, отладчики) — приоритет №2
- [ ] Интеграционные тесты с реальными запросами (не только мок-моделью)
- [ ] RAG: сегментирование по папкам для больших кодовых баз (6000 чанков ≈ 3 млн символов)
- [ ] CLI-режим без UI (для серверных сред; mcp_server.py уже есть)
- [ ] Восстановление после сбоев: сохранение состояния сессии, перезапуск без потери контекста
- [ ] Тесты кроссплатформенности (Windows/Linux/macOS)
- [ ] Документация для конечного пользователя (установка/настройка/использование)
- [ ] Автопроверка новых версий (update check)
- [ ] Мульти-агентное иерархическое планирование (исследование → реализация → тестирование)
- [x] Cache-Control для static: public, max-age=604800 (без version-hash пока)

## По оценке DeepSeek 3 (8.6/10, 2026-08-06) — рекомендации
Приоритеты ревьювера: 1) динамический контекст, 2) интеграционные тесты, 3) xterm.js, 4) рефакторинг монолитов, 5) few-shot на ошибке тула.
- [ ] Динамический контекст в промпте (ПРИОРИТЕТ №1): «ты в проекте X, последнее действие Y, открыт файл Z» — 7B теряют контекст через 3-4 итерации
- [ ] Интеграционные тесты с реальной моделью: 5-10 сквозных сценариев с qwen2.5-coder:7b (мок-тесты 58/58 не показывают реальное поведение)
- [ ] Усилить bare-парсер: регулярка для {"tool":"[a-z_]+" в любом контексте (не только код-блок); @tool / // tool: как альтернативные маркеры
- [ ] Промпт: правило «tools ONLY inside ```tool blocks, иначе игнорируются» + примеры VALID/INVALID (negative examples)
- [ ] Промпт: «On first turn, you MUST read at least one file before writing/editing»
- [ ] Retry с температурой 0.1 после ошибки тула (сейчас retry есть, но без смены температуры)
- [ ] TOOL_STATS в промпт осторожно: «TOOL STATS (last 5 calls)» + advice-строка; НЕ сырые цифры, НЕ чужие сессии
- [ ] Docker: BASH_DOCKER_READONLY=1 (read-only mount); --memory=512m --memory-swap=1g; --user 1000:1000
- [ ] /health эндпоинт для мониторинга
- [ ] Восстановление сессии после падения сервера (session storage есть, но не используется для восстановления)
- [ ] UI: индикатор «модель думает» до первого токена (~2.6с тишины)
- [ ] UI: прогресс-бар RAG-индексации («индексация: 45/6000 файлов»)
- [ ] UI: просмотр .agent_audit.log (админ-панель аудита)
- [ ] Troubleshooting guide («модель не отвечает», «тулы не работают», «Ollama не видит GPU»)

## По оценке Kimi 3 (8.7/10, 2026-08-06) — рекомендации
Что нужно для 9/10: рефакторинг монолитов (2-3 дня), динамический контекст (2-3 часа), few-shot при ошибках (1 день), USER_GUIDE.md (1 день).
- [ ] Рефакторинг монолитов (P1): core/agent_loop.py (только цикл LLM→parse→execute→feedback), core/tool_parser.py (```tool/yaml/bare/lenient JSON), core/tool_executor.py (dispatch+validation+stats), core/safety/bash_guard.py (whitelist+docker+path), core/safety/path_guard.py (ensure_safe_path+symlink). agent.py — только HTTP-роутинг, tools.py — только инструменты
- [ ] Динамический контекст в промпте (P1, 2-3 часа): перед каждым вызовом — «You are working in project: X / Last action: {tool} on {file} (result: {status}) / Current open files: {tabs}» — +15-20% к точности путей
- [ ] Few-shot при ошибке тула (P1, 1 день): вместо голого nudge — конкретный пример исправления (tried → error → corrected tool)
- [ ] USER_GUIDE.md (P1): Установка → Первый запуск → Как задать задачу → Что делать, если модель зациклилась → Как добавить свой skill
- [ ] xterm.js + WebSocket (P2, критично для кодинга): полноценный PTY для долгих процессов
- [ ] Интеграционный тест с реальной моделью (P2): «создай hello.py с функцией greet» → проверка def greet (ловит регрессии prompt-формата)
Для 9.5/10: xterm.js, интеграционные тесты, RAG-сегментация по папкам (>100k строк), CLI-режим (python -m myopencode "задача")

## Собственные идеи (низкий приоритет)
- [ ] Native tool calling (когда Ollama поддержит)
- [ ] Desktop App (Tauri — pywebview уже работает)
- [ ] GPU embeddings (Ollama уже на GPU — фактически не требуется)
- [ ] deepseek-coder-v2:16b — пулл (для стабильного кодинга на 12GB)
- [x] Полнотекстовый поиск по сессиям — GET /api/sessions/search?q=&limit= (SQLite LIKE + JSON-fallback, сниппеты с контекстом, test_session_search)
### Безопасность (приоритет №1 по Kimi)
- [ ] Docker-изоляция bash — docker run --rm -v $(pwd):/workspace -w /workspace; на Windows требует Docker Desktop (это блокер «production-ready» для команд)
- [x] Whitelist bash вместо blacklist — УЖЕ СДЕЛАНО (BASH_ALLOWED + recursive python -c/-m, node -e, запрет `..`-обхода) — Kimi не видел это в оценке
- [ ] Git pre-backup перед batch-операциями + «restore all» (сейчас .agent_backups есть, restore — частично через undo)
### Надёжность модели
- [ ] Few-shot examples в system prompt (2-3 примера диалога user → tool → result → assistant) — Kimi обещает -30-40% галлюцинаций на 7B
- [x] Cache-Control для /static/app.js — public, max-age=604800 (верш. хэш-версионирование: /static/app.js?v=hash при CDN-развёртывании)
- [x] Code detector: если ответ содержит def/class/import БЕЗ ```tool → system-nudge «Не пиши код, используй write tool» (макс 2 раза, затем цикл продолжается; test_code_detector_nudge)
- [x] Таймаут после [CONFIRM] — НЕ НУЖЕН: после [CONFIRM] цикл завершается break по дизайну (юзер отвечает yes → auto-exec pending); мёртвый код убран
- [ ] JSON Schema constrained output через Ollama format:"json" (экспериментально, {"thought": "...", "tool": {...}})
- [ ] RAG source attribution: модель должна цитировать [file:line] в ответах
- [ ] Модель-роутер: авто-переключение на qwen2.5-coder при галлюцинациях deepseek-r1 (метрика: % tool-blocks)
### UX / инфраструктура
- [ ] Vendor CodeMirror 5 с CDN в static/vendor/ (единственная внешняя зависимость — CDN fallback)
- [ ] StaticFiles mount: app.mount("/static", StaticFiles(directory="static")) вместо ручного FileResponse
- [ ] Inline diff preview перед подтверждением edit (как в Cursor)
- [ ] Полноценный MCP client для внешних инструментов (браузер, БД) — mcp_client.py уже есть

## Собственные идеи (низкий приоритет)
- [ ] Native tool calling (когда Ollama поддержит)
