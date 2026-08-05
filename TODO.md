# My OpenCode — Status

## Что сделано (Core) — 58/58 тестов
- [x] FastAPI + SSE, agent loop (12 итераций, таймаут, cancel), prompt-based tool calling, стриминг тулов в UI
- [x] 28 инструментов (read/write/edit/bash/glob/grep/list/web/websearch/diff/commit/undo/verify/plan/search/question/skill/patch/task/todo/lsp/testgen/db_query/deps/mcp + плагины)
- [x] Сессии SQLite (+миграция из JSON), multi-project, RAG (BM25+эмбеддинги, FAISS/numpy, RAG_MAX_CHUNKS, фоновая индексация), LLM кеш TTL, memory, skills, subagents, slash-команды, MCP сервер+клиенты, LSP (18 серверов), CodeMirror + терминал SSE, pywebview desktop, плагины, audit log
- [x] Безопасность: whitelist bash (не blacklist) + рекурсивная проверка python -c/node -e + запрет `..`-обхода; Docker-песочница (BASH_DOCKER=1, opt-in, fallback); path jail через resolve() (symlink-safe); подтверждение деструктивных операций; блок абсурдных путей; anti-loop; graceful cancellation
- [x] Промпт: правила 1-19 + EXAMPLES (few-shot), code detector, tool-error nudge, lenient JSON (_parse_tool_json), live streaming (первый токен ~2.6s), статистика тулов (TOOL_STATS + /api/stats), Cache-Control static, регрессионный гард промпта (test_system_prompt_rules)

## Оценки внешних ревьюверов (2026-08)
Kimi 2: 8.3/10 → DeepSeek 2: 8.5/10 → DeepSeek 3: 8.6/10 → Kimi 3: 8.7/10
Путь к 9/10: рефакторинг монолитов, динамический контекст, few-shot при ошибках, USER_GUIDE.md
Путь к 9.5/10: xterm.js+WS, интеграционные тесты, RAG-сегментация по папкам, CLI-режим

## ДОДЕЛАТЬ — сводка по всем оценкам (приоритет по консенсусу ревьюверов)

### Этап 1. Динамический контекст в промпте (DS3 №1, Kimi3 P1) — СДЕЛАНО
- [x] Перед каждым вызовом модели: «You are working in project: X (iteration N) / Last action: {tool} (result: ok|error)» (_dynamic_context, agent.py); тесты test_dynamic_context, test_dynamic_context_error_status

### Этап 2. Промпт-усиления + bare-парсер (DS3) — СДЕЛАНО
- [x] Правило 20: «tools ONLY inside ```tool blocks, иначе IGNORED» + примеры VALID/INVALID (negative examples) в конце промпта
- [x] Правило 21: «On the first turn, READ at least one file before writing/editing»
- [x] Retry с температурой 0.1 после сбоя Ollama (attempt>0 → temp 0.1, stream+non-stream)
- [x] Bare-парсер: регулярка {"tool":"..."} в любом контексте уже была (bare_tool_pat) — покрыта; @tool/`// tool:` маркеры — не требуются (модель пишет JSON)
- [ ] TOOL_STATS в промпт осторожно (нужен per-session stats: «TOOL STATS (last 5 calls)» + advice; НЕ сырые цифры, НЕ чужие сессии)

### Этап 3. Few-shot при ошибке тула (DS2, DS3 №5, Kimi3 P1) — СДЕЛАНО
- [x] Вместо голого nudge — конкретный пример исправления (tried → error → corrected tool: glob → read → edit); test_tool_error_fewshot; live-подтверждение в test_live.py

### Этап 4. Инфраструктура (быстрые победы) — СДЕЛАНО
- [x] /health эндпоинт (status, model, planner, workspace, sessions, rag_chunks, uptime); test_health_endpoint
- [x] Docker: BASH_DOCKER_READONLY=1 (read-only mount), BASH_DOCKER_MEM/--memory-swap/--user; test_bash_docker_flags
- [ ] UI: индикатор «модель думает» до первого токена; прогресс-бар RAG-индексации; просмотр .agent_audit.log в UI

### Этап 5. Интеграционные тесты с реальной моделью (DS3 №2, Kimi3 P2) — СДЕЛАНО
- [x] test_live.py: «создай hello.py с функцией greet» (10.8s, прошёл live 2/2) + простой вопрос; skip без Ollama; python test_live.py [--full]

