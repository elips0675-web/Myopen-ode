# My OpenCode — Локальный AI-агент программист

**RTX 3060 12GB + Ollama + qwen2.5-coder:7b**

Работает полностью offline. Не нужны API ключи, интернет, npm.

---

## Быстрый старт

```bash
# 1. Убедись что Ollama запущена
ollama list

# 2. Загрузи модель
ollama pull qwen2.5-coder:7b

# 3. Запусти агента
cd E:\My OpenCode
python agent.py

# 4. Открой в браузере
http://localhost:8765/
```

## Инструменты (14)

| Инструмент | Описание |
|---|---|
| `read` | Читать файлы (путь или URL) |
| `write` | Создавать файлы (в любой папке) |
| `edit` | Заменять текст в файлах |
| `bash` | Выполнять команды |
| `glob` | Искать файлы по шаблону |
| `grep` | Искать текст в файлах |
| `list` | Содержимое папок |
| `web` | Загружать веб-страницы |
| `diff` | Git diff |
| `commit` | Git add + commit |
| `undo` | Откатить изменения |
| `verify` | Проверить синтаксис |
| `plan` | Составить план, пользователь подтверждает |
| `search` | Семантический поиск по codebase (RAG) |

## Безопасность

- Бэкапы перед write/edit (до 50 версий в `.agent_backups/`)
- Подтверждение перед write/edit/bash/commit/undo
- `plan` инструмент — модель предлагает шаги, пользователь подтверждает
- Проверка синтаксиса после изменений (py_compile, tsc, json.tool)
- 60s таймаут на agent loop, 3 retries при битом JSON
- JSON Schema валидация всех tool вызовов

## Архитектура

Один файл `agent.py` (~600 строк), зависимости: `fastapi`, `uvicorn`, `requests`.

- **FastAPI** сервер на порту 8765, SSE streaming
- **Agent loop**: до 12 итераций, 60s timeout, 3 JSON retries
- **Prompt-based tool calling** — qwen2.5-coder:7b не поддерживает native tool_calls
- **HTML UI** — встроенный (zero npm), Cancel, diff view
- **Context**: автоsummarization через qwen2.5-coder:1.5b при >4K символов
- **32K контекстное окно**
- **RAG**: семантический поиск через Ollama `/api/embed` + cosine similarity

## Файлы

| Файл | Назначение |
|---|---|
| `agent.py` | Агент (сервер + UI + agent loop + RAG) |
| `test_agent.py` | Smoke-тесты (11 тестов) |
| `context.txt` | Описание проекта для ревью |
| `TODO.md` | Что сделано и что осталось |
| `opencode.json` | Конфиг opencode CLI |

## Тесты

```bash
python test_agent.py   # 11/11 passed
```

## Репозиторий

https://github.com/elips0675-web/Myopen-ode

Агент сам пишет свой код, коммитит и пушит — dogfooding.
