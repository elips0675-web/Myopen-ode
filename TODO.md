# My OpenCode — Что сделано и что осталось

## Что сделано

### Ядро агента (`agent.py`)
- [x] FastAPI сервер на порту 8765, SSE streaming
- [x] Agent loop: до 12 итераций модель → ```tool → исполнение → результат
- [x] 14 инструментов: read, write, edit, bash, glob, grep, list, web, diff, commit, undo, verify, plan, search
- [x] Prompt-based tool calling (qwen2.5-coder:7b не поддерживает native tool_calls)
- [x] Парсинг ```tool, ```json и голого JSON
- [x] Поддержка абсолютных путей (C:/Users/...)
- [x] Поддержка URL в read (http/https)
- [x] Web инструмент для загрузки страниц
- [x] Fallback auto-execute при "yes"/"да" без tool block
- [x] DeepSeek-R1 reasoning (<think>) авто-фильтрация
- [x] Параллельный tool calling — несколько ```tool блоков в одном ответе

### Сессии
- [x] Сохранение истории в `.agent_sessions/*.json`
- [x] API: GET/POST/DELETE /api/sessions
- [x] UI: боковая панель сессий, создание/удаление/переключение
- [x] Авто-загрузка сессии при отправке сообщения
- [x] Авто-сохранение после каждого ответа агента

### UI
- [x] Встроенный HTML (без npm, zero зависимостей)
- [x] SSE streaming ответа
- [x] Переключение моделей
- [x] Статус Ollama (online/offline)
- [x] Боковая панель: файловое дерево + сессии
- [x] Просмотр файлов (file viewer overlay)
- [x] Тёмная тема с сохранением в localStorage
- [x] Cancel (AbortController)
- [x] Diff view — подсветка ```diff (+/-) в UI
- [x] Confirm box с кнопками Yes/No в сообщении

### Безопасность
- [x] Бэкапы перед каждой write/edit (до 50 версий в .agent_backups)
- [x] Undo — откат до предыдущей версии файла
- [x] Подтверждение перед write/edit/bash/commit/undo
- [x] Verify — авто-проверка синтаксиса (py_compile, tsc --noEmit, json.tool)
- [x] JSON Schema валидация всех 14 инструментов
- [x] 60s таймаут + 3 JSON retries
- [x] 32K контекстное окно

### Планирование
- [x] `plan` инструмент — модель составляет список шагов
- [x] Пользователь подтверждает "yes" перед выполнением плана
- [x] Auto-execute плана при "yes" без повторного tool block

### Контекст
- [x] Автосуммаризация старых сообщений через 1.5b модель
- [x] Срабатывает при >4000 символов в истории

### RAG / Поиск
- [x] Семантический поиск по codebase через Ollama embeddings
- [x] Индексация .py, .js, .ts, .json, .md файлов
- [x] Разбивка на чанки по def/class
- [x] Cosine similarity поиск

### Git
- [x] diff — показать изменения
- [x] commit — git add -A + commit
- [x] Репозиторий на GitHub

### Тесты
- [x] `test_agent.py` — 11 smoke-тестов (read, write, edit, bash, glob, list, URL, backup, undo, verify)

### Инфраструктура
- [x] Один файл agent.py, zero зависимостей кроме fastapi+uvicorn+requests
- [x] context.txt для ревью проекта
- [x] README.md с описанием
- [x] NO_CONFIRM=1 для отключения подтверждений
- [x] Переменные окружения: AI_MODEL, EMBED_MODEL, WORK_DIR, PORT, OLLAMA_URL

---

## Оценки проекта

### Оценка Kimi: 8.2 / 10
| Критерий | Балл |
|----------|------|
| Архитектура и код | 8/10 |
| Функциональность | 9/10 |
| Безопасность | 8/10 |
| UX/UI | 7/10 |
| Потенциал | 9/10 |

### Оценка DeepSeek: 8.5 / 10
"Проект является рабочим, продуманным и надёжным решением для локальной AI-помощи в разработке."

---

## Что осталось

### Важное
- [x] **Лимит по токенам** — MAX_TOKENS env var, агент останавливается при превышении
- [x] **Управление моделями** — pull/delete через UI (кнопки +Pull/-Del в топбаре)
- [x] **WebSearch** — поиск через DuckDuckGo (без API ключа)

### Среднее
- [x] **Структурный diff** — показывать только изменённые строки с файлами
- [x] **Лучшая обработка ошибок** — логирование, Ollama health check, fallback
- [x] **Расширение RAG** — поддержка .go, .rs, .java, .env, .yml, .toml, .cfg, .ini
- [x] **Async rewrite** — /api/chat через asyncio.to_thread, сервер не блокируется

### Долгосрочное
- [x] **Мультиагентность** — PLANNER_MODEL (1.5b) + MODEL (7b)
- [x] **Agent memory** — .agent_memory/, summary между сессиями
- [x] **Claude/GPT API** — FALLBACK_MODEL + OPENAI/ANTHROPIC ключи
- [x] **CI/CD** — .github/workflows/test.yml
- [x] **File drag-and-drop** — drop zone overlay + /api/upload
- [x] **Рефакторинг** — tools.py, rag.py, ui.py, agent.py