### Этап 6. Документация (Kimi3 P1) — СДЕЛАНО
- [x] USER_GUIDE.md: установка, первый запуск, как задавать задачи, настройка, troubleshooting, скиллы/плагины
- [x] Troubleshooting в USER_GUIDE.md («модель не отвечает», «тулы не работают», «Ollama не видит GPU»)

### Этап 7. Рефакторинг монолитов (Kimi3 P1, 2-3 дня)
- [ ] core/agent_loop.py (только цикл LLM→parse→execute→feedback), core/tool_parser.py (```tool/yaml/bare/lenient), core/tool_executor.py (dispatch+validation+stats), core/safety/bash_guard.py, core/safety/path_guard.py; agent.py — HTTP-роутинг, tools.py — инструменты

### Этап 8. xterm.js + WebSocket (DS2 P2, DS3 №3, Kimi3 P2)
- [ ] Полноценный PTY для долгих процессов (npm start, python server.py) — сейчас SSE-терминал

### Этап 9. Средние фичи (P2, по оценкам)
- [ ] RAG-сегментация по папкам (>100k строк, 6000 чанков ≈ 3 млн символов)
- [ ] CLI-режим без UI (python -m myopencode "задача"; mcp_server.py уже есть)
- [ ] Восстановление сессии после падения сервера (storage есть, но не для восстановления)
- [ ] Восстановление после сбоев: перезапуск без потери контекста
- [ ] Модель-роутер: авто-переключение на qwen2.5-coder при галлюцинациях deepseek-r1 (метрика: % tool-blocks)
- [ ] RAG source attribution: цитирование [file:line]
- [ ] JSON Schema constrained output (Ollama format:"json" — экспериментально)
- [ ] Тесты кроссплатформенности (Windows/Linux/macOS)
- [ ] Автопроверка новых версий (update check)
- [ ] Мульти-агентное иерархическое планирование
- [ ] Git pre-backup перед batch-операциями + «restore all»
- [ ] Inline diff preview перед edit (как в Cursor)
- [ ] Vendor CodeMirror 5 в static/vendor/ (CDN fallback); StaticFiles mount вместо ручного FileResponse
- [ ] Полноценный MCP client (браузер, БД) — mcp_client.py уже есть

## Найденные баги при live-проверке кодинга (2026-07-31) — исправлены
- [x] /api/chat игнорировал выбранную модель (req.model не доходил) — добавлен параметр model
- [x] Итерация 1 всегда шла через PLANNER_MODEL (deepseek-r1:1.5b не следует tool-формату) — retry с основной моделью при отсутствии tool-блоков
- [x] YAML-стиль tool-блоков (`tool write\npath "demo.py"`) не парсился — добавлен yaml_tool_pat
- [x] «yes» после [CONFIRM] не выполнял отложенный тул — _PENDING_CONFIRM + авто-выполнение без вызова модели
- [x] Зацикливание на question/тул-спам — анти-loop, _strip_system_markers, короткие сообщения минуют планировщик
- [x] «Долгое думание» 60+ сек — num_ctx 16384 (8x быстрее), num_predict 2048, AGENT_TIMEOUT 300
- [x] RAG search падал (относительные импорты) — исправлены на абсолютные
- [x] read/edit «not found» без подсказки — _similar_files (похожие файлы)
- [x] Потеря tool-событий в SSE при завершении — 2s grace-drain
- [x] deepseek-r1:7b нестабилен в tool-формате — дефолт qwen2.5-coder:7b (проверено live)

## Live-проверки агента-программиста (2026-08-05)
- [x] Полный цикл: задача → write (CONFIRM) → yes → файл создан → verify (пройдена)
- [x] «Кто ты?» — прямой ответ за 3.6s, без тул-спама и фейковых маркеров (пройдена)
- [x] /api/sessions/search — сессия со сниппетом (пройдена)
- [x] Стриминг: первый текст ~2.6s, итог 8.8s (пройден)
- [x] /api/stats, Cache-Control на /static/app.js (проверены)
- Предел (поведение модели, не кода): полный цикл «исправь баг + прогони тесты» требует follow-up «yes» на CONFIRM (bash) — по дизайну

## Собственные идеи (низкий приоритет)
- [ ] Native tool calling (когда Ollama поддержит)
- [ ] Desktop App (Tauri — pywebview уже работает)
- [ ] GPU embeddings (Ollama уже на GPU — фактически не требуется)
- [ ] deepseek-coder-v2:16b — пулл (для стабильного кодинга на 12GB)
