# My OpenCode — Status

## Что сделано (Core)

- [x] FastAPI сервер, SSE streaming, agent loop (12 итераций)
- [x] 15 инструментов: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search
- [x] Prompt-based tool calling (```tool блоки)
- [x] Сессии (.agent_sessions/), API CRUD
- [x] UI: файловое дерево, сессии, тёмная тема, drag-and-drop, confirm-диалоги
- [x] Бэкапы (50 версий в .agent_backups)
- [x] RAG (семантический поиск), расширен на .go, .rs, .java, .yml, .toml, .env, .cfg, .ini
- [x] Multi-agent (PLANNER_MODEL + MODEL)
- [x] Fallback OpenAI/Claude API
- [x] WebSearch (DuckDuckGo)
- [x] Agent memory (.agent_memory/)
- [x] Управление моделями (+Pull/-Del в UI)
- [x] Async rewrite (asyncio.to_thread)
- [x] CI/CD (.github/workflows/test.yml)
- [x] 11 smoke-тестов (test_agent.py)

## Доработано по ревью (DeepSeek + Kimi)

### Безопасность
- [x] **Защита от directory traversal** — ensure_safe_path() для всех файловых инструментов
- [x] **Bash sandbox** — чёрный список команд (rm -rf /, mkfs, dd, curl | sh и т.д.)
- [x] **Path validation** для glob/grep/list

### Производительность
- [x] **Точный подсчёт токенов** — eval_count из ответа Ollama (вместо len/4)
- [x] **Суммаризация контекста внутри loop** — каждые 3 итерации
- [x] **RAG cache на диск** — .rag_cache/, не пересчитывается при каждом запуске
- [x] **Настраиваемые лимиты** — AGENT_TIMEOUT, AGENT_MAX_ITER, AGENT_MEMORY_LIMIT

### Стабильность
- [x] **Retry с exponential backoff** в call_ollama (3 попытки, 2^attempt сек)
- [x] **Configurable bash timeout** — AGENT_TIMEOUT применяется и к bash

### UI
- [x] **Подсветка синтаксиса** в просмотре файлов (Python, JS, TS, Go, Rust, Java, JSON, YAML, TOML, INI, .env)

### Документация
- [x] **Все env vars описаны** (включая AGENT_MAX_ITER, AGENT_TIMEOUT, AGENT_MEMORY_LIMIT, DEBUG)
- [x] **English версия README**
- [x] **TODO.md обновлён**

## Что ещё можно сделать (некритично)

- [ ] MCP-протокол для интеграции с IDE
- [ ] Native tool calling (когда Ollama поддержит)
- [ ] Юнит-тесты для каждого инструмента
- [ ] Автодополнение (tab completion) для путей в UI
- [ ] Прогресс-бар для pull модели
- [ ] Mobile-responsive sidebar
