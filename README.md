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

## Что умеет

| Инструмент | Описание |
|---|---|
| `read` | Читать файлы (локальные пути + URL) |
| `write` | Создавать файлы (в любой папке) |
| `edit` | Заменять текст в файлах |
| `bash` | Выполнять команды |
| `glob` | Искать файлы по шаблону |
| `grep` | Искать текст в файлах |
| `list` | Просмотр содержимого папок |
| `web` | Загружать веб-страницы |
| `diff` | Показать git diff |
| `commit` | Git add + commit |
| `undo` | Откатить изменения |
| `verify` | Проверить синтаксис |
| `plan` | Составить план перед работой |

## Архитектура

Один файл `agent.py` (~500 строк), zero зависимостей кроме `fastapi+uvicorn+requests`:

- **FastAPI** сервер на порту 8765
- **HTML UI** — встроенный, без npm
- **SSE streaming** — ответ приходит по токену
- **Agent loop** — до 12 итераций: модель → ```tool → исполнение → результат
- **Prompt-based tool calling** — qwen2.5-coder:7b не поддерживает native tool_calls в Ollama, но агент работает через парсинг ```tool блоков

## Безопасность

- Бэкапы перед каждым write/edit (до 50 версий, в `.agent_backups/`)
- Подтверждение перед write/edit/bash/commit/undo
- Проверка синтаксиса после изменений (py_compile, tsc, json.tool)
- Автоsummarization контекста при длинных диалогах

## Файлы

| Файл | Назначение |
|---|---|
| `agent.py` | Агент (сервер + UI + agent loop) |
| `test_agent.py` | Smoke-тесты (11 тестов) |
| `context.txt` | Описание проекта для ревью |
| `TODO.md` | Что сделано и что осталось |
| `opencode.json` | Конфиг opencode CLI |
| `desktop.py` | Версия с Monaco Editor (архив) |

## Тесты

```bash
python test_agent.py   # 11/11 passed
```

## Репозиторий

https://github.com/elips0675-web/Myopen-ode

Агент сам пишет свой код, коммитит и пушит — dogfooding.
