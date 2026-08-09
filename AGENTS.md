# AGENTS.md — обязательные правила для этого проекта

## Промпт-система агента (справочник для ИИ — копировать эти правила при работе над агентом)

Иерархия: **3 варианта системного промпта** (full/compact/native) + **динамический
контекст** + **few-shot recovery** + скиллы по требованию. Всё активируется
автоматически в зависимости от модели и номера итерации.

1. **SYSTEM_PROMPT** (full, legacy) — `tools/__init__.py:37`, ~2K токенов.
   Структура: `[RULES 1–23]` + `[EXAMPLES]` (good/bad/fix-path) + `[VALID/INVALID]`
   (валидный ```tool JSON vs игнорируемый). Используется на итерациях 1–2 и для
   legacy-моделей (qwen2.5-coder:7b, deepseek-coder-v2:16b).
   Ключевые правила: **20** — всё вне ```tool игнорируется (лечит «JSON в
   markdown-списках»); **21** — на первом ходу прочитать файл до write/edit
   (лечит «слепые перезаписи»); **16+22** — не выдумывать пути, внешние папки —
   полными абсолютными путями; **23** — task(agent='reviewer') → task(agent='fixer'),
   не патчить вручную после отчёта. Один тул за ответ, [DONE] для завершения.
2. **COMPACT_SYSTEM_PROMPT** — `tools/__init__.py:215`, ~0.3K токенов.
   Включается при `it >= 3` (core/agent_loop.py:186). Начинается с "CRITICAL: You
   are a coding AGENT with tools on Windows. [COMPACT SYSTEM PROMPT]" и содержит
   **"RULES (short):"** — критично: native-ветка детектит системный промпт по
   подстроке `"RULES" in content[:4000]` (agent_loop.py:188 и :241) — полный,
   компактный и native промпты содержат её, поэтому замена работает для всех.
3. **NATIVE_SYSTEM_PROMPT** — `tools/llm.py:270`, для `native_supported()` моделей
   (qwen3:8b, llama3.1, gpt-oss). **НЕ содержит правил про ```tool-блоки**
   (иначе qwen3 пишет текст вместо tool_calls). 14 правил, модель получает
   `tools=[...]` и возвращает tool_calls. agent_loop.py:236-255: каждый system-месседж
   с "RULES" в [:4000] подменяется на NATIVE_SYSTEM_PROMPT перед native_chat.
4. **SUBAGENT_PROMPTS** — `tools/__init__.py` (reviewer/fixer/general/explore/scout).
   Активация: маркер `@reviewer/@fixer/@general` в первом user-сообщении
   (agent.py `_apply_subagent_marker`, этап 54) или тул `task` (tools/exec.py
   `_tool_task`). Reviewer: read файлов → находки `file:line` → VERDICT: PASS/FAIL —
   без правок. Fixer: по одной правке → verify → test. General: декомпозиция.
5. **Динамический контекст** — `core/agent_loop.py` `_dynamic_context()` (стр. 28),
   вставляется перед КАЖДЫМ вызовом LLM отдельным user-сообщением. Компоненты:
   (a) project + iteration; (b) last action (последний тул + результат);
   (c) per-session ошибки (до 3 тулов); (d) global stats (топ-3 тулов с
   повторяющимися ошибками, ≥2 вызовов); (e) **self-healing**: при `heal_count >= 2`
   — «SWITCH STRATEGY NOW. Do NOT retry <tool> with the same or guessed arguments»
   (стр. 39-44). err_streak поддерживается в цикле (стр. 146, 389-392).
6. **Few-shot recovery-вставки** (после ошибок тула, если модель ответила текстом):
   (a) **tool-error nudge** — system-сообщение с примером исправления
   «tried → Error → corrected» (agent_loop.py:306, максимум 2 цикла);
   (b) **code detector** — если модель пишет `def/class/import` в тексте без тула,
   nudge «use the write tool» (стр. 326). Тесты: test_agent_loop_error_nudge,
   test_code_detector_nudge.
7. **TOOL_SCHEMAS** — `tools/_state.py` (30 тулов, JSON-схемы). Lenient-парсер
   (этап 37) принимает значения без кавычек. JSON без ```tool тоже парсится.
8. **Скиллы** — `.agent_skills/*.md` (webapp, swiftmatch_arch, offline-ollama,
   generate-api, dating-app-*): дополнительные system-инструкции по запросу
   `{"tool":"skill","name":"..."}`. Перед сложной задачей скилл — полный контекст.

**Кастомизация/усиление:**
- Добавить правило — синхронно в SYSTEM_PROMPT + COMPACT_SYSTEM_PROMPT +
  NATIVE_SYSTEM_PROMPT + гард test_system_prompt_rules (test_agent.py:114-116
  проверяет "RULES" в первых 4000 символах).
- Few-shot — в секцию [EXAMPLES] SYSTEM_PROMPT (формат tried → error → corrected).
- Self-healing порог — `heal_count >= 2` в core/agent_loop.py:39 (err_streak, стр. 146).
- Новый скилл — `.agent_skills/my_domain.md` + вызов через skill-тул.

Любые правки этих промптов: обновлять этот раздел, не ломать
test_system_prompt_rules и 115+ тестов, синхронизировать README/TODO/context.

## Документация (ОБЯЗАТЕЛЬНО после любых изменений)

1. После КАЖДОГО изменения кода (фикс, фича, рефакторинг) — обновить ДОКИ в том же шаге:
   - `README.md` (RU + EN разделы) — фичи, инструменты, тесты, установка
   - `TODO.md` — отметить сделанное [x], убрать/перенести пункты, добавить новые
   - `context.txt` — статус, фиксы, баги, модели, счётчики
2. Синхронизировать числа и факты между доками и кодом:
   - количество инструментов (схемы в `tools.py` TOOL_SCHEMAS + плагины `.agent_plugins/`)
   - количество тестов (`python test_agent.py` — актуальное число)
   - оценки в README/context — сверять с файлами `Оценка *.txt` (Kimi 7.8, DeepSeek 9)
   - список коммитов/что сделано
3. Перед коммитом: `git status` — в коммит должны входить и доки, и код (один коммит = код + доки).
4. Проверка перед пушем: `python test_agent.py` (все тесты зелёные), `python -m py_compile <изменённые файлы>`.
5. Не хранить устаревшие копии кода в репо (папка `test/` — кандидат на удаление).

## Чистота репозитория

1. В git только исходники и доки. НЕ трекать: бинарники (`AI Desktop.exe`), локальные данные (`projects.json` — автосоздаётся при старте), устаревшие прототипы (`chat.html` удалён), копии кода для ревьюеров (`test/` удалена), логи/кэши (`*.log`, `*.err`, `.rag_cache/`, `.agent_sessions/`, `.agent_memory/`, `.agent_backups/`, `__pycache__/`).
2. .gitignore держать актуальным при добавлении новых артефактов (exe, json-данные, кэши).
3. Перед коммитом: `git status` — не должно быть лишних/служебных файлов в стейдже.
