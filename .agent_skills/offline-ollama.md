# Offline Ollama — локальная разработка без интернета

Use this skill when creating/running apps with the agent (Ollama, qwen3:8b,
12 GB VRAM) fully OFFLINE — no cloud APIs, no external services.

## Правило: что заменять (SwiftMatch → offline)
| Сервис | Offline-замена |
|---|---|
| Redis (кеш, очереди, idempotency) | in-memory Map + setInterval-клинеры; LRU-обёртка |
| Bull Queue (email/push/image) | простые таймеры/setInterval jobs; файл-журнал |
| Stripe Checkout | mock: POST create-checkout → {url: '/api/premium/mock/complete?plan=gold'}; GET mock/complete → подписка сразу active +30 дней |
| OpenAI / AWS Rekognition модерация | banned-words regex + эскалация по отчётам (1→pending, 3+→temp, 5+→perm) |
| S3 (multer-s3) | локальная папка uploads/ + multer.diskStorage; имя файла uuid |
| Nodemailer SMTP | журнал писем в файл logs/emails.json (или console) |
| Twilio SMS | код в console/файл (проверка кода всё равно работает) |
| web-push / FCM | отключить; уведомления только в приложении |
| Sentry | winston-лог в файл; sentry.init — под DSN-флагом, оффлайн просто skip |
| Supabase | не используется вообще (MySQL локально) |
| Google Maps | заглушка координат/города или OSM |

## Как запускать локально
- MySQL: Laragon (порт 3306) или Docker: docker-compose.yml с mysql:8 (создать
  пользователя и БД, применить миграции migrate.js + seed)
- Бэк: cd server && npm install && node src/index.js → http://localhost:3002
- Фронт: npm install && npm run dev → http://localhost:8081 (VITE_API_URL=http://localhost:3002)
- Проверка: curl /health → {"status":"ok","db":"connected"}

## Как агент должен работать (этапы)
1. Создай скелет (docker-compose, package.json, schema.sql) одним patch files=[...]
2. Домен за доменом: auth → profile → matching → chat → premium(mock) → admin
3. После каждого домена: verify (node --check / tsc) + запуск сервера + curl
4. Тесты: vitest run (моки mysql2 — реальный пул в тестах не нужен)
5. В README: команды запуска, демо-аккаунты, пароль demo123456, note «работает полностью оффлайн»

## Ограничения модели
- qwen3:8b: файлы >300 строк читать по частям (read offset/limit), не давать
  «сделай всё сразу» — только один домен за раз
- После генерации всегда npm install + npm run build — исправлять ошибки
  компиляции, а не оставлять на пользователя
