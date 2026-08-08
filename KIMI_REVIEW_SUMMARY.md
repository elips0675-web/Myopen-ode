# My OpenCode v2 — Сводка для внешнего анализа (Kimi)

Дата: 2026-08-08 · Тесты: **83/83 unit + мультимодельный live-набор (qwen2.5-coder:7b, qwen3:8b, deepseek-coder-v2:16b)** · Сервер: `python agent.py` → http://localhost:8765
Репозиторий: github.com/elips0675-web/Myopen-ode (master, работает локально, Windows, Python 3.14)

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
30. **Этап 16 — вынос роутов из agent.py**: добавлены api_sessions.py / api_files.py /
    api_misc.py (APIRouter), в agent.py — include_router в конце + импорты-сироты вычищены.
    Спецслучай: `python agent.py` (а не `import agent`) — __main__ регистрируется в sys.modules
    как `agent` (иначе роутеры импортируют свежую копию модуля → ImportError/цикл). Мутируемые
    глобалы (WORK_DIR/SESSIONS_DIR при switch_project) в роутерах читаются динамически через
    `import agent as _agent` (копия-на-импорт устаревала бы). Тесты health/update_check/
    session_search перенесены на api_misc/api_sessions. 83/83, CLI live, сервер перезапущен.

Из рекомендаций оценок 2-3 реализовано: few-shot, [DONE]-маркер, один тул за раз, статистика тулов,
пост-обработка JSON, Docker-песочница, code detector, Cache-Control, динамический контекст,
интеграционные тесты (мультимодельные), xterm.js+WS терминал, RAG-сегментация по папкам,
CLI-режим, восстановление сессии, update check, кроссплатформенные тесты, MCP client,
native tool calling, desktop (pywebview). «Таймаут после [CONFIRM]» — НЕ нужен:
после CONFIRM цикл завершается break по дизайну (юзер пишет «yes» → auto-exec pending без вызова модели).

## Что осталось (P2)
- TOOL_STATS в system prompt (per-session stats — частично закрыт через sess_stats в _dynamic_context)
- CodeMirror 6 / Monaco; AST multi-file edit (parso/tree-sitter)
- Tauri desktop (ждёт установки Rust/MSVC — pywebview уже закрывает потребность)
- JSON Schema constrained output — экспериментально доступен (AI_JSON_FORMAT=1)
- UI-динамика (индикатор «думает», RAG-прогресс, audit-просмотр) — уже реализованы в app.js

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
