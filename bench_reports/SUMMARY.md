# Benchmark results (bench_reports/)

Запуск: `python -X utf8 test_bench.py --models <model>[,<model>...]`
Модель/среда: RTX 3060 12GB VRAM, Ollama 127.0.0.1:11434, 2026-08-09.

| Модель | Результат | Время | Примечание |
|---|---|---|---|
| qwen3:8b | **7/7** | 394.1s | native tool calling; create-file 65.9s, edit-rename 10.9s, find-and-fix 100.8s, js-create 12.4s, sql-schema 28.0s, refactor-extract 137.3s, subagent-review 38.9s (task → reviewer → VERDICT) |
| qwen2.5-coder:7b | 1/6 | 48.6s | legacy ```tool; отвечает инструкциями вместо выполнения (известное поведение); прошёл только sql-schema |
| deepseek-coder-v2:16b | 0/6 | 105.6s | не выполняет тулы (битые/отсутствующие блоки); файлы не создаются |

Вывод: qwen3:8b — единственная модель, на которой агент выполняет полный цикл
задач в бенчмарке (включая делегирование ревью сабагенту); остальные годятся
только как fallback/чат.

Подробно: qwen3-8b.json, qwen2.5-coder-7b.json, deepseek-coder-v2-16b.json.
