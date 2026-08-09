# Dating App — Backend Architecture

Слои и паттерны бэкенда как в SwiftMatch. Применять для ЛЮБОГО нового сервера
(Express/MySQL), не только для dating-приложений.

## Слои (структура server/src/)
1. index.js — сборка приложения: middleware (cors, helmet, rate-limit, request-id,
   raw body для webhooks, static uploads), регистрация роутеров, /health, error-handler,
   graceful shutdown (SIGTERM → close pool/redis/httpServer)
2. routes/ — Express-роутеры (один файл на домен: auth, profile, social, premium...)
3. middleware/ — auth, adminAuth, idempotency
4. services/utils: queue.js (Bull: email/push/image), cache.js (Redis), logger.js
   (request-id + winston), mail.js (Nodemailer + retry), metrics.js (prom-client),
   ai-moderation.js, banned-words.js, audit.js, sentry.js (PII-filter), swagger.js
5. db.js — единственный mysql2/promise пул (exports pool; query: pool.query)

## Паттерны (копировать как есть, адаптируя имена)
- **Soft Delete**: колонки deleted_at/is_active на всех сущностях; удаление = UPDATE,
  выборки всегда с условием is_active=1
- **Audit Log**: audit.js — хелпер log(action, targetType, targetId, adminId?);
  INSERT в activity_log; вызывается на каждой мутации
- **Request-ID + structured log**: req.rid = x-request-id || randomUUID(),
  res.setHeader('X-Request-Id'), req.log = createLogger(req.rid) — каждая ошибка
  трассируется по id
- **Idempotency** на платёжные POST (см. dating-app-payments)
- **Rate limit**: общий limiter + отдельный на auth-роуты
- **Очереди**: Bull(redis) для email/push/image jobs; в оффлайне — Map + setInterval
- **Error-handler**: один app.use((err,req,res,next) => 500 {message:'Internal server error'})
  с логированием; никогда не отдавать stack trace клиенту
- **Uploads**: multer, MIME-whitelist (image/*), лимит 10MB, имя файла = uuid,
  sharp для ресайза; хранение локально uploads/ (S3 — опционально)
- **Модерация**: banned-words regex + эскалация по числу отчётов (1→pending, 3+→temp ban, 5+→perm)

## Graceful shutdown
process.on('SIGTERM') → disconnectRedis() → pool.end() → httpServer.close(() => process.exit(0))

## Правила генерации
- ESM ("type": "module"), все imports с .js суффиксами.
- Параметры запросов через prepared statements (?) — НИКОГДА не конкатенировать.
- Секреты из process.env через dotenv; .env.example без реальных значений.
- Каждый роут-файл < 200 строк — при разрастании разбивать на middleware/utils.
- Тесты (Vitest + supertest): по файлу на роут-домен, мок пула mysql2.
