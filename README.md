# AI Coder v2 — OpenCode Desktop Alternative

Локальный AI-агент-программист на Ollama. Замена Cursor/Windsurf/Claude Code — бесплатно, приватно, офлайн.

**Оценки:** Kimi 8.2/10 · DeepSeek 8.5/10 · Рекомендации из оценок реализованы

## Возможности

- **22 инструмента**: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search (RAG), **question**, **skill**, **patch**, **task**, **todo**, **lsp**
- **UI**: файловое дерево + сессии, тёмная тема, подсветка синтаксиса, diff, drag-and-drop, confirm-диалоги
- **RAG**: семантический поиск по codebase с **дисковым кешированием** — .py, .js, .ts, .go, .rs, .java, .yml, .toml, .env, .cfg, .ini
- **Multi-agent**: PLANNER_MODEL (лёгкая 1.5b) планирует, основная модель исполняет
- **WebSearch** через DuckDuckGo (без API ключа)
- **Fallback**: OpenAI / Claude API, если Ollama недоступен
- **Agent memory**: `.agent_memory/` — кросс-сессионная память (лимит настраивается)
- **Verify**: автопроверка синтаксиса после write/edit
- **Бэкапы**: до 50 версий, undo одной командой
- **Управление моделями**: +Pull / -Del прямо из UI
- **Async**: все блокирующие вызовы через `asyncio.to_thread`
- **CI/CD**: `.github/workflows/test.yml`

### Безопасность (добавлено по ревью)
- ✅ **Защита от directory traversal** — read/write/edit за пределами WORK_DIR блокируются
- ✅ **Bash sandbox** — чёрный список опасных команд (rm -rf /, mkfs, dd, curl | sh и др.)
- ✅ **Retry с exponential backoff** при падении Ollama (3 попытки)

### Производительность (добавлено по ревью)
- ✅ **Точный подсчёт токенов** — через `eval_count` из ответа Ollama
- ✅ **Суммаризация контекста внутри loop** — каждые 3 итерации
- ✅ **RAG cache на диск** — эмбеддинги сохраняются в `.rag_cache/`, не пересчитываются при каждом запуске
- ✅ **Настраиваемый таймаут** — AGENT_TIMEOUT для цикла и bash

### UI (добавлено по ревью)
- ✅ **Подсветка синтаксиса** в просмотре файлов (Python, JS, TS, Go, Rust, Java, JSON, YAML, TOML, INI и др.)
- ✅ **Question tool** — агент задаёт вопросы с вариантами ответа, пользователь выбирает кнопкой
- ✅ **Skills система** — `.agent_skills/*.md` — переиспользуемые инструкции для агента
- ✅ **Patch tool** — применение unified diff к файлам
- ✅ **Session sharing** — экспорт/импорт сессий через JSON
- ✅ **Subagents** — @explore (read-only), @scout (web), @general (full access) с разными правами
- ✅ **Multi-project** — переключение между проектами из UI, отдельные сессии/файлы/RAG на проект
- ✅ **LSP интеграция** — goToDefinition, findReferences, hover, documentSymbols через pylsp/typescript-language-server
- ✅ **Slash-команды** — /test, /deploy, /review, /fix, /doc в чате
- ✅ **Todo tracking** — todo-лист внутри сессии (add/complete/list)
- ✅ **DeepSeek-V4-Flash** — поддержка 1M контекста через FLASH_PROVIDER/FLASH_API_KEY

```bash
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text
pip install fastapi uvicorn requests duckduckgo_search
python agent.py
# → http://localhost:8765/
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `AI_MODEL` | `deepseek-r1:7b` | Основная модель |
| `PLANNER_MODEL` | `deepseek-r1:1.5b` | Модель для планирования |
| `EMBED_MODEL` | `nomic-embed-text` | Модель для RAG |
| `WORK_DIR` | `E:\\My OpenCode` | Рабочая директория (проект) |
| `NO_CONFIRM` | `0` | `1` = без подтверждений для write/edit/bash |
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

## Архитектура

```
agent.py   — FastAPI сервер, endpoints, agent loop
tools.py   — инструменты, call_ollama с retry, fallback, bash sandbox
rag.py     — индексация и семантический поиск с дисковым кешем
ui.py      — HTML UI (встроенный, без зависимостей)
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
| `/api/upload` | POST | Drag-and-drop загрузка файлов |

