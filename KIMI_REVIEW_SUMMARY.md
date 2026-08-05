# My OpenCode v2 — Сводка для внешнего анализа (Kimi)

Дата: 2026-08-06 · Тесты: **63/63 unit + 2/2 live (реальная qwen2.5-coder:7b)** · Сервер: `python agent.py` → http://localhost:8765
Репозиторий: github.com/elips0675-web/Myopen-ode (master, работает локально, Windows, Python 3.14)

## Что это
Локальный ИИ-агент-программист на Ollama (замена Cursor/Windsurf/Claude Code — бесплатно, приватно).
Ключевая особенность: Ollama НЕ имеет нативных tool_calls → модель принуждается промптом выдавать
блоки ```tool {JSON}```, бэкенд парсит/валидирует/выполняет их в цикле (prompt-based tool calling).
Дефолтная модель qwen2.5-coder:7b (deepseek-r1:7b игнорирует tool-формат), num_ctx 16384.

## Архитектура (3 слоя)
HTML/CLI UI --HTTP/SSE--> FastAPI (`agent.py`) --> agent loop (LLM → parse → tool → LLM, max 12 итераций)
--> Ollama 127.0.0.1:11434. Файлы: `agent.py` (сервер+цикл, ~1030 стр.), `tools.py` (28 инструментов +
call_ollama + bash-песочница, ~1110 стр.), `rag.py` (гибридный поиск BM25+эмбеддинги, FAISS/numpy),
`ui.py` (HTML, ~20KB) + `static/app.js` (JS, 30KB), `lsp.py`, `mcp_server.py`, `mcp_client.py`,
плагины `.agent_plugins/*.py`, скиллы `.agent_skills/`.

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

Из рекомендаций оценок 2 реализовано: few-shot, [DONE]-маркер, один тул за раз, статистика тулов,
пост-обработка JSON, Docker-песочница, code detector, Cache-Control. «Таймаут после [CONFIRM]» — НЕ нужен:
после CONFIRM цикл завершается break по дизайну (юзер пишет «yes» → auto-exec pending без вызова модели).

## Что осталось (P2)
- xterm.js + WebSocket для долгих процессов (серверы, отладчики) — приоритет №2
- TOOL_STATS в промпт (нужен per-session stats)
- Динамические элементы UI: индикатор «модель думает», прогресс-бар RAG, просмотр audit-лога
- Рефакторинг монолитов: core/agent_loop.py, core/tool_parser.py, core/tool_executor.py, core/safety/*
- RAG: сегментирование по папкам (6000 чанков ≈ 3 млн символов)
- CLI-режим без UI; восстановление сессии после сбоя; кроссплатформенные тесты; update check
- CodeMirror 6 / Monaco; AST multi-file edit (parso/tree-sitter)
- JSON Schema constrained output (Ollama format:"json" — экспериментально)
- Native tool calling — когда Ollama поддержит; Tauri desktop; deepseek-coder-v2:16b (12GB VRAM)

## Известные пределы (поведение модели, не кода)
- Полный цикл «исправь баг + прогони тесты» требует follow-up «yes» на [CONFIRM] (деструктивные операции — по дизайну)
- deepseek-r1:7b в UI (если выбрать) галлюцинирует пути и пишет туториалы вместо тулов — дефолт qwen2.5-coder:7b
- 7B-модели иногда пишут JSON-тул в тексте без ```tool-ограждения — bare-парсер + lenient JSON теперь ловит почти всё

## Вопросы для анализа (что хотим от Kimi)
1. Правильна ли архитектура prompt-based tool calling для 7B-моделей? Что улучшить в system prompt теперь?
2. Достаточны ли анти-галлюцинационные гарды (code detector, lenient JSON, tool-error nudge)? Что ещё реально работает на 7B?
3. Docker-песочница: правильный ли дизайн (opt-in, whitelist + контейнер, fallback)? Стоит ли сделать её режимом по умолчанию или это ок для локального агента?
4. Статистика тулов (TOOL_STATS) — стоит ли встраивать счётчики ошибок в system prompt для самообучения модели?
5. Что важнее дальше: xterm.js+WS, интеграционные тесты, динамический контекст или рефакторинг монолитов?
6. Оценка версии (было 8.3/10): что поднять до «production-ready»?
