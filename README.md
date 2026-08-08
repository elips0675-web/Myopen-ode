# AI Coder v2 — OpenCode Desktop Alternative

Локальный AI-агент-программист на Ollama. Замена Cursor/Windsurf/Claude Code — бесплатно, приватно, офлайн.

**Оценки:** Kimi 8.7/10 · Внешнее ревью 8.8/10 · DeepSeek 8.9/10 (+ переоценка 8.9) · Внешнее ревью 2 — 8.9/10 (весь план оценок P1–P3 закрыт этапами 21–34 + важные пункты 35–38, тесты 103/103, ожидается переоценка 9.5) · План до 9.5/10 — в `KIMI_REVIEW_SUMMARY.md`

**Вне workspace:** `EXTRA_ROOTS="E:\папка;D:\data"` — разрешить агенту читать/писать в папки вне проекта («создай приложение в E:\...»); `ALLOW_OUTSIDE=1` — снять ограничение полностью (для локального использования).

**Оглавление:**
1. [Возможности](#возможности) · [Безопасность](#безопасность-добавлено-по-ревью) · [Производительность](#производительность-добавлено-по-ревью) · [UI](#ui-добавлено-по-ревью)
2. [Тесты](#тесты) · [Переменные окружения](#переменные-окружения) · [Архитектура](#архитектура) · [API endpoints](#api-endpoints)
3. [LSP серверы](#lsp-серверы-установка) · [Примеры промптов](#примеры-промптов) · [Промпты для ИИ-архитектора](#промпты-для-ии-архитектора) · [Рекомендуемые модели](#рекомендуемые-модели) · [English](#english)

## Возможности

- **28 инструментов**: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search (RAG), **question**, **skill**, **patch**, **task**, **todo**, **lsp**, **testgen**, **db_query**, **deps**, **mcp** + 3 плагина (count_lines, format_code, git_stats)
- **Streaming tool execution**: live-прогресс в чате — вызовы инструментов видны в реальном времени по мере работы агента
- **CodeMirror редактор**: вкладки, подсветка, сворачивание кода, Ctrl+S сохранение, **Ctrl+Space автодополнение (LSP)**
- **UI**: файловое дерево + сессии, тёмная тема, diff, drag-and-drop, confirm-диалоги, **автодополнение в чате** (@файлы, #скиллы, /команды), **история сообщений стрелками**, **встроенный терминал** (SSE-стриминг, история, Ctrl+C)
- **Sessions**: SQLite (`.agent_sessions/sessions.db`) — CRUD, экспорт/импорт, авто-миграция из JSON
- **RAG**: гибридный поиск (**BM25 + семантика**) с **инкрементальным дисковым кешем** по файлам — пересчитываются только изменённые
- **LLM кеш** с TTL — повторные запросы не тратят токены (LLM_CACHE_TTL)
- **Multi-agent**: PLANNER_MODEL (лёгкая 1.5b) планирует, основная модель исполняет
- **WebSearch** через DuckDuckGo (без API ключа)
- **Fallback**: OpenAI / Claude API, если Ollama недоступен
- **Agent memory**: `.agent_memory/` — кросс-сессионная память (лимит настраивается)
- **Verify**: автопроверка синтаксиса после write/edit
- **Бэкапы**: до 50 версий, undo одной командой
- **Action audit**: `.agent_audit.log` — журнал всех вызовов инструментов
- **Управление моделями**: +Pull / -Del прямо из UI
- **Async**: все блокирующие вызовы через `asyncio.to_thread`
- **Swagger UI**: `/docs` — OpenAPI документация API
- **CI/CD**: `.github/workflows/test.yml`

### Безопасность (добавлено по ревью)
- ✅ **Защита от directory traversal** — read/write/edit за пределами WORK_DIR блокируются
- ✅ **Bash sandbox** — чёрный список опасных команд (rm -rf /, mkfs, dd, curl | sh и др.)
- ✅ **Retry с exponential backoff** при падении Ollama (3 попытки)

### Производительность (добавлено по ревью)
- ✅ **Точный подсчёт токенов** — через `eval_count` из ответа Ollama
- ✅ **Суммаризация контекста внутри loop** — каждые 3 итерации
- ✅ **Инкрементальный RAG кеш** — per-file кеш в `.rag_cache/`, переиндексируются только изменённые файлы
- ✅ **Гибридный поиск** — BM25 (Okapi) + косинусное сходство
- ✅ **LLM кеш с TTL** — повторные вызовы не расходуют токены (LLM_CACHE_TTL=60)
- ✅ **Настраиваемый таймаут** — AGENT_TIMEOUT для цикла и bash

### UI (добавлено по ревью)
- ✅ **CodeMirror редактор** — вкладки файлов, подсветка, сворачивание, Ctrl+S сохранение, **Ctrl+Space автодополнение через LSP** (POST /api/lsp/completion)
- ✅ **Интерактивный терминал** — панель в UI, потоковый вывод через SSE (POST /api/terminal), история команд, Kill (Ctrl+C)
- ✅ **Автодополнение в чате** — @ для файлов/агентов, / для команд, # для скиллов
- ✅ **История сообщений** — стрелки ↑/↓ в пустом поле
- ✅ **Question tool** — агент задаёт вопросы с вариантами ответа, пользователь выбирает кнопкой
- ✅ **Skills система** — `.agent_skills/*.md` — переиспользуемые инструкции для агента
- ✅ **Patch tool** — применение unified diff (line-aware хунки по номерам `@@`, при несовпадении — ошибка, файл не портится)
- ✅ **Session sharing** — экспорт/импорт сессий через JSON
- ✅ **Subagents** — @explore (read-only), @scout (web), @general (full access) с разными правами
- ✅ **Multi-project** — переключение между проектами из UI, отдельные сессии/файлы/RAG на проект
- ✅ **LSP интеграция** — goToDefinition, findReferences, hover, documentSymbols, **rename**, **completion** через pylsp/typescript-language-server; **fallback по токенам файла** когда LSP-сервер не установлен (идентификаторы + keywords языка, source:"tokens")
- ✅ **MCP сервер** — Model Context Protocol для интеграции с VS Code, Cursor, Claude Desktop
- ✅ **Tab completion** — автодополнение путей по Tab в чате
- ✅ **Progress bar** — SSE прогресс при pull модели
- ✅ **Desktop App** — нативное окно через Tauri/WebView2 и pywebview (или браузер)
- ✅ **Плагины** — `.agent_plugins/*.py`, динамическая загрузка новых инструментов
- ✅ **Slash-команды** — /test, /deploy, /review, /fix, /doc в чате
- ✅ **Todo tracking** — todo-лист внутри сессии (add/complete/list)
- ✅ **testgen** — генерация unit-тестов из кода (Python, JS/TS)
- ✅ **db_query** — выполнение SQL-запросов к локальной БД (SQLite)
- ✅ **deps** — анализ зависимостей: requirements.txt, pyproject.toml, package.json, go.mod, Cargo.toml, Pipfile
- ✅ **MCP-клиенты** — внешние MCP-серверы через `mcp_servers.json` (stdio), инструмент `mcp`: `{"server":"filesystem","call":"read_file","args":{...}}`, `server:"_list"` — список доступных тулов
- ✅ **Streaming tool execution** — SSE-события `tool`/`status` в реальном времени при работе агента (вызовы тулов видны в чате до финального ответа)
- ✅ **Action audit** — `.agent_audit.log` — журнал всех вызовов инструментов
- ✅ **DeepSeek-V4-Flash** — поддержка 1M контекста через FLASH_PROVIDER/FLASH_API_KEY
- ✅ **Thread-safety** — лок на LLM-кеш, todo-список и RAG-индекс (RLock): корректная работа при конкурентных запросах uvicorn

## Тесты

```bash
python test_agent.py   # 83/83 smoke-тестов
python test_live.py    # live-набор на реальных моделях (create/edit/question)
```

Интеграционные тесты с мок-моделью (agent loop + tool calls + live events), SQLite-сессии (CRUD + миграция из JSON), patch line-aware (мульти-хунки, mismatch → None), bash-фильтр (вложенные `bash -c` / `cmd /c`), thread-safety todo, RAG инкрементальный кеш, аудит, терминал, deps, anti-loop (question останавливает итерацию, повтор вызова блокируется).

`test_live.py` прогоняет сценарии по всем установленным моделям (по умолчанию qwen2.5-coder:7b, qwen3:8b, deepseek-coder-v2:16b) с warm-up; флаги `--models qwen3:8b`, `--full`. Пропускается, если Ollama/модель отсутствуют. На 12GB VRAM live-результаты нестабильны между прогонами (вытеснение моделей).

```bash
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text
pip install -r requirements.txt
python agent.py
# → http://localhost:8765/
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `AI_MODEL` | `qwen2.5-coder:7b` | Основная модель. Если не задана явно, при старте выполняется авто-подбор: при ≥10 ГБ VRAM и установленной `qwen3:8b` дефолт становится `qwen3:8b` (лог «Auto-picked...») |
| `DOCKER_SANDBOX` | `0` | `1` = bash-команды в Docker-песочнице (`python:3.12-slim`, при наличии docker; аналог `BASH_DOCKER=1`). `0` отключает и автодетект при старте. При старте Docker детектируется и лог подсказывает включить |
| `PLANNER_MODEL` | `deepseek-r1:1.5b` | Модель для планирования |
| `EMBED_MODEL` | `nomic-embed-text` | Модель для RAG |
| `WORK_DIR` | папка репозитория | Рабочая директория (проект) |
| `NO_CONFIRM` | `0` | `1` = без подтверждений для write/edit/bash |
| `GIT_AUTO_COMMIT` | `0` | `1` = авто-коммит после каждого write/edit/patch (`git: <hash>` в ответе тула) |
| `GIT_AUTO_BRANCH` | `0` | `1` (с GIT_AUTO_COMMIT) = работа в ветке agent-session-*, история не трогается |
| `PORT` | `8765` | Порт сервера |
| `OLLAMA_URL` | `http://localhost:11434` | URL сервера Ollama |
| `MAX_TOKENS` | `0` | Лимит токенов за сессию (0 = без лимита) |
| `FALLBACK_MODEL` | `""` | Резервная модель (`gpt-4`, `claude-3-sonnet`) |
| `OPENAI_API_KEY` | `""` | API ключ OpenAI для fallback |
| `ANTHROPIC_API_KEY` | `""` | API ключ Anthropic для fallback |
| `AGENT_MAX_ITER` | `12` | Максимум итераций агента |
| `AGENT_TIMEOUT` | `60` | Таймаут цикла агента (сек) |
| `AGENT_MEMORY_LIMIT` | `10` | Сколько сессий хранить в памяти |
| `DEBUG` | `""` | `1` = включить debug-логи |
| `FLASH_PROVIDER` | `""` | Провайдер DeepSeek-V4-Flash (`fireworks`, `together`, `groq`) |
| `FLASH_API_KEY` | `""` | API ключ для flash провайдера |
| `FLASH_MODEL` | `deepseek-v4-flash` | Модель flash провайдера |
| `LLM_CACHE_TTL` | `60` | TTL LLM-кеша в секундах (0 = выключен) |

## Архитектура

```
agent.py          — FastAPI app, /api/chat (SSE), сессии/память/проекты, state
api_sessions.py   — сессии: CRUD, поиск, экспорт/импорт
api_files.py      — файловый браузер/редактор, upload
api_misc.py       — stats, health, update, models, projects, terminal (SSE/WS), skills
tools/            — пакет инструментов: _state.py (конфиг), llm.py (Ollama/native/fallback),
                     exec.py (validate/execute/dispatch 26 tools), backup.py, plugins.py,
                     audit.py, paths.py
rag.py            — индексация и семантический поиск с дисковым кешем
ui.py             — HTML UI (встроенный, без зависимостей)
```

## API endpoints

| Endpoint | Метод | Описание |
|---|---|---|
| `/api/chat` | POST | SSE streaming чат |
| `/api/models` | GET | Список моделей Ollama |
| `/api/models/pull?name=` | POST | Скачать модель |
| `/api/models/{name}` | DELETE | Удалить модель |
| `/api/files` | GET | Дерево файлов проекта |
| `/api/file?path=` | GET | Содержимое файла (с подсветкой в UI) |
| `/api/file` | PUT | Сохранить файл (из CodeMirror редактора) |
| `/api/sessions` | GET/POST | Список / создание сессий |
| `/api/sessions/{id}` | GET/DELETE | Загрузка / удаление сессии |
| `/api/project` | GET | Информация о проекте |
| `/api/skills` | GET | Список доступных навыков |
| `/api/sessions/{id}/export` | GET | Экспорт сессии в JSON |
| `/api/sessions/import` | POST | Импорт сессии из JSON |
| `/api/task/{agent}` | GET | Запустить subagent (`explore`, `scout`, `general`) |
| `/api/skills` | GET | Список навыков |
| `/api/projects` | GET/POST | Список / добавить проект |
| `/api/projects/switch` | POST | Переключить активный проект |
| `/api/projects/{idx}` | DELETE | Удалить проект |
| `/api/models/pull/stream` | GET | SSE прогресс скачивания модели |
| `/api/upload` | POST | Drag-and-drop загрузка файлов |

## LSP серверы (установка)

```bash
pip install python-lsp-server    # Python
npm i -g typescript-language-server  # JS/TS
go install golang.org/x/tools/gopls@latest  # Go
```

## Примеры промптов

Как давать задачи агенту (работает на qwen2.5-coder:7b / qwen3:8b):

| Задача | Промпт | Что ожидать |
|---|---|---|
| Багфикс | `В tools/exec.py read падает на пустом файле. Найди причину и исправь, добавь тест` | read → grep → read → edit → verify; запросит `yes` перед записью |
| Рефакторинг | `Переименуй переменную `count` в `total_count` в core/agent_loop.py` | glob/grep вхождения → patch (или серия edit) |
| Новая фича | `Создай utils/timefmt.py: функция fmt_duration(sec) -> "2h 3m"` | write → verify (Syntax: OK) → финальный ответ |
| Тесты | `Сгенерируй тесты для tools/paths.py в test_agent.py (5 кейсов)` | тул testgen / write, потом запуск pytest |
| Объяснение | `Объясни как работает цикл агента в core/agent_loop.py` | read → разбор по шагам, без правок кода |
| Multi-file | `Добавь параметр timeout во все вызовы llm_call в tools/` | patch с `files=[{path, diff}...]` одним вызовом |
| Сабагент | `Исследуй через @explore, какие LSP-серверы поддерживаются, потом summary` | subagent (read-only) → сводка |

Полезные тулы в один шаг: `{"tool":"patch","files":[...]}` (multi-file diff), `{"tool":"task"}` (сабагент с собственным циклом), `{"tool":"search","scope":"core"}` (RAG по папке), `{"tool":"question"}` (агент спрашивает вас с вариантами).

## Промпты для ИИ-архитектора

Готовые системные промпты, превращающие любую LLM в эксперта по проектированию локальных ИИ-агентов:

| Файл | Содержимое |
|---|---|
| `prompts/architect_ru.txt` | Полный промпт (русский) + сокращённый вариант |
| `prompts/architect_en.txt` | Полный промпт (English) с архитектурным стеком и правилами |
| `.agent_skills/architect.md` | Skill для самого агента — `@skill architect` перед сложными задачами по улучшению агента |

Использование: вставить в Custom Instructions (Claude) / System Message (API) / как ТЗ фрилансеру / `.cursorrules`.

## Рекомендуемые модели

| Модель | VRAM | Для чего |
|---|---|---|
| `deepseek-r1:7b` | ~5.5GB | Кодинг + reasoning |
| `deepseek-r1:1.5b` | ~1.5GB | Планирование (PLANNER_MODEL) |
| `qwen2.5-coder:7b` | ~5.5GB | Альтернатива deepseek |
| `nomic-embed-text` | ~0.5GB | RAG эмбеддинги |

## English

# AI Coder v2 — OpenCode Desktop Alternative

Local AI coding agent powered by Ollama. Free, private, offline alternative to Cursor/Windsurf/Claude Code.

**Ratings:** Kimi 7.8/10 · DeepSeek 9/10 · All review recommendations implemented

## Features

- **28 tools**: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search (RAG), **question**, **skill**, **patch**, **task**, **todo**, **lsp**, **testgen**, **db_query**, **deps**, **mcp** + 3 plugin tools (count_lines, format_code, git_stats)
- **Streaming tool execution**: live tool progress visible in chat while the agent works
- **CodeMirror editor**: tabs, syntax highlight, folding, Ctrl+S save, **Ctrl+Space LSP autocomplete**
- **UI**: file tree + sessions, dark theme, diff, drag-and-drop, confirm dialogs, **chat autocomplete** (@files, #skills, /commands), **message history (arrows)**, **built-in terminal** (SSE streaming, history, Ctrl+C)
- **Sessions**: SQLite (`.agent_sessions/sessions.db`) — CRUD, export/import, auto-migration from JSON
- **RAG**: hybrid search (**BM25 + semantics**) with **incremental disk cache** per file — only changed files are reindexed
- **LLM cache** with TTL — repeated queries save tokens (LLM_CACHE_TTL)
- **Multi-agent**: PLANNER_MODEL (light 1.5b) plans, main model executes
- **WebSearch** via DuckDuckGo (no API key)
- **Fallback**: OpenAI / Claude API if Ollama is down
- **Agent memory**: `.agent_memory/` — cross-session memory
- **Verify**: auto syntax check after write/edit
- **Backups**: up to 50 versions, one-command undo
- **Action audit**: `.agent_audit.log` — journal of all tool calls
- **Model management**: +Pull / -Del from UI
- **Async**: all blocking calls via `asyncio.to_thread`
- **Swagger UI**: `/docs` — OpenAPI docs
- **CI/CD**: `.github/workflows/test.yml`

### Security
- ✅ **Directory traversal protection** — read/write/edit outside WORK_DIR blocked
- ✅ **Bash sandbox** — whitelist разрешённых команд + blacklist опасных паттернов (rm -rf, mkfs, dd, curl | sh), нормализация пробелов/кавычек, рекурсивная проверка вложенных интерпретаторов (`bash -c`, `cmd /c`, `powershell -c`, `python -c`, `node -e`), запрет `..`-обхода для деструктивных команд
- ✅ **Graceful cancellation** — POST /api/chat/cancel: агентный цикл останавливается между итерациями, клиент получает `[cancelled]`
- ✅ **Exponential backoff retry** on Ollama failure (3 attempts)

### Performance
- ✅ **Accurate token counting** via Ollama's `eval_count`
- ✅ **In-loop context summarization** every 3 iterations
- ✅ **Incremental RAG cache** — per-file cache in `.rag_cache/`, only changed files re-indexed
- ✅ **Hybrid search** — BM25 (Okapi) + cosine similarity
- ✅ **LLM cache with TTL** — repeated calls don't consume tokens (LLM_CACHE_TTL=60)
- ✅ **Configurable timeout** — AGENT_TIMEOUT for loop and bash

### UI
- ✅ **CodeMirror editor** — file tabs, highlighting, code folding, Ctrl+S save
- ✅ **Chat autocomplete** — @ for files/agents, / for commands, # for skills
- ✅ **Message history** — ↑/↓ arrows in empty input
- ✅ **Question tool** — agent asks questions with answer buttons
- ✅ **Skills system** — `.agent_skills/*.md` — reusable instructions for the agent
- ✅ **Patch tool** — apply unified diffs (line-aware hunks from `@@` numbers, mismatch → clear error, no file corruption)
- ✅ **Session sharing** — export/import sessions as JSON
- ✅ **Subagents** — @explore (read-only), @scout (web), @general (full access) with different permissions
- ✅ **Multi-project** — switch between projects from UI, separate sessions/files/RAG per project
- ✅ **LSP integration** — goToDefinition, findReferences, hover, documentSymbols, **rename** via pylsp/typescript-language-server
- ✅ **MCP server** — Model Context Protocol for VS Code, Cursor, Claude Desktop integration
- ✅ **Tab completion** — path completion via Tab key in chat
- ✅ **Progress bar** — SSE progress stream for model pull
- ✅ **Desktop App** — native window via Tauri/WebView2 and pywebview (or browser fallback)
- ✅ **Plugins** — `.agent_plugins/*.py`, dynamic tool loading
- ✅ **Slash commands** — /test, /deploy, /review, /fix, /doc in chat
- ✅ **Todo tracking** — in-session todo list (add/complete/list)
- ✅ **testgen** — auto-generates unit tests from code (Python, JS/TS)
- ✅ **db_query** — SQL queries against local SQLite DB
- ✅ **DeepSeek-V4-Flash** — 1M context support via FLASH_PROVIDER/FLASH_API_KEY
- ✅ **Real terminal** — xterm.js over WebSocket (`/ws/term`, PTY shell: interactive Python/CMD/PowerShell, resize, Ctrl+C)
- ✅ **CLI mode** — `python -m myopencode "task"` without UI (NO_CONFIRM=1)
- ✅ **Crash recovery** — session checkpoints every 2 iterations + «⚠ interrupted» marker + resume note
- ✅ **Model router** — auto-switch to main model when the planner ignores tool format
- ✅ **Native tool calling** — Ollama `tools=` for qwen3/llama3.1/gpt-oss, legacy ` ```tool` pipeline as fallback
- ✅ **Git snapshot / restore all** — automatic pre-backup before the first mutating tool
- ✅ **Inline diff preview** (Cursor-style) + fully offline UI (vendored CodeMirror 6, no CDN)
- ✅ **Update check** (`/api/update` badge) + CI matrix (Windows/Linux/macOS) + JSON Schema constrained output
- ✅ **RAG folder scope** + source attribution `[file:line]`
- ✅ **MCP client** — full handshake (initialize → notifications/initialized), resources/prompts/tools
- ✅ **Desktop App** — native window via pywebview/Tauri: auto-start/reuse server, ready-poll, app icon, browser fallback

### Tests

```bash
python test_agent.py   # 83/83 smoke tests
python test_live.py    # live suite against real models (create/edit/question)
```

Integration tests with mock model (agent loop + tool calls + live SSE events), SQLite sessions (CRUD + JSON migration), line-aware patch (multi-hunk, mismatch → None), bash filter (nested `bash -c` / `cmd /c`), todo thread-safety, incremental RAG cache, audit, terminal, deps.

`test_live.py` runs the scenarios on every installed model (default: qwen2.5-coder:7b, qwen3:8b, deepseek-coder-v2:16b) with warm-up; flags `--models qwen3:8b`, `--full`. Skips when Ollama/models are missing. On 12GB VRAM live results vary between runs (model eviction).

```bash
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text
pip install -r requirements.txt
python agent.py
# → http://localhost:8765/
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AI_MODEL` | `qwen2.5-coder:7b` | Main model |
| `PLANNER_MODEL` | `deepseek-r1:1.5b` | Planning model |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model for RAG |
| `WORK_DIR` | repo folder | Workspace directory |
| `NO_CONFIRM` | `0` | `1` = skip confirmations |
| `PORT` | `8765` | Server port |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `MAX_TOKENS` | `0` | Token limit per session (0 = unlimited) |
| `FALLBACK_MODEL` | `""` | Fallback model (`gpt-4`, `claude-3-sonnet`) |
| `OPENAI_API_KEY` | `""` | OpenAI API key for fallback |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key for fallback |
| `AGENT_MAX_ITER` | `12` | Max agent loop iterations |
| `AGENT_TIMEOUT` | `60` | Agent loop timeout (seconds) |
| `AGENT_MEMORY_LIMIT` | `10` | Number of sessions to keep in memory |
| `DEBUG` | `""` | `1` = enable debug logging |
| `FLASH_PROVIDER` | `""` | DeepSeek-V4-Flash provider (`fireworks`, `together`, `groq`) |
| `FLASH_API_KEY` | `""` | API key for flash provider |
| `FLASH_MODEL` | `deepseek-v4-flash` | Flash model name |

## Architecture

```
agent.py          — FastAPI app, /api/chat (SSE), sessions/memory/projects, state
api_sessions.py   — sessions: CRUD, search, export/import
api_files.py      — file browser/editor, upload
api_misc.py       — stats, health, update, models, projects, terminal (SSE/WS), skills
tools/            — tool package: _state.py (config), llm.py (Ollama/native/fallback),
                     exec.py (validate/execute/dispatch of 26 tools), backup.py, plugins.py,
                     audit.py, paths.py
rag.py            — code indexing and semantic search with disk cache
ui.py             — HTML UI (inline, zero dependencies)
```

## Recommended Models

| Model | VRAM | Purpose |
|---|---|---|
| `deepseek-r1:7b` | ~5.5GB | Coding + reasoning |
| `deepseek-r1:1.5b` | ~1.5GB | Planning (PLANNER_MODEL) |
| `qwen2.5-coder:7b` | ~5.5GB | Alternative to deepseek |
| `nomic-embed-text` | ~0.5GB | RAG embeddings |
