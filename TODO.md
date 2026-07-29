# My OpenCode — Что сделано и что осталось

## Что сделано

### Ядро агента (`agent.py`)
- [x] FastAPI сервер на порту 8765, SSE streaming
- [x] Agent loop: до 12 итераций модель → ```tool → исполнение → результат
- [x] 12 инструментов: read, write, edit, bash, glob, grep, list, web, diff, commit, undo, verify
- [x] Prompt-based tool calling (qwen2.5-coder:7b не поддерживает native tool_calls)
- [x] Парсинг ```tool, ```json и голого JSON
- [x] Поддержка абсолютных путей (C:/Users/...)
- [x] Поддержка URL в read (http/https)
- [x] Web инструмент для загрузки страниц

### Безопасность
- [x] Бэкапы перед каждой write/edit (до 50 версий в .agent_backups)
- [x] Undo — откат до предыдущей версии файла
- [x] Подтверждение перед write/edit/bash/commit/undo
- [x] Verify — авто-проверка синтаксиса (py_compile, tsc --noEmit, json.tool)

### Планирование
- [x] `plan` инструмент — модель составляет список шагов
- [x] Пользователь подтверждает "yes" перед выполнением плана

### Контекст
- [x] Автосуммаризация старых сообщений через qwen2.5-coder:1.5b
- [x] Срабатывает при >4000 символов в истории

### Git
- [x] diff — показать изменения
- [x] commit — git add -A + commit
- [x] Репозиторий на GitHub

### UI
- [x] Встроенный HTML (без npm, zero зависимостей)
- [x] SSE streaming ответа
- [x] Переключение моделей
- [x] Статус Ollama (online/offline)

### Тесты
- [x] `test_agent.py` — 11 smoke-тестов (read, write, edit, bash, glob, list, URL, backup, undo, verify)

### Инфраструктура
- [x] Один файл agent.py, zero зависимостей кроме fastapi+uvicorn+requests
- [x] context.txt для ревью проекта
- [x] README.md с описанием

---

## Что осталось

### Критическое
- [x] **Лимит контекста 32K** — 8192 → 32768
- [x] **Таймаут** — 60с лимит + 3 JSON retries
- [x] **Verify с пробелами** — пути в кавычках
- [x] **Structured output validation** — JSON Schema для всех 14 инструментов
- [x] **RAG / embeddings** — семантический поиск по codebase через Ollama embeddings

### Важное
- [ ] **Multi-turn сессии** — stateless HTTP, история теряется между запросами
- [x] **Diff view** — подсветка ```diff (+/-) в UI
- [x] **Retry JSON** — 3 попытки, чистка комментариев
- [ ] **Лимит по токенам** — вместо числа итераций
- [ ] **Управление моделями** — pull/delete через UI

### Среднее
- [ ] **Структурный diff** — только изменённые строки с контекстом
- [x] **Cancel** — кнопка X, AbortController
- [ ] **Тёмная тема**
- [ ] **Параллельный tool calling** — несколько ```tool в одном ответе

### Долгосрочное
- [ ] **Мультиагентность** — 1.5b план, 7b исполнение
- [ ] **WebSearch** — поиск документации/StackOverflow
- [ ] **Claude/GPT API** — fallback для сложных задач
- [ ] **Agent memory** — контекст между сессиями
- [ ] **CI/CD** — авто-тесты на каждое изменение

### Долгосрочное
- [ ] **Мультиагентность** — отдельные агенты для кодинга, дебага, ревью
- [ ] **WebSearch** — поиск документации/StackOverflow
- [ ] **Поддержка Claude/GPT через API** — как fallback для сложных задач
- [ ] **Agent memory** — сохранение контекста между сессиями (файл на диске)
- [ ] **CI/CD** — авто-тесты на каждое изменение agent.py
