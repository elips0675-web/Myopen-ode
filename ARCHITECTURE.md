# ARCHITECTURE.md

Архитектура My OpenCode: как устроен агент, куда идёт запрос, как выполняются инструменты, и как расширять проект.

## 1. Обзор

My OpenCode — локальный AI-агент для редактирования кода. Три способа использования — CLI, веб-интерфейс (FastAPI + статический JS-клиент), десктоп-обёртка (Tauri). Все пути используют один и тот же цикл агента в `core/agent_loop.py`.

```
┌────────────┐   ┌──────────────────┐   ┌──────────────────────────────┐
│   CLI      │   │   Web UI (JS)    │   │   Desktop (Tauri, WebView2)  │
│ myopencode │   │  http://127.0.0.1│   │   спавнит agent.py сам,      │
└─────┬──────┘   └────────┬─────────┘   │   если порт закрыт           │
      │                   │             └──────────────┬───────────────┘
      ▼                   ▼                            ▼
┌───────────────────────────────────────────────────────────────┐
│                     agent.py (FastAPI)                        │
│  роутеры: /api/chat (SSE-поток), сессии, pending/cancel,      │
│  проекты, /health; env-конфиг; авто-подбор модели по VRAM;    │
│  автодетект Docker                                             │
└──────────────┬────────────────────────────────────────────────┘
               ▼
┌───────────────────────────────────────────────────────────────┐
│            core/agent_loop.py — run_agent_loop()              │
│  цикл LLM → parse → execute → feedback (max_iter, timeout,    │
│  анти-луп, summary каждые 3 итерации, компактный промпт,      │
│  native/legacy ветки вызова модели, события для UI)           │
└──────┬──────────────────┬──────────────────┬──────────────────┘
       ▼                  ▼                  ▼
┌────────────┐   ┌────────────────┐   ┌──────────────────────────┐
│ core/      │   │  tools/        │   │  rag.py — RAG-поиск по    │
│ tool_parser│   │  exec.py       │   │  проекту (embeddings +    │
│ tool_exec..│   │  backup.py     │   │  BM25, диск-кэш, SKIP_    │
│ safety/    │   │  llm.py        │   │  PARTS)                   │
│ bash_guard │   │  _state.py     │   └──────────────────────────┘
│ path_guard │   │  audit.py ...  │
└────────────┘   └──────┬─────────┘
                        ▼
              ┌──────────────────┐
              │   Ollama (HTTP)  │  call_ollama / stream_ollama /
              │  :11434 /api/    │  native_chat, /api/embed
              └──────────────────┘
```

## 2. Поток запроса

