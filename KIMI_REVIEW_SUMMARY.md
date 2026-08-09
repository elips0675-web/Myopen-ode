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
- Внешний ревьювер: **8.9/10** (оценка 5, 2026-08-08, +0.1 к 8.8; «зона production-ready beta», Tauri закрыл последний крупный P2; план P1/P2/P3 — ВЕСЬ закрыт этапами 21–31: edit guard=21, git-auto-branch=22, KV-cache=23, AUTO_CONFIRM_SAFE=24, авто-модель=25, Docker=26, ARCHITECTURE.md=27, AST-тулы=28, VRAM=29, router=30, plan tree=31; тесты 97/97 (на момент оценки было 86/86); до 9.5 остался P3: self-healing loop, multi-turn RAG, voice input)
- DeepSeek: **8.9/10** (оценка 5, переоценка, 2026-08-08; Stage 20 Tauri закрыл все P2; «production-ready»; P1-план — весь закрыт этапами 21–26, P2 — этапами 27–31; тесты 97/97 на сегодня; до 9.5 остался P3: self-healing loop, multi-turn RAG, voice input [P3 закрыт этапами 32–34, тесты 99/99 — ВЕСЬ план оценок реализован, заявка на переоценку])

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
37. **Этап 23 — Prompt KV-cache (compact system prompt)** (2026-08-08):
    `COMPACT_SYSTEM_PROMPT` в tools/__init__.py (~0.3K токенов против ~2K
    полного RULES-блока: 8 сжатых правил + список тулов, маркеры RULES и
    COMPACT сохранены). В core/agent_loop.py после итерации ≥3 (it>=3) первое
    system-сообщение (msgs[0]) заменяется на компактный промпт — модель уже
    усвоила правила, а фиксированный system-префикс становится короче, что
    позволяет Ollama переиспользовать KV-cache префикса между ходами.
    Предохранитель «COMPACT not in content» — от повторной компакции;
    native-ветка по-прежнему подменяет RULES-сообщение. Тест
    test_compact_prompt_after_iterations (5+ вызовов: полный на ранних,
    компактный на поздних, размер < 50%). 90/90 ×2 + live-набор 4/9
    (обычная стохастика: qwen2.5 2/3, qwen3 2/3, 16b 0/3), CLI live,
    сервер перезапущен.
38. **Этап 24 — AUTO_CONFIRM_SAFE=1** (2026-08-08): в core/tool_executor.py
    `_auto_confirm_safe(name, tc)` — write в НОВЫЙ файл (не существует) при
    AUTO_CONFIRM_SAFE=1 выполняется сразу, без [CONFIRM] (diff-preview и
    git-prebackup по-прежнему работают); overwrite существующего файла, edit,
    bash, commit, undo — по-прежнему требуют «yes» (NO_CONFIRM остаётся
    all-or-nothing). Тест test_auto_confirm_safe (новый файл → сразу создан
    без CONFIRM; повторная запись → CONFIRM, файл нетронут; env
    восстанавливается). 91/91 ×2, CLI live (write вызван без CONFIRM — модель
    в прогонах давала битые блоки, известный предел 7B), сервер перезапущен.
39. **Этап 25 — авто-выбор модели по VRAM** (2026-08-08): в agent.py
    `_auto_pick_model()` — если AI_MODEL НЕ задан явно: `ollama list`
    содержит qwen3:8b И nvidia-smi >= 10 GB VRAM → дефолт становится
    qwen3:8b (лог «Auto-picked...»); вызов при импорте. `import subprocess`
    вынесен наверх, чтобы тест мог мокать agent_mod.subprocess.run. Тест
    test_auto_pick_model (VRAM>=10GB+установлена → qwen3:8b; малая VRAM →
    дефолт; явный AI_MODEL побеждает). 92/92 ×2, CLI live (qwen3:8b
    ответила через tool verify), сервер перезапущен.
    ВАЖНО-баг 1: автопик сменил тестовую модель на native-совместимую
    qwen3:8b → все loop-тесты (мокают только legacy call_ollama) упали с
    «model never called»/реальными ответами модели; фикс: в __main__
    тест-раннера модель форсится в qwen2.5-coder:7b, если
    native_supported(MODEL). ВАЖНО-баг 2: в .rag_cache было 3 битых файла
    (эмбеддинги dim 2 / dim 0 — мусор прошлых прогонов), а
    _rebuild_fast_index брал dim от ПЕРВОГО эмбеддинга → один битый файл
    ломал весь индекс («RAG search error: »); фикс: dim = max по всем +
    фильтр в _load_file_cache; битые файлы удалены.
