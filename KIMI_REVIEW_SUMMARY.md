# My OpenCode v2 — Сводка для внешнего анализа (Kimi)

Дата: 2026-08-08 · Тесты: **86/86 unit + мультимодельный live-набор (qwen2.5-coder:7b, qwen3:8b, deepseek-coder-v2:16b)** · Сервер: `python agent.py` → http://localhost:8765
Репозиторий: github.com/elips0675-web/Myopen-ode (master, работает локально, Windows, Python 3.14)
История оценок: `Оценка kimi.txt` (7.8/8.7/8.8) и `Оценка deepseek.txt` (8.5/8.6/8.9) — в репо.

## Что это
Локальный ИИ-агент-программист на Ollama (замена Cursor/Windsurf/Claude Code — бесплатно, приватно).
Ключевая особенность: Ollama НЕ имеет нативных tool_calls → модель принуждается промптом выдавать
блоки ```tool {JSON}```, бэкенд парсит/валидирует/выполняет их в цикле (prompt-based tool calling).
Дефолтная модель qwen2.5-coder:7b (deepseek-r1:7b игнорирует tool-формат), num_ctx 16384.

## Архитектура (3 слоя)
HTML/CLI UI --HTTP/SSE--> FastAPI (`agent.py`) --> agent loop (LLM → parse → tool → LLM, max 12 итераций)
--> Ollama 127.0.0.1:11434. Файлы: `agent.py` (сервер: app/роуты чата, state, сессии-хранилище, память,
проекты; ~470 стр.), `api_sessions.py` (CRUD/поиск/экспорт/импорт сессий), `api_files.py`
(файл-браузер/редактор/upload), `api_misc.py` (stats/health/update/models/projects/terminal/ws/skills),
`tools/` — пакет (`_state.py` — конфиг+глобалы+init_config с синхронизацией копий; `llm.py` —
Ollama/stream/native/fallback; `exec.py` — диспетчер 26 per-tool хендлеров `_tool_*`; `backup.py`,
`plugins.py`, `audit.py`, `paths.py`, `__init__.py` — фасад-реэкспорт; был монолитом tools.py ~1350 стр.),
`rag.py` (гибридный поиск BM25+эмбеддинги, FAISS/numpy), `ui.py` (HTML, ~20KB) + `static/app.js`
(JS, 30KB), `lsp.py`, `mcp_server.py`, `mcp_client.py`, плагины `.agent_plugins/*.py`,
скиллы `.agent_skills/`.

## Оценки внешних ревьюверов
- Kimi: **8.3/10** (оценка 2, 2026-08-05; P1: Docker > рефакторинг монолитов; whitelist bash уже был — ревьювер не увидел)
- DeepSeek: **8.5/10** (оценка 2, 2026-08-05; few-shot = −30-40% галлюцинаций на 7B; Docker №1, xterm.js №2)
- DeepSeek: **8.6/10** (оценка 3, 2026-08-06; приоритеты: динамический контекст > интеграционные тесты > xterm.js > рефакторинг > few-shot на ошибке; +0.5 до 9.1 даст: интеграционные тесты + xterm.js + динамический контекст + восстановление сессии)
- Kimi: **8.7/10** (оценка 3, 2026-08-06; «самый зрелый open-source агент на 7B»; до 9/10: рефакторинг монолитов, динамический контекст, few-shot при ошибках, USER_GUIDE.md; до 9.5/10: xterm.js+WS, живой интеграционный тест, RAG-сегментация, CLI-режим)
- DeepSeek: **8.9/10** (оценка 4, 2026-08-08; «самая зрелая локальная open-source альтернатива Cursor/Claude Code»; до 9.2–9.3: AUTO_CONFIRM_SAFE, qwen3:8b дефолт при 12GB+, Docker по умолчанию; до 9.5: ARCHITECTURE.md+Mermaid, AST-рефакторинг тулы, VRAM-индикатор)
- Внешний ревьювер: **8.8/10** (оценка 4, 2026-08-08; план до 9.5: P1 — AST-based edit guard, git-auto-branch, prompt KV-cache; P2 — task-level router, plan tree UI, Tauri [уже сделан этапом 20]; P3 — self-healing loop, multi-turn RAG)

