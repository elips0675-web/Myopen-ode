# Benchmark results (bench_reports/)

Запуск: `python -X utf8 test_bench.py --models <model>[,<model>...]`
Стенд: RTX 3060 12GB VRAM, Ollama 127.0.0.1:11434.

| Модель | Результат | Время | Примечания |
|---|---|---|---|
| qwen3:8b | **7/7** | **270.5s** (2026-08-12, свежий код stage 73/82: create-file 10.1s, edit-rename 9.2s, find-and-fix 79.9s, js-create 12.3s, sql-schema 26.5s, refactor-extract 101.8s, subagent-review 30.8s; 0 ошибок кодировки; прежние прогоны 394.1s / 513.8s 2026-08-09) | native tool calling |
| qwen2.5-coder:7b | **5/7** (пик 6/7) | 84-148s | этап 69 (фикс: бенч не передавал SYSTEM_PROMPT + few-shot примеры 4/5 + правило 24 + rename_symbol в рекламе): create-file/find-and-fix/js-create/sql-schema/subagent-review прошли; упали edit-rename и refactor-extract (предлагает готовый код вместо цепочки read→edit→bash); старт 1/6 (2026-08-09, 48.6s) |
| deepseek-coder-v2:16b | 0/6 | 105.6s | тулы не выполняет (дает инструкции/лишний текст); только для fallback-общения |

Вывод: qwen3:8b — единственная рабочая модель для полного цикла
(прямые вызовы инструментов в формате Ollama); qwen2.5-coder:7b после этапа 69
стабильно сохраняет 5/7 при включённом few-shot (пик Kimi 3/6 подтверждён);
deepseek-coder-v2:16b подходит только как fallback-собеседник.

Замечание (этап 69): модель-независимость — бенч не передавал системного
промпта с примерями по умолчанию (раньше работал только с user-сообщениями,
не задействуя настройки legacy-формата).

Отчёты: qwen3-8b.json, qwen2.5-coder-7b.json, deepseek-coder-v2-16b.json.