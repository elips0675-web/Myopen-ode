# Benchmark results (bench_reports/)

Запуск: `python -X utf8 test_bench.py --models <model>[,<model>...]`
Модель/среда: RTX 3060 12GB VRAM, Ollama 127.0.0.1:11434, 2026-08-09.

| Модель | Результат | Время | Примечание |
|---|---|---|---|
| qwen3:8b | **7/7** | 394.1s | native tool calling; create-file 65.9s, edit-rename 10.9s, find-and-fix 100.8s, js-create 12.4s, sql-schema 28.0s, refactor-extract 137.3s, subagent-review 38.9s (task → reviewer → VERDICT) |
| qwen2.5-coder:7b | **5/7** (пик 6/7) | 84–148s | после этапа 69 (бенч теперь передаёт SYSTEM_PROMPT + few-shot примеры 4/5 + правило 24 + rename_symbol в промпте): create-file/find-and-fix/js-create/sql-schema/subagent-review стабильны; провалы — edit-rename и refactor-extract (модель следует шаблону read→edit→bash и не делает полный rename/extract); было 1/6 (2026-08-09, 48.6s) |
| deepseek-coder-v2:16b | 0/6 | 105.6s | не выполняет тулы (битые/отсутствующие блоки); файлы не создаются |

Вывод: qwen3:8b — единственная модель с полным циклом задач в бенчмарке
(включая делегирование ревью сабагенту); qwen2.5-coder:7b после этапа 69
стабильно закрывает 5/7 простых сценариев (цель Kimi 3/6 перевыполнена);
deepseek-coder-v2:16b годится только как fallback/чат.

Важно (этап 69): бенч-обвязка была исправлена — сценарии теперь передают
модели системный промпт (раньше они шли только с user-сообщением, что
искусственно занижало результаты legacy-моделей).

Подробно: qwen3-8b.json, qwen2.5-coder-7b.json, deepseek-coder-v2-16b.json.