## Сессия 2026-08-05 (коммиты 2480a59..c2aea27, все запушены)
1. **Живой стриминг**: `stream_ollama()` отдаёт текст по мере генерации → UI печатает с ~2.6s
   (раньше — тишина до конца генерации, 9+s). Финальная выдача не дублируется. Фоллбэк на call_ollama при сбое.
2. **Гарды против галлюцинаций**: блок абсурдных путей (`/path/to`, `/tmp`, `C:\Windows`...) в
   `ensure_safe_path`; правило промпта 16 «never invent paths»; tool-error nudge — после ошибки тула +
   текста модели system-напоминание возвращает модель к исправленному ```tool блоку (макс 2 раза).
3. **RAG оптимизация**: FAISS IndexFlatIP (faiss-cpu 1.15.0) → numpy matmul → pure-Python fallback;
   жёсткий лимит памяти `RAG_MAX_CHUNKS=6000` (env); фоновая реиндексация уже была.
4. **Обработка ошибок**: json.JSONDecodeError/sqlite3.Error/OSError/ValueError в критичных местах
   (парсинг тул-блоков, сессии, git); тайп-хинты в 6 ключевых сигнатурах.
5. **Рефакторинг UI**: JS вынесен в static/app.js (GET /static/app.js, FileResponse).
6. **LSP**: добавлены clangd (C/C++), bash-language-server, css/scss/html + keywords;
   исправлена опечатка CREATE_NO_WINDOW (всплывало окно cmd).

## Сессия 2026-08-06 (коммиты 33833c3, fc10cfb, c80f55d — запушены)
7. **Few-shot промпт**: правила 17–19 (один тул за ответ; финиш — plain text или `[DONE]`, без ```tool;
   код ТОЛЬКО через write/edit) + секция EXAMPLES (read→answer; edit-воркфлоу с многострочным old/new;
   исправление неверного пути). Code detector: проза с `def/class/import/...` без тула → system-nudge
   «не пиши код, используй write tool» (макс 2 раза, затем цикл продолжается).
8. **RAG crash fix**: фоновая индексация падала «inhomogeneous shape (4,)» — `_rebuild_fast_index`
   теперь фильтрует эмбеддинги неверной размерности (лог-варнинг, fallback на пустой индекс).
9. **Docker-песочница bash** (опционально): `BASH_DOCKER=1` → `docker run --rm -i -v WORK_DIR:/workspace
   -w /workspace -e PYTHONUTF8=1 <image> sh -lc "<cmd>"` (image из `BASH_DOCKER_IMAGE`,
   default python:3.12-slim). `check_bash` whitelist применяется ДО запуска; при недоступности docker —
   fallback на локальный shell с warning. На Windows не требует Docker Desktop (только для тех, кто включит).
10. **Статистика тулов**: `TOOL_STATS` (calls/errors per tool) в tools.py + `GET /api/stats`;
    warning в лог при 3+ ошибках одного тула подряд (ранний индикатор «модель передаёт плохие аргументы»).
11. **Lenient парсинг tool-JSON**: `_parse_tool_json()` — эвристики по порядку: plain JSON →
    одинарные кавычки → unquoted keys (`{tool: write}`) → голые значения-идентификаторы →
    truncation по последней `}` (мусор после блока) + trailing comma перед `}`. Подключён к
    tool-block и bare-парсеру.
12. **Cache-Control**: `public, max-age=604800` на /static/app.js (version-hash — при CDN-развёртывании).
13. **Регрессионный гард промпта**: test_system_prompt_rules проверяет правила 16-21 + EXAMPLES + VALID/INVALID.