40. **Этап 26 — Docker по умолчанию при наличии** (2026-08-08): Docker-
    песочница уже была (docker_bash в core/safety/bash_guard.py, флаг
    BASH_DOCKER=1). Добавлено: (1) флаг DOCKER_SANDBOX=1 как синоним
    (проверка `os.environ.get("BASH_DOCKER") or DOCKER_SANDBOX == "1"`);
    (2) `_detect_docker()` в agent.py при старте — один `docker version`
    (timeout 5s), при успехе лог-предупреждение «set DOCKER_SANDBOX=1»;
    DOCKER_SANDBOX=0 отключает и детект, и песочницу. Безопасная
    интерпретация «default when present»: локальный shell НЕ заменяется
    автоматически (иначе ломаются git/pip/node в python:3.12-slim), но
    docker по умолчанию детектируется и включается одним флагом. Тест
    test_docker_sandbox_flag (мок shutil.which + subprocess.run в
    bash_guard: без флага → None/локально; =1 → docker run; =0 → локально).
    93/93 ×2, сервер перезапущен (docker на машине отсутствует — детект
    молча вернул False).
41. **Этап 28 — AST-рефакторинг тулы** (2026-08-08, P2 #10): в tools/exec.py
    три тула (зарегистрированы в _TOOL_DISPATCH + TOOL_SCHEMAS):
    (1) `rename_symbol` — поиск узлов ast.Name/arg/def/class с ТОЧНЫМ именем,
    замена по позициям с конца (байтовые смещения UTF-8), syntax-проверка
    результата перед записью, backup + git_auto_commit;
    (2) `extract_function` — вырезание строк line_start..line_end в новую
    функцию (params/call_args задаёт модель явно), диапазон заменяется
    вызовом, функция в конец файла;
    (3) `inline_variable` — top-level `var = expr` на line_number: удаление
    строки + замена ПОЗДНИХ вхождений var на текст выражения (ast.Name).
    ВАЖНО (py3.14): col_offset у FunctionDef/ClassDef указывает на 'def'/
    'class', а НЕ на имя → позиция имени ищется line.find() от col_offset;
    end_col_offset у FunctionDef — конец ВСЕГО блока (не имени). Тест
    test_ast_refactor_tools (rename с проверкой отсутствия 'foo' в файле,
    ошибки для не-.py и отсутствующего символа; extract с синтаксисом;
    inline двух использований). 94/94, CLI live:     модель переименовала
    total → sum_total (def sum_total, print(sum_total)) — файл корректен.
    Сервер перезапущен.
42. **Этап 29 — VRAM-индикатор** (2026-08-08, P2 #11): api_misc.py
    `_vram_info()` — nvidia-smi memory.total/used (кэш 10 c, ok=False без
    GPU) → GET /api/vram + поле vram в /health; static/app.js `vramPoll()`
    (15 c) — бейдж «VRAM 7.3/12.0 GB (61%)», фон красный при >90%;
    ui.py бейдж #vram-badge. Тест test_vram_indicator (мок nvidia-smi:
    парсинг 12288/5120 → free 7168; отсутствие → ok=False). 95/95 ×2.
    Live: /api/vram = {total 12288, used 9430, ok:true} — qwen3:8b грузит
    карту. Сервер перезапущен. Остались P2: task-level router, plan tree UI.
43. **Этап 30 — Task-level router** (2026-08-08, P2 #7): tools/llm.py
    `pick_task_model(task, base)` — zero-shot классификатор (один лёгкий
    вызов PLANNER_MODEL, temperature 0: bugfix/refactor/tests/chat/other)
    ВЫБИРАЕТ модель до цикла: bugfix/refactor/tests → qwen3:8b,
    chat → qwen2.5-coder:3b. Правила: явный AI_MODEL всегда побеждает;
    юзер-выбранная модель не трогается (req.model — приоритет); короткие
    запросы (<20 симв.) и «уже qwen3:8b» не классифицируются; целевая
    модель не установлена (кэш /api/tags, TTL 60 с) → дефолт. Подключено
    в /api/chat (chosen_model до run_agent_loop) и CLI (myopencode.py).
    Тест test_task_router (6 сценариев; короткий/недоступная/явный AI_MODEL).
    Баг в тесте: qwen2.5-coder:3b НЕ установлена на машине — ветка chat
    тестируется с подменой списка установленных. 96/96 ×2, CLI live «10»,
    сервер перезапущен. Остался P2: plan tree UI.
44. **Этап 31 — Plan tree UI** (2026-08-08, P2 #8, ПОСЛЕДНИЙ пункт оценок):
    tools/_state.py PLAN_STEPS/PLAN_LOCK; core/tool_executor.py: план-ветка
    сохраняет шаги pending и эмитит {type:"plan", steps}; `_plan_mark(ctx,r)`
    после КАЖДОГО выполненного тула отмечает первый pending как done (или
    error при «Error...») и переэмитит (3 ветки: auto_confirm_safe, yes,
    generic). static/app.js `planTree(steps)` — дерево ✓/✗/○ (pldone/plerr/
    plpend), блок под ответом; ui.py стили .plantree. Тест
    test_plan_tree_events (мок execute_tool: plan → 2 pending + событие;
    read → первый done; write с Error → error; сброс после плана; ctx.state
    требует last_result_name/last_call_key). 97/97 ×2. Live CLI: план с
    [PLAN] 2 шага + «Reply 'yes'» (стохастика шагов модели — механизм
    работает). Сервер перезапущен. **ВСЕ пункты оценок 2–4 закрыты.**

Из рекомендаций оценок 2-3 реализовано: few-shot, [DONE]-маркер, один тул за раз, статистика тулов,
пост-обработка JSON, Docker-песочница, code detector, Cache-Control, динамический контекст,
интеграционные тесты (мультимодельные), xterm.js+WS терминал, RAG-сегментация по папкам,
CLI-режим, восстановление сессии, update check, кроссплатформенные тесты, MCP client,
native tool calling, desktop (pywebview). «Таймаут после [CONFIRM]» — НЕ нужен:
после CONFIRM цикл завершается break по дизайну (юзер пишет «yes» → auto-exec pending без вызова модели).

## Что осталось (P2)
- закрыто: Tauri desktop ✓ (этап 20), JSON Schema constrained output ✓ (AI_JSON_FORMAT=1),
  UI-динамика ✓ (индикатор «думает», RAG-прогресс, audit-просмотр)
- ВСЕ пункты плана до 9.5 (оценка 4) закрыты этапами 21–31 (см. разделы «Оценка 4/5»):
  edit guard=21, git-auto-branch=22, KV-cache=23, AUTO_CONFIRM_SAFE=24, авто-модель=25,
  Docker=26, ARCHITECTURE.md=27, AST-тулы=28, VRAM=29, router=30, plan tree=31.
  До 9.5 остался P3: self-healing loop, multi-turn RAG, voice input. [ЗАКРЫТ этапами 32–34:
  self-healing=32 (2+ ошибки подряд → SWITCH STRATEGY), RAG over plan=33 (план → авто-
  контекст затронутых файлов), voice input=34 (Web Speech API STT в UI); тесты 99/99]
  → ВЕСЬ план оценок 8.3–8.9 реализован; ожидание внешней переоценки 9.5/10.

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
- **agent.py ~470 стр. с глобалами** — нужен AgentApp-класс/DI. (Частично закрыто: core/agent_loop.py
  с deps-инъекцией (этап 7), роуты вынесены в api_* (этап 16); глобалы обновляются через
  import agent as _agent и init_config. Полный DI-контейнер — вне плана 9.5.)
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
- [x] **AST-based edit guard** — перед apply: старый текст уникален или fuzzy-совпадает 90%+,
      иначе warning «old text found N times» (уберёт ~50% «edit failed» в live) — Этап 21
      (`_edit_old_stats` + fuzzy-подсказка, count>1 → отклонение без мутаций)
- [x] **Git-auto-branch** — сессия = ветка, write/edit/patch = auto-commit, undo = git reset
      (сейчас .agent_backups/ + ручной undo) — Этап 22 (GIT_AUTO_COMMIT/GIT_AUTO_BRANCH,
      ветка agent-session-*, auto-commit write/edit/patch, --no-verify)
- [x] **Prompt KV-cache** — compressed system prompt после 3-й итерации (суммаризация правил) —
      Этап 23 (COMPACT_SYSTEM_PROMPT при it>=3, ~0.3K токенов, RULES-маркер сохранён)
### P2 (отличие от «зрелого прототипа»)
- [x] **Tauri desktop** — этап 20 (`dd45746`), WebView2 ~50MB против ~300MB pywebview
- [x] **Task-level model router** — классификатор задачи (zero-shot 1.5b) выбирает модель до
      цикла — Этап 30 (pick_task_model: bugfix/refactor/tests→qwen3:8b, chat→3b; AI_MODEL/
      юзер-выбор побеждают; кэш установленных 60с)
- [x] **Plan tree UI** — визуальное дерево шагов (pending/done/error) — Этап 31 (PLAN_STEPS +
      {type:plan} SSE-события, _plan_mark после каждого тула, JS-дерево ✓/✗/○)
### P3 (10/10)
- [x] **Self-healing loop** — 2 ошибки одним тулом → агент сам меняет стратегию (edit → read→write) — Этап 32 (err_streak/err_tool → «SWITCH STRATEGY NOW» в динамическом контексте)
- [x] **Multi-turn RAG** — «RAG over plan»: сначала найти все затронутые файлы, потом редактировать — Этап 33 (_rag_over_plan: шаги плана → rag_search → блок «Plan context» с топ-6 файлами; AI_RAG_OVER_PLAN=0 отключает)
- [x] Голосовой ввод — Этап 34 (кнопка 🎤, Web Speech API ru-RU) + Этап 43 (Whisper-бэкенд: AI_STT_URL / AI_STT_BINARY, /api/stt, MediaRecorder-фолбэк без браузерного API)

Отметки по оценке: structural prompt (XML-теги) и constrained decoding — заморозка правил 1-22 +
AI_JSON_FORMAT=1 уже частично покрывают; семантическая валидация путей — видит «директорию» на
уровне ФС (аналогичные подсказки), unquoted values — в lenient-парсере (Этап 37).

### Обновление 2026-08-09 — этапы 35–43 (план до 9.5 закрыт, кроме внешней переоценки)
- 35 rate limiting /api/chat (per-IP, burst), 36 семантическая валидация путей (директория → подсказка ДО мутаций),
  37 unquoted JSON-значения, 38 EXTRA_ROOTS/ALLOW_OUTSIDE (работа вне workspace),
  39 glob по абсолютным путям/cwd, 40 обучение SwiftMatch-класс приложений (11 скиллов + Rule 22),
  41 DI-контейнер (core/container.py, api_* на resolve вместо import agent), 42 абстракции RAG/DB
  (RagAdapter/KVStore/init_defaults), 43 Whisper STT (stt.py, /api/stt, MediaRecorder-фолбэк).
- Тесты: 86 → 104 → 107/107. Осталось: внешняя переоценка 9.5/10.

## Известные пределы (поведение модели, не кода)
- Полный цикл «исправь баг + прогони тесты» требует follow-up «yes» на [CONFIRM] (деструктивные операции — по дизайну)
- deepseek-r1:7b в UI (если выбрать) галлюцинирует пути и пишет туториалы вместо тулов — дефолт qwen2.5-coder:7b
- 7B-модели иногда пишут JSON-тул в тексте без ```tool-ограждения — bare-парсер + lenient JSON теперь ловит почти всё
- deepseek-coder-v2:16b (legacy-путь) — слабый исполнитель: ~0–1/3 live-сценариев (битые блоки, инструкции вместо действий); qwen3:8b (native) — лучшая из установленных ~3/3
- live-прогоны нестабильны между запусками из-за вытеснения моделей из 12GB VRAM (warm-up сглаживает)

## Оценка 5 — 8.9/10 (внешний ревьювер, 2026-08-08)

«С учётом обновлённых артефактов (stage 20 Tauri desktop, 86/86 тестов, оценки 8.7/8.8/8.9)
даю переоценку: 8.9/10 (+0.1 к предыдущей).»

| Что изменилось | Было | Стало | Влияние |
|---|---|---|---|
| Tauri (P2, blocked on Rust/MSVC) | заблокировано | сделано (stage 20): Rust 1.97.1 + MSVC Build Tools, src-tauri/ cargo-only wrapper, WebView2 1280×860, scripts/run_tauri.bat | UX/UI +0.2 (native desktop двойной: Tauri ~50MB + pywebview fallback) |
| Тесты | 83/83 | 86/86 (+3: vendor static, syntax guard, multi-file patch) | Код/тесты — на уровне 9.5 |
| Оценки | Kimi 8.7, DS 8.6 | Kimi 8.7, External 8.8, DS 8.9 | консенсус внешних ревьюверов вырос |

| Ось | Балл | Комментарий |
|---|---|---|
| Архитектура | 9.0 | монолиты разбиты, core/ + api_* + tools/ — зрелая модульность. Остаётся: DI вместо import agent as _agent |
| Код/тесты | 9.5 | 86/86 unit + live multi-model suite — уровень production-команды |
| Безопасность | 8.5 | Docker opt-in, whitelist bash, path jail. Ждёт: AST-анализ python -c/node -e, git-auto-branch |
| AI/модели | 8.2 | native/legacy гибрид, dynamic context, TOOL_STATS. Ждёт: prompt KV-cache, task-level router |
| UX/UI | 8.3 | CM6, xterm.js+WS, Tauri WebView2, diff preview, RAG progress. Ждёт: plan tree UI, AST multi-file edit |
| Доки/процесс | 9.0 | AGENTS.md, bilingual README, context.txt с историей коммитов — лучше 90% open-source |

Что осталось до 9.5/10 (по оценке): P1 — AST-based edit guard, git-auto-branch, prompt KV-cache;
P2 — task-level router, plan tree UI, ARCHITECTURE.md; P3 — self-healing loop, multi-turn RAG.
[На сегодня (этапы 21–34) ВЕСЬ план закрыт; осталось вне оценок: DI-контейнер,
rate limiting /api/chat, семантическая валидация аргументов, unquoted JSON.]
Вердикт: «прошёл точку "зрелый прототип", зона production-ready beta. Tauri закрыл последний
крупный P2. Оставшиеся P1 — полировка крайних случаев, а не архитектурные дыры. После P1(1)
AST edit guard проект заслуживает v2.0-stable и 9.2–9.3/10.»

СТАТУС НА СЕГОДНЯ (этапы 21–31, 2026-08-08): **ВСЕ пункты оценки 5 закрыты** —
P1(1) AST edit guard = этап 21 (уникальность + fuzzy-подсказка), P1(2) git-auto-branch =
этап 22 (GIT_AUTO_COMMIT/GIT_AUTO_BRANCH, ветка agent-session-*, auto-commit write/edit/patch),
P1(3) prompt KV-cache = этап 23 (COMPACT_SYSTEM_PROMPT при it>=3), P2(1) task-level router =
этап 30 (pick_task_model до цикла, AI_MODEL/юзер-выбор побеждают), P2(2) plan tree UI = этап 31
(PLAN_STEPS + события {type:plan} + дерево ✓/✗/○), P2(3) ARCHITECTURE.md = этап 27 (Mermaid +
тулы + env), плюс AUTO_CONFIRM_SAFE (этап 24), авто-подбор qwen3:8b по VRAM (этап 25),
Docker default-when-present (этап 26), AST-рефакторинг тулы rename/extract/inline (этап 28),
VRAM-индикатор (этап 29). Тесты: 97/97 ×2 (было 86/86 на момент оценки). Осталось до 9.5:
P3 — self-healing loop, multi-turn RAG, voice input. [ПЕРЕОЦЕНКА ИТОГА: P3 закрыт
этапами 32–34 (2026-08-08) — self-healing loop (2+ ошибки тула подряд → совет
SWITCH STRATEGY в dynamic context, err_streak в цикле), RAG over plan (план →
rag_search по шагам → блок «Plan context» с содержимым топ-6 файлов,
AI_RAG_OVER_PLAN=0), voice input (🎤 в UI, Web Speech API STT ru-RU interim).
Тесты: 99/99 ×2 (b85800f). ВЕСЬ план оценок 8.3–8.9 реализован этапами 19–34.
Осталось вне оценок (до 10/10): DI-контейнер, rate limiting /api/chat,
семантическая валидация аргументов, unquoted JSON в lenient-парсере.]
[ЗАКРЫТО этапами 35–37 (1f8413f): rate limiting /api/chat (per-IP окно
60/мин + burst 6, 429, AI_RATE_LIMIT=0 откл.), семантическая валидация
путей (_path_dir_hint: директория → «looks like a directory» + list/glob,
read/write/edit/patch до мутаций), unquoted string values в lenient JSON
(включая пути с точкой). Тесты 102/102 ×2. Осталось до 10/10: DI-контейнер,
абстракции RAG/DB, Whisper-сервер, внешняя переоценка 9.5/10.]
[Этап 38 (6afcfb9): EXTRA_ROOTS/ALLOW_OUTSIDE — работа вне workspace по
запросу «создай приложение в E:\test mycode» (path jail расширяем);
блок изобретённых путей сохранён; тесты 103/103; live-подтверждение через
:8765. Осталось до 10/10: DI-контейнер, абстракции RAG/DB, Whisper-сервер,
внешняя переоценка 9.5/10.]

## Вопросы для анализа (что хотим от Kimi)
1. Правильна ли архитектура prompt-based tool calling для 7B-моделей? Что улучшить в system prompt теперь?
2. Достаточны ли анти-галлюцинационные гарды (code detector, lenient JSON, tool-error nudge)? Что ещё реально работает на 7B?
3. Docker-песочница: правильный ли дизайн (opt-in, whitelist + контейнер, fallback)? Стоит ли сделать её режимом по умолчанию или это ок для локального агента?
4. Статистика тулов (TOOL_STATS) — стоит ли встраивать счётчики ошибок в system prompt для самообучения модели?
5. Native tool calling vs legacy ```tool: стоит ли мигрировать legacy-модели или гибрид (qwen3 native, остальные legacy) — правильный выбор?
6. Оценка версии (было 8.7/10): что поднять до «production-ready» (9.5+/10)?
