# Пакет для внешней переоценки 9.5/10 (Этап 44)

Проект: **My OpenCode v2** — локальный AI-агент-программист на Ollama
(замена Cursor/Windsurf/Claude Code), полностью оффлайн, Windows.
Репозиторий: https://github.com/elips0675-web/Myopen-ode (ветка master).

## Текущий статус
- Тесты: **115/115** (`python -X utf8 test_agent.py`) + **live 3/3** на
  qwen3:8b (`python -X utf8 test_live.py --models qwen3:8b`: create file 18.3s,
  simple question, edit rename) + **бенчмарк по 3 моделям** (`python -X utf8
  test_bench.py --models qwen3:8b`): qwen3:8b 7/7 (394s, включая subagent-review), qwen2.5-coder:7b 1/6,
  deepseek-coder-v2:16b 0/6; отчёты bench_reports/*.json + SUMMARY.md. Live
  @reviewer/@fixer подтверждены: обзор → «CRITICAL: calc.py:2 (division by
  zero)» и реальное исправление файла (guard b==0 → None, 60.4s); прямой
  маркер @reviewer в чате → отчёт «VERDICT: PASS» + [DONE]; прямой маркер
  @fixer в чате → реальное исправление livefix/calc.py (guard b==0 → сообщение,
  «Syntax: OK», подтверждение «yes» в той же сессии).
- Оценки истории: Kimi 8.7 → внешний 8.8 → DeepSeek 8.9 (+переоценка 8.9) →
  внешний 8.9 (Оценка 5). ВЕСЬ план оценок P1–P3 закрыт.
- Модель: qwen3:8b (native tool calling), RTX 3060 12GB, deepseek-r1:1.5b
  как planner; 43 сессии, сервер :8765.

## Что закрыто ПОСЛЕ оценки 8.9/10 (этапы 35–43)
| Этап | Что | Доказательство |
|---|---|---|
| 35 | Rate limiting /api/chat (per-IP sliding window 60/мин, burst 6, 429+retry) | test_rate_limit |
| 36 | Семантическая валидация путей: «looks like a directory» → подсказка list/glob ДО мутаций | test_path_dir_hint |
| 37 | Unquoted JSON-значения в lenient-парсере (пути с точкой/слэшем) | test_unquoted_json_values |
| 38 | Работа вне workspace: EXTRA_ROOTS / ALLOW_OUTSIDE (jail остаётся по умолчанию) | test_extra_roots + live: файл создан в E:\test mycode |
| 39 | glob по абсолютным путям и cwd вне workspace | test_glob_outside_workspace |
| 40 | Обучение созданию SwiftMatch-класс приложений оффлайн: 11 скиллов (.agent_skills/webapp, swiftmatch_arch, dating-app-*, react-patterns, generate-api, offline-ollama) + Rule 22 в промптах | live: агент сам вызвал skill webapp+offline-ollama |
| 41 | DI-контейнер (core/container.py): api_* без `import agent as _agent`, живые провайдеры | test_di_container |
| 42 | Абстракции хранилищ: RAGStore/RagAdapter + KVStore/SqliteKVStore, регистрация в DI | test_abstractions |
| 43 | Whisper STT (опция): /api/stt + /api/stt/status, AI_STT_URL/AI_STT_BINARY, MediaRecorder-фолбэк в UI | test_stt_endpoint + live /api/stt/status |
| 44 | Пакет для ревьювера (этот файл) | — |
| 45 | Reviewer/Fixer сабагенты (SUBAGENT_PROMPTS: REVIEWER — разбор кода с file:line; FIXER — правки с самопроверкой) | test_reviewer_subagent + live: обзор calc.py → «CRITICAL: calc.py:2 (division by zero)» |
| 46 | RAG по внешним папкам: AI_EXTRA_RAG (ключи E0/), _file_root/_scan_files | test_rag_extra_roots + live: поиск по E:\swiftmatch1bdnoutprod → E0/eslint.config.js |
| 47 | Лимит шагов AGENT_STEP_BUDGET=N: принудительный финальный summary без новых тулов | test_step_budget + live: маркер BUDGET + summary за 25.8s |
| 48 | Бенчмарк-обвязка: test_bench.py — 6 сценариев, JSON-отчёт bench_reports/<model>.json | test_bench_report + live 6/6 (468s) |
| 54 | Прямые сабагент-маркеры: @reviewer/@fixer/@general в первом user-сообщении меняют system-промпт и убирают маркер (agent.py _apply_subagent_marker) | test_subagent_marker + live: «@reviewer ...» → «VERDICT: PASS» |
| 55 | Правило 23 (task reviewer → fixer) в SYSTEM_PROMPT, строки в compact и native-промптах | test_system_prompt_rules |
| 56 | UI-автокомплит @-маркеров (reviewer/fixer/general/explore/scout) | static/app.js |
| 60 | Status-событие subagent в потоке чата + agent_type из маркера | test_subagent_marker |
| 61 | GET /api/subagents — каталог (name/marker/desc/tools) | test_subagents_api |
| 62 | Бенч-сценарий subagent-review (7-й): task(agent='reviewer') → VERDICT | test_bench_report |

Тесты выросли: 86 → 104 → 107 → 111 → 113 → 114 → 115 (июль-август 2026).

## Как проверить самому (5 минут)
1. `git clone https://github.com/elips0675-web/Myopen-ode && cd Myopen-ode`
2. `python -X utf8 test_agent.py` → ждать «113/113 passed»
3. `ollama pull qwen3:8b` (если нет) → `python -X utf8 agent.py` →
   открыть http://localhost:8765 → задать «что такое 2+2?» и «создай файл
   hello.py с функцией greet» (деструктивные — подтвердить «да»)
4. Для проверки обучения: «какими скиллами создашь dating-приложение
   полностью оффлайн?» → агент вызовет skill webapp/offline-ollama
5. Скиллы: папка .agent_skills/ (11 md). Обучение по методологии —
   «Обучения программиста.txt» в корне репозитория.
6. Бенчмарк: `python -X utf8 test_bench.py --models qwen3:8b` → 6/6,
   отчёт bench_reports/qwen3-8b.json

## Запрос на оценку
Оценить версию с учётом этапов 35–48 + 54–56 (коммиты 6afcfb9..HEAD):
- Архитектура: DI, абстракции хранилищ, модульность core/ + api_* + tools/
- Код/тесты: 115/115 + 3/3 live, AST-guard, git-бэкапы, rate limit
- Возможности: работа вне workspace, обучение скиллами, Whisper STT,
  RAG over plan, self-healing, native tool calling (qwen3), Tauri desktop,
  сабагенты-маркеры @reviewer/@fixer/@general в чате
- Безопасность: path-jail + EXTRA_ROOTS, bash whitelist, rate limiting,
  изобретённые пути блокируются
- Оффлайн: весь стек (Ollama, MySQL-клоны, STT whisper.cpp) локальный

Ожидание: 9.5/10 при подтверждении закрытия всех пунктов плана.