## Сессия 2026-08-06b — спринт по оценкам 3 (63/63 + 2/2 live)
14. **Динамический контекст** (DS3 №1, Kimi3 P1): перед каждым вызовом модели —
    «You are working in project: X (iteration N) / Last action: {tool} (result: ok|error)»
    (_dynamic_context). 7B теряют контекст через 3-4 итерации.
15. **Промпт**: правило 20 (tools ONLY в ```tool блоках, иначе IGNORED) + примеры VALID/INVALID
    (negative examples); правило 21 (first turn — read перед write/edit).
16. **Retry temp 0.1**: при повторной попытке Ollama-запроса после сбоя (attempt>0) — температура 0.1
    (детерминированный ретрай), stream + non-stream.
17. **Few-shot при ошибке тула** (вместо голого nudge): пример tried → error → corrected
    (glob → read → edit с EXACT-текстом).
18. **/health** эндпоинт (status/model/planner/workspace/sessions/rag_chunks/uptime).
19. **Docker флаги**: BASH_DOCKER_READONLY (`:ro` mount), BASH_DOCKER_MEM/SWAP (лимиты RAM),
    BASH_DOCKER_USER (не-root). 
20. **test_live.py** — интеграционные тесты с реальной qwen2.5-coder:7b: «создай hello.py с greet»
    (10.8s, прошёл) + простой вопрос (0.2s); auto-skip если Ollama выключен. Ловит регрессии
    prompt-формата, которые моки не ловят.
21. **USER_GUIDE.md** — установка, первый запуск, задачи, env-таблица, troubleshooting, скиллы/плагины.

## Сессии 2026-08-06c .. 2026-08-08 — этапы 8–13 (83/83 + live-набор)
22. **Этап 8 (`e3bb4dd`) — crash recovery**: state-файл сессии + «interrupted»-маркер при сбое
    (test_session_checkpoint); восстановление после рестарта сервера.
23. **Этап 9 (`3bc58f4`) — MCP + иерархия**: полный MCP handshake (initialize → notifications/initialized,
    capabilities, resources/list|read, prompts/list|get в mcp_call); тул `task` — сабагент выполняет
    подцикл run_agent_loop (NO_CONFIRM=True, fallback на одиночный вызов).
24. **Этап 10 (`cd3ea06`) — native tool calling**: для qwen3/llama3.1/gpt-oss (Ollama tools=) —
    `native_chat()` с подменой system-промпта (legacy-правила заставляют qwen3 писать текст вместо
    tool_calls — проверено probe); пустые calls → финальный ответ; сбой → fallback на legacy ```tool.
    qwen2.5-coder:7b и deepseek-coder-v2:16b не поддерживают (HTTP 400 на tools=).
25. **Этап 11 (`41c3cd7`) — desktop**: Rust/MSVC нет → Tauri заморожен, вместо него pywebview
    (desktop.py): автозапуск сервера, poll /health до готовности, иконка (icon.png/ico, генератор
    без PIL), флаг --browser, fallback в браузер.
26. **Этап 12 (`577cdff`) — deepseek-coder-v2:16b**: установлен (8.9GB), legacy-only; live-кодинг
    подтверждён (write → CONFIRM → yes → файл создан, аудит фиксирует только выполнившиеся тулы).
27. **Этап 13 (`b0a294b`) — мультимодельный live-набор + роутер-фикс**: test_live.py прогоняет
    create/edit/question по ВСЕМ установленным моделям (warm-up, --models/--full, честный отчёт).
    Результаты: qwen3:8b (native) ~3/3 — сильнейшая; qwen2.5-coder:7b ~2/3; deepseek-coder-v2:16b
    ~0–1/3 (битые ```tool блоки, инструкции вместо действий). Нестабильность между прогонами —
    вытеснение VRAM (12GB). Роутер больше НЕ переключает юзер-выбранную модель (раньше юзер выбрал
    16b, а работала qwen2.5-coder:7b — молча); planner-retry сохранён. Пустой ответ модели —
    один retry перед break.
28. **Этап 14 (`4a5fe21`) — рефакторинг монолита tools.py → пакет tools/**: _state.py (все
    мутабельные глобалы + init_config с _sync_register: копии конфиг-имён в каждом подмодуле
    синхронизируются), paths/backup/plugins/llm/audit/exec, __init__.py — фасад с полным
    реэкспортом API (включая tools.requests для моков тестов и приватные хелперы). Циклы импортов
    решены: BASH_TIMEOUT читается через _state, SUBAGENT_PROMPTS — лениво через `import tools`,
    requests/DDGS — ленивые импорты. Замечание: `tools.WORK_DIR = x` больше не распространяется
    на подмодули — только tools.init_config(WORK_DIR=x) (обновлён test_git_snapshot_restore).
    Проверено: 83/83, CLI live, сервер перезапущен на новой структуре.
29. **Этап 15 (`5fe99eb`) — разбивка _execute_tool_inner (366 стр.)**: диспетчер `_TOOL_DISPATCH`
    из 26 хендлеров `_tool_*` в tools/exec.py (read/web, write, edit, bash, glob, grep, list, diff,
    commit, undo, verify, search, snapshot, restore, websearch, question, skill, patch, task, todo,
    lsp, testgen, db_query, deps, mcp) + fallback на плагины. Поведение побайтово идентично
    (83/83, CLI live). Открытый вопрос: «длинная задача + цепочка тулов» на CONFIRM (bash) —
    follow-up «yes» по дизайну.
30. **Этап 16 (`30fd2c6`) — вынос роутов из agent.py**: добавлены api_sessions.py / api_files.py /
    api_misc.py (APIRouter), в agent.py — include_router в конце + импорты-сироты вычищены.
    Спецслучай: `python agent.py` (а не `import agent`) — __main__ регистрируется в sys.modules
    как `agent` (иначе роутеры импортируют свежую копию модуля → ImportError/цикл). Мутируемые
    глобалы (WORK_DIR/SESSIONS_DIR при switch_project) в роутерах читаются динамически через
    `import agent as _agent` (копия-на-импорт устаревала бы). Тесты health/update_check/
    session_search перенесены на api_misc/api_sessions. 83/83, CLI live, сервер перезапущен.
31. **Этап 17 (`cc60f55`) — TOOL_STATS в system prompt**: `_dynamic_context` получил блок «Global tool
    stats (all sessions)» — топ-3 тула с повторяющимися ошибками (>=2 вызовов, иначе
    одиночный сбой не мусорит контекст), сортировка по числу ошибок, тот же advice
    (use glob or list). Статистика резолвится лениво через `import tools` — CLI/тесты
    ничего не передают; параметр tool_stats= позволяет чистый unit-тест без сети.
    Per-session блок («Tool errors this session») сохранён. 84/84, CLI live.
32. **Этап 18 (`440dfdf`) — AST syntax guard + multi-file patch**: после write/edit/patch —
    `_syntax_check()` (только stdlib: ast для .py с номером строки ошибки,
    json.loads для .json, node --check для .js/.ts если node установлен; прочие
    файлы пропускаются) — модель сразу видит «Syntax: OK/ERROR» и может
    исправить битый код без ручного прогона. Тулу `patch` добавлен режим
    `files=[{path, diff}, ...]` — несколько файлов одним вызовом, порядок
    применения, backup+verify+синтакс-чек на каждый; validate_tool понимает
    files-вызов (required path/diff не обязательны при files) и валидирует
    каждый diff; legacy path+diff не тронут. 86/86, CLI live, сервер
    перезапущен.
33. **Этап 19 (`b12689d`) — CodeMirror 6 вместо CodeMirror 5**: собран офлайн-бандл
    (esbuild, IIFE, 601KB) в `static/vendor/cm6.bundle.js` — codemirror@6 +
    lang-python/lang-javascript/lang-json/lang-html + theme-one-dark +
    autocomplete/lint API; 15 CM5-скриптов из ui.py заменены одним тегом,
    `CM_READY = typeof cm6`. app.js: makeEditor → EditorView (basicSetup +
    oneDark + foldGutter + Ctrl-S keymap + autocompletion), renderEditor →
    dispatch-правки, saveFile → state.doc.toString(), старый кастомный
    completion-попап удалён — Ctrl+Space отдаёт `cm6.autocompletion` с
    override-source на /api/lsp/completion (line = number-1, CM6 0-based).
    Whitelist /static/vendor/ дополнен (cm6.bundle.js); RAG-флак (большой
    JS-бандл попадал в индекс) устранён: `static`/`vendor` добавлены в
    SKIP_PARTS. 86/86 ×2 прогона, CLI live, сервер перезапущен.
34. **Этап 20 — Tauri desktop (WebView2)** (2026-08-08): установлены Rust
    1.97.1 (rustup) + MSVC Build Tools (VCTools workload, winget) — блокер
    снят. Обёртка `src-tauri/` (cargo-only, без npm): main.rs — если
    :8765 закрыт, сам спавнит `python -X utf8 agent.py` (env
    MYOPENCODE_PORT/MYOPENCODE_PYTHON), ждёт готовности (poll 0.5s × 240),
    затем tauri::Builder → окно WebView2 1280×860, иконка из assets/icon.ico,
    URL devUrl http://127.0.0.1:8765 (живой UI агента). Сборка 2m16s,
    `cargo build` (debug, без bundling) → `target/debug/myopencode.exe`;
    запуск окна подтверждён (WebView2-процессы поднялись). Стартер
    `scripts/run_tauri.bat` (сборка при первом запуске + инструкция
    установки тулчейна). Pywebview сохранён как fallback. 86/86, CLI live.
35. **Этап 21 — AST-based edit guard** (2026-08-08): `_edit_old_stats()` в tools/exec.py —
    до применения edit: (1) `old` найден N>1 раз → edit НЕ применяется, ответ модели
    «found N times — ambiguous, make old unique (include surrounding lines)» (раньше
    replace менял ВСЕ вхождения молча — потенциально ломал не то место); (2) `old`
    не найден → fuzzy-подсказка «Closest match: ... (similarity N%)» через
    difflib.SequenceMatcher (>=0.8) — модель видит свою опечатку. Мутации не
    происходит ни в одном из случаев (backup не вызывается). Тесты
    test_edit_guard_ambiguous (2 вхождения → reject, уникальный edit проходит,
    Syntax: OK) и test_edit_guard_fuzzy_hint (опечатка → «Closest match»). 88/88,
    CLI live, сервер перезапущен.
36. **Этап 22 — Git auto-branch / auto-commit** (2026-08-08): opt-in через
    `GIT_AUTO_COMMIT=1` (+`GIT_AUTO_BRANCH=1`): после каждого успешного
    write/edit/patch — `git add <rel> + git commit --no-verify -m "agent: <tool>
    <path>"`, ответ тула получает «git: <hash> committed». GIT_AUTO_BRANCH
    создаёт ветку agent-session-<ts> при первом коммите — история юзера
    (main/master) не трогается; вне git-репо или при сбое — тихий None (бэкапы
    .agent_backups остаются основным undo-механизмом). Найдены и исправлены
    два бага по ходу: (1) rel-путь write/edit считался от устаревшей копии
    WORK_DIR в exec.py — теперь от _s.WORK_DIR.resolve(); (2) git add с
    обратными слэшами в Windows — нормализация "\"→"/". Тест
    test_git_auto_commit (временный репо, ветка agent-session, main нетронут,
    history ≥2 «agent:» коммитов; rmtree с chmod-обработчиком из-за read-only
    .git на Windows). 89/89 ×3, CLI live, сервер перезапущен.

Из рекомендаций оценок 2-3 реализовано: few-shot, [DONE]-маркер, один тул за раз, статистика тулов,
пост-обработка JSON, Docker-песочница, code detector, Cache-Control, динамический контекст,
интеграционные тесты (мультимодельные), xterm.js+WS терминал, RAG-сегментация по папкам,
CLI-режим, восстановление сессии, update check, кроссплатформенные тесты, MCP client,
native tool calling, desktop (pywebview). «Таймаут после [CONFIRM]» — НЕ нужен:
после CONFIRM цикл завершается break по дизайну (юзер пишет «yes» → auto-exec pending без вызова модели).

## Что осталось (P2)
- закрыто: Tauri desktop ✓ (этап 20), JSON Schema constrained output ✓ (AI_JSON_FORMAT=1),
  UI-динамика ✓ (индикатор «думает», RAG-прогресс, audit-просмотр)

## Оценка 4 — 8.8/10 (внешний ревьювер, 2026-08-08)

«Проект — самый зрелый open-source локальный агент на 7B. От 8.8 до 9.5 — не количество фич,
а полировка крайних случаев (fuzzy edit, git-native, prompt cache). Осталось ~3-4 спринта.»

| Ось | Балл | До 9.5 |
|---|---|---|
| Архитектура | 9.0 | DI-контейнер, абстракции для RAG/DB |
| Код/тесты | 9.5 | уже на уровне |
| Безопасность | 8.5 | AST-анализ python/node инъекций, git-auto-branch |
| AI/модели | 8.0 | prompt caching, task-level router, AST edit |
| UX/UI | 8.0 | agentic plan tree, AST multi-file, Tauri ✓ |
| Доки/процесс | 9.0 | уже на уровне |

Сильные стороны (цитаты): рефакторинг монолитов (agent.py 883→470, tools.py→tools/, core/) —
production-grade решения циклических импортов (deps-инъекция, ленивые импорты, sys.modules["agent"]);
«больше инфраструктуры качества, чем у 90% open-source агентов»; 4 интерфейса (CLI/Web/Desktop/MCP)
к одному ядру; ensure_safe_path + symlink-safe resolve; anti-loop + few-shot nudge; lenient JSON
«must-have для 7B, реализован качественно»; Docker-дизайн правильный (opt-in, whitelist+контейнер,
fallback; дефолтом для локального агента не делать); гибрид native vs legacy — «единственно
рациональная стратегия»; AGENTS.md-дисциплина, bilingual README, context.txt — «уровень коммерческого продукта».

Что снижает оценку (и наши ответы):
- **agent.py ~470 стр. с глобалами** — нужен AgentApp-класс/DI. (В работе: спринт по абстракциям.)
- **RAG/LLM-кеш без интерфейсов** — замена FAISS/SQLite потребует правки по дереву.
- **Prompt перегружен** (правила 1-21 + EXAMPLES + VALID/INVALID + контекст + stats) — близко
  к prompt engineering ceiling; рекомендация: структурный prompt (XML-теги) или constrained decoding
  (Ollama format — AI_JSON_FORMAT=1 уже есть, экспериментальный).
- **Нет семантической валидации аргументов** (read path — «looks like a directory» ДО выполнения).
- **Нет fuzzy-маtcher для edit** («old text найден N раз, уточни»).
- **Lenient JSON не ловит unquoted string values** (`{"tool": write, "path": test.py}`).
- **python -c/node -e проверяются рекурсивно только по ключевым словам** — нужен ast.parse.
- **Нет rate limiting на /api/chat** (если порт открыт в LAN — тривиальный DoS).
- **Rollback вне git-репозитория** — сейчас .agent_backups/ + ручной undo; лучше auto-branch.
- **TOOL_STATS** — «корреляция ≠ причинность», лучше мнемоника «You often make errors with: edit
  (wrong old text), read (invented paths)» вместо сырых счётчиков.
- **Нет prompt KV-cache** — правила 1-21 ~2K токенов каждый раз (system как первый message
  кешируется KV-cache Ollama).
- **Роутер только на уровне итераций** — нужен task-level (bugfix→qwen3, refactor→16b, chat→3b).
- **Нет AST-aware multi-file edit** (rename function X в N файлах сам, без exact old/new).
- **Нет agentic plan tree в UI** (чекбоксы pending/done/error, как Cursor Composer).
- **pywebview ~300MB RAM** — Tauri ~50MB (уже сделан, этап 20).

## План до 9.5/10 (по оценке 4) — статус
### P1 (критично для production)
- [ ] **AST-based edit guard** — перед apply: старый текст уникален или fuzzy-совпадает 90%+,
      иначе warning «old text found N times» (уберёт ~50% «edit failed» в live)
- [ ] **Git-auto-branch** — сессия = ветка, write/edit/patch = auto-commit, undo = git reset
      (сейчас .agent_backups/ + ручной undo)
- [ ] **Prompt KV-cache** — compressed system prompt после 3-й итерации (суммаризация правил)
### P2 (отличие от «зрелого прототипа»)
- [x] **Tauri desktop** — этап 20 (`dd45746`), WebView2 ~50MB против ~300MB pywebview
- [ ] **Task-level model router** — классификатор задачи (zero-shot 1.5b) выбирает модель до цикла
- [ ] **Plan tree UI** — визуальное дерево шагов (pending/done/error)
### P3 (10/10)
- [ ] **Self-healing loop** — 2 ошибки одним тулом → агент сам меняет стратегию (edit → read→write)
- [ ] **Multi-turn RAG** — «RAG over plan»: сначала найти все затронутые файлы, потом редактировать

Отметки по оценке: structural prompt (XML-теги) и constrained decoding — заморозка правил 1-21 +
AI_JSON_FORMAT=1 уже частично покрывают; семантическая валидация путей — видит «директорию» на
уровне ФС (аналогичные подсказки), unquoted values — кандидат в lenient-парсер.

## Известные пределы (поведение модели, не кода)
- Полный цикл «исправь баг + прогони тесты» требует follow-up «yes» на [CONFIRM] (деструктивные операции — по дизайну)
- deepseek-r1:7b в UI (если выбрать) галлюцинирует пути и пишет туториалы вместо тулов — дефолт qwen2.5-coder:7b
- 7B-модели иногда пишут JSON-тул в тексте без ```tool-ограждения — bare-парсер + lenient JSON теперь ловит почти всё
- deepseek-coder-v2:16b (legacy-путь) — слабый исполнитель: ~0–1/3 live-сценариев (битые блоки, инструкции вместо действий); qwen3:8b (native) — лучшая из установленных ~3/3
- live-прогоны нестабильны между запусками из-за вытеснения моделей из 12GB VRAM (warm-up сглаживает)

## Вопросы для анализа (что хотим от Kimi)
1. Правильна ли архитектура prompt-based tool calling для 7B-моделей? Что улучшить в system prompt теперь?
2. Достаточны ли анти-галлюцинационные гарды (code detector, lenient JSON, tool-error nudge)? Что ещё реально работает на 7B?
3. Docker-песочница: правильный ли дизайн (opt-in, whitelist + контейнер, fallback)? Стоит ли сделать её режимом по умолчанию или это ок для локального агента?
4. Статистика тулов (TOOL_STATS) — стоит ли встраивать счётчики ошибок в system prompt для самообучения модели?
5. Native tool calling vs legacy ```tool: стоит ли мигрировать legacy-модели или гибрид (qwen3 native, остальные legacy) — правильный выбор?
6. Оценка версии (было 8.7/10): что поднять до «production-ready» (9.5+/10)?
