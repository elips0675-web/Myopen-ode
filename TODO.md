# My OpenCode — Status

## Что сделано (Core) — 83/83 тестов
- [x] FastAPI + SSE, agent loop (12 итераций, таймаут, cancel), prompt-based tool calling, стриминг тулов в UI
- [x] 27 инструментов (read/write/edit/bash/glob/grep/list/web/websearch/diff/commit/undo/verify/plan/search/question/skill/patch/task/todo/lsp/testgen/db_query/deps/mcp/snapshot/restore + плагины)
- [x] Сессии SQLite (+миграция из JSON), multi-project, RAG (BM25+эмбеддинги, FAISS/numpy, RAG_MAX_CHUNKS, фоновая индексация), LLM кеш TTL, memory, skills, subagents, slash-команды, MCP сервер+клиенты, LSP (18 серверов), CodeMirror + терминал SSE, pywebview desktop, плагины, audit log
- [x] Безопасность: whitelist bash (не blacklist) + рекурсивная проверка python -c/node -e + запрет `..`-обхода; Docker-песочница (BASH_DOCKER=1, opt-in, fallback); path jail через resolve() (symlink-safe); подтверждение деструктивных операций; блок абсурдных путей; anti-loop; graceful cancellation
- [x] Промпт: правила 1-21 + EXAMPLES + VALID/INVALID (few-shot), code detector, tool-error nudge, lenient JSON (_parse_tool_json), live streaming (первый токен ~2.6s), статистика тулов (TOOL_STATS + /api/stats), Cache-Control static, регрессионный гард промпта (test_system_prompt_rules)
- [x] Спринт (2026-08-07): per-session tool-errors → advice в динамический контекст; модель-роутер (2+ пустые итерации → fallback на основную); RAG_STATUS + /api/rag/status + индикатор в UI; /api/audit + просмотр лога в UI; CLI python -m myopencode; crash recovery (checkpoint каждые 2 итерации + interrupted-маркер)

## Оценки внешних ревьюверов (2026-08)
Kimi 2: 8.3/10 → DeepSeek 2: 8.5/10 → DeepSeek 3: 8.6/10 → Kimi 3: 8.7/10 → Внешний: 8.8/10 → DeepSeek 4: 8.9/10
Путь к 9/10: рефакторинг монолитов ✓, динамический контекст ✓, few-shot при ошибках ✓, USER_GUIDE.md ✓
Путь к 9.5/10: xterm.js+WS ✓, интеграционные тесты ✓, RAG-сегментация по папкам ✓, CLI-режим ✓ (этапы 8–9)
Следующая цель (10/10): native tool calling ✓, Tauri-десктоп ✓ (этап 20), GPU embeddings ✓ (не требуется), deepseek-coder-v2:16b ✓

## ДОДЕЛАТЬ — сводка по всем оценкам (приоритет по консенсусу ревьюверов)

### Этап 1. Динамический контекст в промпте (DS3 №1, Kimi3 P1) — СДЕЛАНО
- [x] Перед каждым вызовом модели: «You are working in project: X (iteration N) / Last action: {tool} (result: ok|error)» (_dynamic_context, agent.py); тесты test_dynamic_context, test_dynamic_context_error_status

### Этап 2. Промпт-усиления + bare-парсер (DS3) — СДЕЛАНО
- [x] Правило 20: «tools ONLY inside ```tool blocks, иначе IGNORED» + примеры VALID/INVALID (negative examples) в конце промпта
- [x] Правило 21: «On the first turn, READ at least one file before writing/editing»
- [x] Retry с температурой 0.1 после сбоя Ollama (attempt>0 → temp 0.1, stream+non-stream)
- [x] Bare-парсер: регулярка {"tool":"..."} в любом контексте уже была (bare_tool_pat) — покрыта; @tool/`// tool:` маркеры — не требуются (модель пишет JSON)
- [x] Per-session TOOL_STATS: «Tool errors this session» (до 3 тулов) + advice «use glob or list to find the real path» в _dynamic_context (test_sess_stats_advice)

### Этап 3. Few-shot при ошибке тула (DS2, DS3 №5, Kimi3 P1) — СДЕЛАНО
- [x] Вместо голого nudge — конкретный пример исправления (tried → error → corrected tool: glob → read → edit); test_tool_error_fewshot; live-подтверждение в test_live.py

