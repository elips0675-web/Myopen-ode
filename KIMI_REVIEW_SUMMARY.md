# My OpenCode v2 — Сводка для внешнего анализа (Kimi)

Дата: 2026-08-05 · Тесты: **52/52 passed** · Сервер: `python agent.py` → http://localhost:8765
Репозиторий: github.com/elips0675-web/Myopen-ode (master, работает локально, Windows)

## Что это
Локальный ИИ-агент-программист на Ollama (замена Cursor/Windsurf/Claude Code — бесплатно, приватно).
Ключевая особенность: Ollama НЕ имеет нативных tool_calls → модель принуждается промптом выдавать
блоки ```tool {JSON}```, бэкенд парсит/валидирует/выполняет их в цикле (prompt-based tool calling).

## Архитектура (3 слоя)
HTML/CLI UI --HTTP/SSE--> FastAPI (`agent.py`) --> agent loop (LLM → parse → tool → LLM, max 12 итераций)
--> Ollama 127.0.0.1:11434. Файлы: `agent.py` (сервер+цикл, 1000 стр.), `tools.py` (28 инструментов +
call_ollama + bash-песочница, 1050 стр.), `rag.py` (гибридный поиск BM25+эмбеддинги, FAISS/numpy),
`ui.py` (HTML, ~20KB) + `static/app.js` (JS, 30KB), `lsp.py`, `mcp_server.py`, `mcp_client.py`,
плагины `.agent_plugins/*.py`, скиллы `.agent_skills/`.

## Последние сессии (коммиты 2480a59..c2aea27, все запушены)
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

Ранее (эти же недели): SQLite-сессии + миграция + JSON-fallback; полнотекстовый поиск по сессиям;
background RAG-индексация; чанкинг RAG по размеру (500 симв., overlap 80); bash whitelist + рекурсивная
проверка python -c/node -e + запрет `..`-обхода; graceful cancellation (кнопка Cancel реально останавливает);
анти-спам гарды (план-гард, anti-loop, _strip_system_markers, формат-ретрай); num_ctx 16384 (~8x быстрее);
дефолтная модель qwen2.5-coder:7b (deepseek-r1:7b игнорирует tool-формат).

## Что осталось (только P2)
- Разбить монолиты run_agent_loop / _execute_tool_inner (1000+ строк на файл), полные docstring/тайп-хинты
- CodeMirror 6 / Monaco (сейчас CodeMirror 5 CDN, zero-dep)
- AST-based multi-file edit (parso/tree-sitter)
- xterm.js терминал (сейчас свой SSE-терминал)
- Docker-изоляция bash (строгая песочница)
- Native tool calling — когда Ollama поддержит
- Tauri desktop (pywebview уже работает); пулл deepseek-coder-v2:16b (12GB VRAM)

## Известные пределы (поведение модели, не кода)
- Полный цикл «исправь баг + прогони тесты» требует follow-up «yes» на [CONFIRM] (деструктивные операции — по дизайну)
- deepseek-r1:7b в UI (если выбрать) галлюцинирует пути и пишет туториалы вместо тулов — дефолт qwen2.5-coder:7b
- Модель иногда пишет JSON-тул в тексте без ```tool-ограждения — bare-парсер ловит частично

## Вопросы для анализа (что хотим от Kimi)
1. Правильна ли архитектура prompt-based tool calling для 7B-моделей? Что улучшить в system prompt?
2. Достаточны ли анти-галлюцинационные гарды? Что ещё реально работает на 7B (retry-стратегии, few-shot тулов)?
3. Есть ли риск деградации после выноса JS в static (кэш/CDN/пути)?
4. Что важнее: рефакторинг монолитов или Docker-песочница/инструменты? Куда инвестировать дальше?
5. Оценка новой версии (было 7.8/10): что поднять до «production-ready»?