## LSP серверы (установка)

```bash
pip install python-lsp-server    # Python
npm i -g typescript-language-server  # JS/TS
go install golang.org/x/tools/gopls@latest  # Go
```

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

**Ratings:** Kimi 8.2/10 · DeepSeek 8.5/10 · All review recommendations implemented

## Features

- **22 tools**: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search (RAG), **question**, **skill**, **patch**, **task**, **todo**, **lsp**
- **UI**: file tree explorer + session management, dark theme, **syntax highlighting**, diff view, drag-and-drop, confirm dialogs
- **RAG**: semantic code search with **disk caching** — .py, .js, .ts, .go, .rs, .java, .yml, .toml, .env, .cfg, .ini
- **Multi-agent**: PLANNER_MODEL (lightweight 1.5b) plans, main model executes
- **WebSearch** via DuckDuckGo (no API key required)
- **Fallback**: OpenAI / Claude API when Ollama is unavailable
- **Agent memory**: `.agent_memory/` — cross-session memory (configurable limit)
- **Verify**: auto syntax check after write/edit (py_compile, tsc, json.tool)
- **Backups**: up to 50 file versions, undo via single command
- **Model management**: +Pull / -Del from UI
- **Async**: all blocking calls via `asyncio.to_thread`
- **CI/CD**: `.github/workflows/test.yml`

### Security
- ✅ **Directory traversal protection** — read/write/edit outside WORK_DIR blocked
- ✅ **Bash sandbox** — blacklist of dangerous commands (rm -rf /, mkfs, dd, curl | sh, etc.)
- ✅ **Exponential backoff retry** on Ollama failure (3 attempts)

### Performance
- ✅ **Accurate token counting** via Ollama's `eval_count`
- ✅ **In-loop context summarization** every 3 iterations
- ✅ **RAG disk cache** — embeddings saved to `.rag_cache/`, not rebuilt on every launch
- ✅ **Configurable timeout** — AGENT_TIMEOUT for loop and bash

### UI
- ✅ **Syntax highlighting** in file viewer (Python, JS, TS, Go, Rust, Java, JSON, YAML, TOML, INI, etc.)
- ✅ **Question tool** — agent asks questions with answer buttons
- ✅ **Skills system** — `.agent_skills/*.md` — reusable instructions for the agent
- ✅ **Patch tool** — apply unified diffs to files
- ✅ **Session sharing** — export/import sessions as JSON
- ✅ **Subagents** — @explore (read-only), @scout (web), @general (full access) with different permissions
- ✅ **Multi-project** — switch between projects from UI, separate sessions/files/RAG per project
- ✅ **LSP integration** — goToDefinition, findReferences, hover, documentSymbols via pylsp/typescript-language-server
- ✅ **Slash commands** — /test, /deploy, /review, /fix, /doc in chat
- ✅ **Todo tracking** — in-session todo list (add/complete/list)
- ✅ **DeepSeek-V4-Flash** — 1M context support via FLASH_PROVIDER/FLASH_API_KEY

```bash
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text
pip install fastapi uvicorn requests duckduckgo_search
python agent.py
# → http://localhost:8765/
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AI_MODEL` | `deepseek-r1:7b` | Main model |
| `PLANNER_MODEL` | `deepseek-r1:1.5b` | Planning model |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model for RAG |
| `WORK_DIR` | `E:\\My OpenCode` | Workspace directory |
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
agent.py   — FastAPI server, endpoints, agent loop
tools.py   — tool implementations, Ollama caller with retry, bash sandbox
rag.py     — code indexing and semantic search with disk cache
ui.py      — HTML UI (inline, zero dependencies)
```

## Recommended Models

| Model | VRAM | Purpose |
|---|---|---|
| `deepseek-r1:7b` | ~5.5GB | Coding + reasoning |
| `deepseek-r1:1.5b` | ~1.5GB | Planning (PLANNER_MODEL) |
| `qwen2.5-coder:7b` | ~5.5GB | Alternative to deepseek |
| `nomic-embed-text` | ~0.5GB | RAG embeddings |