### Этап 4. Инфраструктура (быстрые победы) — СДЕЛАНО
- [x] /health эндпоинт (status, model, planner, workspace, sessions, rag_chunks, uptime); test_health_endpoint
- [x] Docker: BASH_DOCKER_READONLY=1 (read-only mount), BASH_DOCKER_MEM/--memory-swap/--user; test_bash_docker_flags
- [x] UI: индикатор «модель думает» до первого токена (уже был); RAG-статус (chunks / индекс-прогресс, poll 5s); кнопка 📋 просмотра .agent_audit.log (/api/audit)

### Этап 5. Интеграционные тесты с реальной моделью (DS3 №2, Kimi3 P2) — СДЕЛАНО
- [x] test_live.py: «создай hello.py с функцией greet» (10.8s, прошёл live 2/2) + простой вопрос; skip без Ollama; python test_live.py [--full]

### Этап 6. Документация (Kimi3 P1) — СДЕЛАНО
- [x] USER_GUIDE.md: установка, первый запуск, как задавать задачи, настройка, troubleshooting, скиллы/плагины
- [x] Troubleshooting в USER_GUIDE.md («модель не отвечает», «тулы не работают», «Ollama не видит GPU»)

### Этап 7. Рефакторинг монолитов (Kimi3 P1) — СДЕЛАНО (2026-08-07)
- [x] core/agent_loop.py — цикл LLM→parse→execute→feedback + _dynamic_context + summarize_context (зависимости инжектятся через deps-модуль; deps=None → import agent)
- [x] core/tool_parser.py — ```tool/bare/yaml парсеры + lenient JSON + _strip_system_markers + extract_pending_tool
- [x] core/tool_executor.py — dispatch одного тула: anti-repeat, алиасы, validate_tool, question/plan/confirm-ветки, _sess_record
- [x] core/safety/bash_guard.py — BASH_BLACKLIST/ALLOWED/NO_DOTDOT + check_bash(cmd, work_dir) + docker_bash()
- [x] core/safety/path_guard.py — resolve/ensure_safe_path/similar_files (path jail)
- [x] agent.py (~1180 → ~790 строк) — HTTP-роутинг + сессии + pending/cancel + проекты, реэкспорты для совместимости; tools.py — инструменты + обёртки (check_bash/resolve/ensure_safe_path с WORK_DIR)
- [x] Поведение 1-в-1: 69/69 тестов + live CLI («4») без изменений

### Этап 8. xterm.js + WebSocket (DS2 P2, DS3 №3, Kimi3 P2) — СДЕЛАНО (2026-08-07)
- [x] core/pty_shell.py — интерактивный шелл: POSIX настоящий PTY (pty.fork + TIOCSWINSZ resize), Windows pipes-fallback (cmd/python -u -i/powershell); API feed/read_available/resize/kill
- [x] WebSocket /ws/term в agent.py — cmd/input/resize/kill JSON-сообщения, потоковый out-фан-аут, exit-код, auto-kill при disconnect
- [x] xterm.js 5.3.0 vendored в static/vendor/ (+whitelist-роут /static/vendor/{fname}, Cache-Control 3600)
- [x] UI: панель терминала на xterm (настоящий терминал вместо pre-вывода): запуск шелла/команды, Ctrl+C, New shell / Kill / Clear, resize → TIOCSWINSZ, история команд
- [x] Требование: websockets>=12.0 добавлено в requirements.txt
- [x] Тесты: test_pty_shell (интерактивный I/O python -u -i), test_ws_terminal (TestClient WS); live: python -i через WS → «>>> 42»
- [x] SSE-эндпоинты /api/terminal(+kill) оставлены для совместимости

### Этап 9. Средние фичи (P2, по оценкам) — СДЕЛАНО (2026-08-07)
- [x] CLI-режим без UI (python -m myopencode "задача"; NO_CONFIRM=1; test_cli_main; live: «what is 2+2?» → «4»)
- [x] Восстановление сессии после падения сервера: state-файл на время цикла, checkpoint каждые 2 итерации, «⚠ interrupted» в списке сессий, маркер-резюме при возобновлении (test_session_checkpoint)
- [x] Модель-роутер: при 2+ итерациях без tool-блоков авто-переключение на основную модель (метрика: % tool-blocks; test_model_router)
- [x] RAG-сегментация по папкам: rag_search(scope=) — поиск только по top-level папке (core/, tools/...); тул search: {"scope": ...}; test_rag_folder_scope
- [x] Восстановление после сбоев: перезапуск без потери контекста (checkpoint + interrupted-маркер)
- [x] RAG source attribution: [file:line] в каждом чанке вывода rag_search
- [x] JSON Schema constrained output: Ollama format:TOOL_JSON_SCHEMA (экспериментально) — set_json_mode() thread-local, включается циклом после format/tool-error/code-нуджей, AI_JSON_FORMAT=1 глобально (test_json_schema_format)
- [x] Тесты кроссплатформенности: CI-матрица .github/workflows/tests.yml (ubuntu/windows/macos), pathlib-пути, CREATE_NO_WINDOW-guard (test_cross_platform)
- [x] Автопроверка новых версий: GET /api/update (HEAD vs origin/master, кэш 1ч, офлайн-safe) + бейдж «⬆ update N» в UI (test_update_check)
- [x] Мульти-агентное иерархическое планирование: тул task запускает сабагента С собственным tool-циклом (run_agent_loop, NO_CONFIRM, fallback на одиночный вызов) (test_task_subagent_loop)
- [x] Git pre-backup перед batch-операциями + «restore all»: авто-snapshot перед первым мутирующим тулом (git diff --binary + untracked-копии), тулы snapshot/restore (test_git_snapshot_restore)
- [x] Inline diff preview перед edit: SSE-событие 'diff' → цветной блок в чате (Cursor-style) (test_diff_preview)
- [x] Vendor CodeMirror 5 в static/vendor/cm/ + StaticFiles mount; /static/vendor/{fname} whitelist; UI полностью офлайн (test_vendor_static)
- [x] Полноценный MCP client: initialize→notifications/initialized хендшейк, capabilities, resources/list|read, prompts/list|get, tools/list/call (test_mcp_client)

## Найденные баги при live-проверке кодинга (2026-07-31) — исправлены
- [x] /api/chat игнорировал выбранную модель (req.model не доходил) — добавлен параметр model
- [x] Итерация 1 всегда шла через PLANNER_MODEL (deepseek-r1:1.5b не следует tool-формату) — retry с основной моделью при отсутствии tool-блоков
- [x] YAML-стиль tool-блоков (`tool write\npath "demo.py"`) не парсился — добавлен yaml_tool_pat
- [x] «yes» после [CONFIRM] не выполнял отложенный тул — _PENDING_CONFIRM + авто-выполнение без вызова модели
- [x] Зацикливание на question/тул-спам — анти-loop, _strip_system_markers, короткие сообщения минуют планировщик
- [x] «Долгое думание» 60+ сек — num_ctx 16384 (8x быстрее), num_predict 2048, AGENT_TIMEOUT 300
- [x] RAG search падал (относительные импорты) — исправлены на абсолютные
- [x] read/edit «not found» без подсказки — _similar_files (похожие файлы)
- [x] Потеря tool-событий в SSE при завершении — 2s grace-drain
- [x] deepseek-r1:7b нестабилен в tool-формате — дефолт qwen2.5-coder:7b (проверено live)

## Live-проверки агента-программиста (2026-08-05)
- [x] Полный цикл: задача → write (CONFIRM) → yes → файл создан → verify (пройдена)
- [x] «Кто ты?» — прямой ответ за 3.6s, без тул-спама и фейковых маркеров (пройдена)
- [x] /api/sessions/search — сессия со сниппетом (пройдена)
- [x] Стриминг: первый текст ~2.6s, итог 8.8s (пройден)
- [x] /api/stats, Cache-Control на /static/app.js (проверены)

## Этап 13. Мультимодельный live-набор (2026-08-08) — СДЕЛАНО
- [x] test_live.py: сценарии create/edit/question прогоняются на всех установленных моделях (qwen2.5-coder:7b, qwen3:8b, deepseek-coder-v2:16b); параметры --models/--full; warm-up каждой модели
- [x] Результаты честные: qwen3:8b (native) сильнейшая ~3/3, qwen2.5-coder:7b ~2/3 (edit-rename даёт инструкции), deepseek-coder-v2:16b ~0-1/3 (слабый исполнитель, битые блоки) — стохастика между прогонами из-за VRAM-вытеснения
- [x] Дизайн-фикс: роутер больше НЕ переключает юзер-выбранную модель (test_model_router: never routed); ветка роутера удалена (мёртвая), planner-retry сохранён (test_agent_loop_planner_fallback)
- [x] Пустой ответ модели → retry один раз перед break («No response from model» на 16b из-за вытеснения VRAM)
- [x] 83/83 mock-тестов, live-набор параметризован

## Этап 14. Рефакторинг монолита tools.py (2026-08-08) — СДЕЛАНО
- [x] tools.py (1352 строки) → пакет tools/: _state.py (конфиг+глобалы+init_config с синхронизацией копий подмодулей через _sync_register), paths.py, backup.py (backup/undo/git/verify/git_prebackup/restore), plugins.py, llm.py (Ollama+stream+native+fallback), audit.py, exec.py (validate/execute/diff/bash-обёртки), __init__.py (фасад: реэкспорт + SYSTEM_PROMPT/SUBAGENT_PROMPTS)
- [x] Фасад сохраняет API: from tools import ... и tools.X (включая tools.requests.post для моков, private-хелперы для тестов)
- [x] init_config теперь синхронизирует копии глобалов во всех подмодулях (WORK_DIR/BASH_TIMEOUT/...); SUBAGENT_PROMPTS в exec.py — ленивый доступ через tools (цикл импортов)
- [x] Обновлён test_git_snapshot_restore: tools.WORK_DIR = x → tools.init_config(WORK_DIR=x) (прямое присваивание атрибута пакета больше не синхронизирует подмодули)
- [x] 83/83 тестов, CLI live («4»), сервер перезапущен на новой структуре (/health 200)

## Этап 15. Разбивка _execute_tool_inner (2026-08-08) — СДЕЛАНО
- [x] 366-строчный _execute_tool_inner → _TOOL_DISPATCH: 26 хелперов _tool_* (read/web, write, edit, bash, glob, grep, list, diff, commit, undo, verify, search, snapshot, restore, websearch, question, skill, patch, task, todo, lsp, testgen, db_query, deps, mcp) + fallback на плагины
- [x] Поведение идентично (побайтовый перенос веток); 83/83 тестов, CLI live «4»
- Предел (поведение модели, не кода): полный цикл «исправь баг + прогони тесты» требует follow-up «yes» на CONFIRM (bash) — по дизайну

## Этап 16. Вынос роутов из agent.py (2026-08-08) — СДЕЛАНО
- [x] agent.py (883 стр.) → api_sessions.py (CRUD/поиск/экспорт/импорт сессий), api_files.py (файл-браузер/редактор/upload), api_misc.py (stats/health/update/models/projects/task/plugins/skills/terminal/ws/lsp); в agent.py остались app, /, static, /api/chat(+cancel), сессии-хранилище, память, проекты, pending/cancel state (~470 стр.)
- [x] include_router в конце agent.py; вычищены осиротевшие импорты (subprocess/WebSocket/glob)
- [x] `python agent.py` (запуск как __main__) — модуль регистрируется в sys.modules как «agent» (иначе роутеры импортируют свежую копию → циклический ImportError); проверено реальным стартом сервера
- [x] Мутируемые глобалы (WORK_DIR/SESSIONS_DIR после switch_project) в роутерах — динамически через import agent as _agent (копия-на-импорт устаревала бы)
- [x] Тесты health/update_check/session_search перенесены на api_misc/api_sessions; 83/83, CLI live, сервер перезапущен на новой структуре (/health 200)

## Этап 17. TOOL_STATS в system prompt (2026-08-08) — СДЕЛАНО
- [x] _dynamic_context: блок «Global tool stats (all sessions)» — топ-3 тула с повторяющимися ошибками (>=2 вызовов, сортировка по числу ошибок) + advice (use glob or list); одиночные сбои не мусорят контекст
- [x] Ленивое резолвление TOOL_STATS через import tools (CLI/тесты не передают); параметр tool_stats= для чистых unit-тестов
- [x] Per-session блок «Tool errors this session» сохранён; тест test_dynamic_context_global_stats (в т.ч. исключение одиночных сбоев); 84/84, CLI live

## Этап 18. AST syntax guard + multi-file patch (2026-08-08) — СДЕЛАНО
- [x] _syntax_check() в tools/exec.py: .py — ast.parse (stdlib, номер строки ошибки), .json — json.loads, .js/.mjs/.ts — node --check (если node есть); прочие расширения пропускаются (None); результат «Syntax: OK/ERROR» добавляется в ответы write/edit/patch — модель сразу видит битый код и исправляет без ручного прогона
- [x] patch: режим files=[{path, diff}, ...] — несколько файлов одним вызовом (порядок, backup+verify+syntax на каждый, ошибки не прерывают остальные); legacy path+diff сохранён
- [x] validate_tool: при files-вызове required path/diff не обязательны; каждый diff валидируется (no hunk headers / shape), ошибка по файлу
- [x] Тесты: test_syntax_guard_write (OK/ERROR py+json, edit-правка ломающая синтаксис), test_patch_multi_file (2 файла, валидация files, per-file mismatch); 86/86, CLI live, сервер перезапущен

## Этап 19. CodeMirror 6 (2026-08-08) — СДЕЛАНО
- [x] Сборка офлайн-бандла esbuild (IIFE, 601KB) → static/vendor/cm6.bundle.js: codemirror@6 + lang-python/js/json/html + theme-one-dark + autocomplete; 15 CM5-скриптов в ui.py → один тег, CM_READY = typeof cm6
- [x] app.js: makeEditor → EditorView (basicSetup+oneDark+foldGutter+Ctrl-S+autocompletion override → /api/lsp/completion, 0-based line); renderEditor → dispatch правки; saveFile → state.doc.toString(); старый кастомный completion-попап удалён
- [x] Whitelist /static/vendor/ + cm6.bundle.js; RAG-флак устранён: static/vendor в SKIP_PARTS (616KB-бандл попадал в индекс)
- [x] Тесты: test_vendor_static + cm6.bundle.js; 86/86 ×2 прогона, CLI live, сервер перезапущен (index без CM5-тегов, /static/vendor/cm6.bundle.js 200)

## Этап 20. Tauri desktop (2026-08-08) — СДЕЛАНО
- [x] Установлены Rust 1.97.1 (winget Rustup.Rustup) + MSVC Build Tools (winget Microsoft.VisualStudio.2022.BuildTools, override VCTools + VC.Tools.x86.x64 --includeRecommended); rustc/cargo/cl.exe проверены
- [x] src-tauri/ (cargo-only): main.rs — reuse сервера на :8765 (иначе spawn `python -X utf8 agent.py`, poll 0.5s×240, env MYOPENCODE_PORT/MYOPENCODE_PYTHON) → tauri::Builder → окно WebView2 1280×860 (center, min 800×600), иконка icons/icon.ico (копия assets), devUrl http://127.0.0.1:8765 (живой UI, как desktop.py); bundle inactive (frontendDist — заглушка, фронтенд отдаёт сервер)
- [x] Сборка cargo build 2m16s → target/debug/myopencode.exe; запуск окна подтверждён (3 WebView2-процесса, процесс жив); scripts/run_tauri.bat — сборка при первом запуске + инструкция установки тулчейна
- [x] Pywebview сохранён как fallback (desktop.py не тронут); USER_GUIDE — таблица двух способов запуска
- [x] 86/86, CLI live («21»), сервер перезапущен (/health 200); KIMI P2 закрыт (Tauri ✓)

## План до 9.5/10 (оценки 8.8–8.9, 2026-08-08)
### P1 (критично для production)
- [x] AST-based edit guard — уникальность/fuzzy-совпадение old text (warning «found N times») — Этап 21
- [x] Git-auto-branch — сессия = ветка, write/edit/patch = auto-commit, undo = git reset — Этап 22 (GIT_AUTO_COMMIT/GIT_AUTO_BRANCH)
- [x] Prompt KV-cache — compressed system prompt после 3-й итерации — Этап 23 (COMPACT_SYSTEM_PROMPT)
- [x] AUTO_CONFIRM_SAFE=1 — автоподтверждение безопасных write/edit (DS4) — Этап 24 (только new-file write)
- [x] qwen3:8b дефолт при >10GB VRAM (проверка через ollama ps) (DS4) — Этап 25 (автопик при старте; явный AI_MODEL побеждает)
- [x] Docker-песочница по умолчанию при наличии Docker + предупреждение в логе (DS4) — Этап 26 (автодетект docker version при старте + лог-совет; DOCKER_SANDBOX=1 синоним BASH_DOCKER=1; =0 отключает; локальный shell не заменяется автоматически)
### P2
- [x] Tauri desktop ✓ (этап 20)
- [ ] Task-level model router — классификатор задачи выбирает модель до цикла
- [ ] Plan tree UI — дерево шагов pending/done/error
- [ ] ARCHITECTURE.md с Mermaid-диаграммой + примеры тулов (DS4)
- [ ] AST-рефакторинг тулы: rename_symbol / extract_function / inline_variable (DS4)
- [ ] VRAM-индикатор и автовыбор модели при старте (DS4)
### P3
- [ ] Self-healing loop — 2 ошибки одним тулом → смена стратегии (edit → read→write)
- [ ] Multi-turn RAG — «RAG over plan»: найти все затронутые файлы → редактировать

## Собственные идеи (низкий приоритет)
- [x] Native tool calling — СДЕЛАНО (Этап 10)
- [x] Desktop App — СДЕЛАНО как Этап 11 (pywebview; Tauri требует Rust/MSVC тулчейн — не установлен)
- [x] GPU embeddings — НЕ ТРЕБУЕТСЯ (Ollama уже работает на GPU: RTX 3060 12GB, qwen3:8b 7.5GB 100% GPU)
- [x] deepseek-coder-v2:16b — пулл завершён (8.9GB, resume после обрыва на 26%); native tool calling НЕ поддерживается (Ollama возвращает 400 при tools= — как qwen2.5-coder), работает legacy-путь; live-кодинг подтверждён: write → CONFIRM → yes → файл создан (8 байт, аудит 1 вызов)

### Этап 10. Native tool calling (Ollama tools=) — СДЕЛАНО (2026-08-07)
- [x] native_chat(): /api/chat с tools=[схемы из TOOL_SCHEMAS], парсинг tool_calls (arguments как dict/строка)
- [x] native_supported(): автодетект по имени модели (default qwen3,llama3.1,gpt-oss; AI_NATIVE_MODELS; отключение AI_NATIVE_TOOLS=0)
- [x] NATIVE_SYSTEM_PROMPT: отдельный промпт БЕЗ legacy-правил ```tool-формата (полный SYSTEM_PROMPT заставляет qwen3 отдавать текст вместо tool_calls — подтверждено probe)
- [x] loop: native-ветка — tool_calls → execute_tool_block (несколько вызовов за ход) → feedback; пустые calls → финальный ответ; сбой → fallback на legacy-парсер
- [x] ВАЖНО: qwen2.5-coder:7b (дефолт) НЕ поддерживает native (отдаёт JSON в контенте) — фича активна только для поддерживающих моделей, legacy-путь не тронут
- [x] live (qwen3:8b): «создай файл и проверь» → native write → [CONFIRM] → yes → write+verify → ответ
- [x] Тесты: test_native_tool_calling (мок native_chat: tool_calls → execute → feedback → answer), test_native_tools_schema; 82/82

### Этап 11. Desktop App (pywebview) — СДЕЛАНО (2026-08-07)
- [x] desktop.py: авто-обнаружение уже запущенного сервера (is_port_open — не стартует второй uvicorn), poll /health до готовности окна (wait_server_ready), reuse вместо double-bind
- [x] Иконка: scripts/make_icon.py генерирует assets/icon.png + icon.ico (PNG/ICO вручную через zlib, без PIL); иконка в заголовке окна
- [x] Окно: 1280x860, min_size 800x600, заголовок «My OpenCode»; fallback: pywebview сломался → браузер; --browser флаг
- [x] Убран блокирующий wait_ollama() перед стартом окна (сервер переживает отсутствие Ollama)
- [x] Тест: test_desktop_helpers (валидность иконок, is_port_open/wait_server_ready на временном http.server); 83/83