1. **Вход**: CLI (`python -X utf8 -m myopencode "задача"`), веб-форма или десктоп — запрос уходит в `/api/chat` (SSE-поток событий для UI).
2. **Цикл агента** (`run_agent_loop(msgs, session_id, events, model, deps)`):
   - `deps=None` → импортируется `agent.py` (в CLI/тестах); при вызове из сервера передаётся модуль-«депс» с HTTP-состоянием (сессии, pending/cancel). Это позволяет тестировать цикл без HTTP.
   - каждая итерация: построение динамического контекста → вызов модели (legacy ```` ```tool ````-блоки через `call_ollama`/`stream_ollama` или нативный формат через `native_chat`, если модель в списке `native_supported`) → парсинг блоков (`core/tool_parser.py`) → исполнение (`core/tool_executor.py`) → результат добавляется в `msgs`.
   - защита: лимит итераций `AGENT_MAX_ITER` (12), таймаут `AGENT_TIMEOUT` (300 c), анти-луп (повторный вызов тула блокируется), «повторное пустое» — ретрай один раз.
3. **Инструмент** (`tools/exec.py`): валидация по схеме → проверка безопасности (path jail, bash-whitelist, подтверждение деструктивных операций) → исполнение → аудит-запись → пре-бэкап для undo → (опционально) git-автокоммит на ветке `agent-session-*`.
4. **Обратная связь**: ответ модели вставляет результат тула; `[DONE]`-маркер или текст без тулов завершает цикл.

## 3. Инструменты

| Инструмент | Что делает | Пример |
|---|---|---|
| `read` | читает файл (или URL при http-префиксе) | `{"tool":"read","path":"src/main.py","line":10,"lines":40}` |
| `write` | пишет файл; новый файл + `AUTO_CONFIRM_SAFE=1` → без подтверждения; перезапись → `[CONFIRM]` + diff | `{"tool":"write","path":"a.py","content":"def f(): ..."}` |
| `edit` | замена old → new; неоднозначность («found N times») отклоняется с подсказкой | `{"tool":"edit","path":"a.py","old":"foo()","new":"bar()"}` |
| `patch` | несколько изменений в одном вызове (diff-формат) | `{"tool":"patch","changes":[{"path":"a.py","old":...,"new":...}]}` |
| `bash` | shell-команда с whitelist-проверкой; опционально Docker-песочница | `{"tool":"bash","cmd":"python -m py_compile a.py"}` |
| `glob` | поиск файлов по шаблону | `{"tool":"glob","pattern":"src/**/*.py"}` |
| `grep` | поиск по содержимому (rg) | `{"tool":"grep","pattern":"def f","include":"*.py"}` |
| `list` | содержимое каталога | `{"tool":"list","path":"."}` |
| `verify` | синтаксис Python/JSON | `{"tool":"verify","path":"a.py","kind":"py"}` |
| `search` | RAG-поиск по проекту (embeddings + BM25) | `{"tool":"search","query":"как сохраняются сессии","top_k":3}` |
| `plan` | разбить задачу на шаги (planner-модель) | `{"tool":"plan","task":"рефакторинг module.py"}` |
| `commit` | git add + commit выбранных файлов | `{"tool":"commit","paths":["a.py"],"message":"fix"}` |
| `undo` | откат последней записи/правки (бэкап) | `{"tool":"undo","path":"a.py"}` |
| `question` | уточнить у пользователя перед действием | `{"tool":"question","text":"удалить файл?"}` |
| `web` / `websearch` | fetch страницы / веб-поиск | `{"tool":"web","url":"https://..."}` |
| `skill` | подключить навык (набор инструкций) | `{"tool":"skill","name":"web"}` |
| `diff` | показать изменения файла | `{"tool":"diff","path":"a.py"}` |
| `task` | подзадача для субагента | `{"tool":"task","prompt":"...","agent_type":"explore"}` |
| `todo` | трекер TODO-списка | `{"tool":"todo","action":"list"}` |
| `snapshot` / `restore` | git-снимок проекта / восстановление | `{"tool":"snapshot"}` |

Полные JSON-схемы: `TOOL_SCHEMAS` в `tools/_state.py`.

## 4. Ключевые модули

| Модуль | Ответственность |
|---|---|
| `agent.py` | FastAPI-приложение, сессии, pending/cancel, проекты, env-конфиг, `_auto_pick_model()` (qwen3:8b при ≥10 ГБ VRAM), `_detect_docker()` |
| `core/agent_loop.py` | цикл LLM→parse→execute→feedback, `_dynamic_context`, `summarize_context`, компактный промпт (этап 23), native/legacy вызовы |
| `core/tool_parser.py` | парсеры ```` ```tool ```` / bare / YAML / lenient JSON, `_strip_system_markers`, `extract_pending_tool` |
| `core/tool_executor.py` | диспетчер одного тула: анти-повтор, алиасы, валидация, ветки question/plan/confirm, `_auto_confirm_safe` (этап 24), статистика тулов |
| `core/safety/bash_guard.py` | whitelist-проверка команд, `docker_bash` (этапы 26), запрет `..`-обхода |
| `core/safety/path_guard.py` | path jail: `resolve`, `ensure_safe_path`, `_similar_files` |
| `tools/__init__.py` | SYSTEM_PROMPT, `native_supported`/`native_chat`/`compact_system_prompt`, переэкспорты |
| `tools/exec.py` | реализация тулов: write/edit/patch/bash/glob/grep/list/verify…, `_edit_old_stats` (этап 21), `_git_auto_commit` (этап 22) |
| `tools/backup.py` | `.agent_backups`, undo, git-prebackup, diff-preview, `git_auto_commit` |
| `tools/llm.py` | `call_ollama` / `stream_ollama` (HTTP-клиент Ollama) |
| `tools/_state.py` | глобальное состояние: WORK_DIR, MODEL, TOOL_SCHEMAS, TODO, env-флаги (NO_CONFIRM, AUTO_CONFIRM_SAFE, GIT_AUTO_COMMIT, DOCKER_SANDBOX…) |
| `rag.py` | RAG: индексация файлов (SKIP_PARTS), кэш `.rag_cache`, FAISS/BM25, `rag_search` |
| `ui.py` | HTML-интерфейс (инлайновый JS-клиент, SSE) |
| `src-tauri/` | десктоп-обёртка (cargo-only): main.rs спавнит `python -X utf8 agent.py`, окно 1280×860, env `MYOPENCODE_PORT`/`MYOPENCODE_PYTHON` |

## 5. Окружение (env)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `AI_MODEL` | `qwen2.5-coder:7b` | основная модель; при ≥10 ГБ VRAM и установленной `qwen3:8b` — авто-подбор |
| `PLANNER_MODEL` | `deepseek-r1:1.5b` | модель для `plan` |
| `EMBED_MODEL` | `nomic-embed-text` | модель RAG-эмбеддингов |
| `NO_CONFIRM` | `0` | `1` = без подтверждений write/edit/bash |
| `AUTO_CONFIRM_SAFE` | `0` | `1` = write в новый файл без подтверждения |
| `GIT_AUTO_COMMIT` / `GIT_AUTO_BRANCH` | `0` | авто-коммит после тулов / на отдельной ветке `agent-session-*` |
| `DOCKER_SANDBOX` | `0` | `1` = bash в Docker-песочнице; `0` = отключить автодетект |
| `AGENT_MAX_ITER` / `AGENT_TIMEOUT` | `12` / `300` | лимиты цикла |
| `OLLAMA_URL` | `http://localhost:11434` | адрес Ollama |
| `WORK_DIR` | папка репозитория | рабочая директория (path jail) |
| `MYOPENCODE_PORT` / `MYOPENCODE_PYTHON` | `8765` | Tauri: порт и путь к python |

## 6. Как расширять

- **Новый инструмент**: добавьте JSON-схему в `TOOL_SCHEMAS` (`tools/_state.py`), реализацию `_tool_<name>` в `tools/exec.py` и строку в `VALID_TOOLS`-список диспетчера. Указания для модели — в `SYSTEM_PROMPT` (`tools/__init__.py`).
- **Новое поведение цикла**: правьте `core/agent_loop.py`; инжектируйте зависимости через `deps` и покрывайте тестами в `test_agent.py` (ручной список `tests` в `__main__`, мок `call_ollama`/`stream_ollama`/`subprocess.run`).
- **Тесты**: `python -X utf8 test_agent.py` (юнит-набор; если дефолтная модель native-совместима, раннер форсит legacy-путь), `python -X utf8 test_live.py` (живые сценарии по установленным моделям).
