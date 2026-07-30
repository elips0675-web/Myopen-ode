# AI Coder v2 — OpenCode Desktop Alternative

Локальный AI-агент-программист на Ollama. Замена Cursor/Windsurf/Claude Code — бесплатно, приватно, офлайн.

**Оценки:** Kimi 8.2/10 · DeepSeek 8.5/10

## Возможности

- **15 инструментов**: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search (RAG)
- **UI**: файловое дерево + сессии, тёмная тема, diff, drag-and-drop, confirm-диалоги
- **RAG**: семантический поиск по codebase (Ollama embeddings) — .py, .js, .ts, .go, .rs, .java, .yml, .toml, .env, .cfg, .ini
- **Multi-agent**: PLANNER_MODEL (лёгкая 1.5b) планирует, основная модель исполняет
- **WebSearch** через DuckDuckGo (без API ключа)
- **Fallback**: OpenAI / Claude API, если Ollama недоступен
- **Agent memory**: `.agent_memory/` — кросс-сессионная память
- **Verify**: автопроверка синтаксиса после write/edit
- **Бэкапы**: до 50 версий, undo одной командой
- **Управление моделями**: +Pull / -Del прямо из UI
- **Async**: все блокирующие вызовы через `asyncio.to_thread`
- **CI/CD**: `.github/workflows/test.yml`

## Быстрый старт

```bash
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text
pip install fastapi uvicorn requests
python agent.py
# → http://localhost:8765/
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `AI_MODEL` | `deepseek-r1:7b` | Основная модель |
| `PLANNER_MODEL` | `deepseek-r1:1.5b` | Модель для планирования |
| `EMBED_MODEL` | `nomic-embed-text` | Модель для RAG |
| `WORK_DIR` | `E:\\My OpenCode` | Рабочая директория |
| `NO_CONFIRM` | `0` | `1` = без подтверждений |
| `PORT` | `8765` | Порт сервера |
| `OLLAMA_URL` | `http://localhost:11434` | URL Ollama |
| `MAX_TOKENS` | `0` | Лимит токенов (0 = без лимита) |
| `FALLBACK_MODEL` | `""` | Резервная модель (gpt-4, claude-3) |
| `OPENAI_API_KEY` | `""` | Ключ для OpenAI fallback |
| `ANTHROPIC_API_KEY` | `""` | Ключ для Claude fallback |

## API endpoints

| Endpoint | Метод | Описание |
|---|---|---|
| `/api/chat` | POST | SSE streaming чат |
| `/api/models` | GET | Список моделей |
| `/api/files` | GET | Дерево файлов |
| `/api/file?path=` | GET | Содержимое файла |
| `/api/sessions` | GET/POST | Список / создание сессий |
| `/api/sessions/{id}` | GET/DELETE | Загрузка / удаление сессии |
| `/api/project` | GET | Информация о проекте |
| `/api/upload` | POST | Drag-and-drop загрузка файлов |

## Архитектура

```
agent.py   — FastAPI сервер, endpoints, agent loop
tools.py   — инструменты, call_ollama, fallback, валидация
rag.py     — индексация и семантический поиск
ui.py      — HTML UI (встроенный, без зависимостей)
```

## Рекомендуемые модели

| Модель | VRAM | Для чего |
|---|---|---|
| `deepseek-r1:7b` | ~5.5GB | Кодинг + reasoning |
| `deepseek-r1:1.5b` | ~1.5GB | Планирование (PLANNER_MODEL) |
| `qwen2.5-coder:7b` | ~5.5GB | Альтернатива |
| `nomic-embed-text` | ~0.5GB | RAG эмбеддинги |
