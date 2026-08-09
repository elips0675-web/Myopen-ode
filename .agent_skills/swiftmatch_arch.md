# SwiftMatch Arch — сводка по референсному приложению

Use this skill as the architectural reference when cloning or building
dating/social apps like SwiftMatch1BD (`E:\swiftmatch1bdnoutprod`).

## Стек (точно из package.json образца)
- Фронт: React 18 + TypeScript + Vite (dev :8081, build dist/), Tailwind + shadcn/ui, react-router-dom v6, framer-motion (свайп-карточки), recharts (админ-аналитика), zod + react-hook-form, TanStack Query, socket.io-client, i18n ru/en
- Бэк: Node ESM ("type": "module"), Express 4, mysql2 (пул), Socket.IO 4 + @socket.io/redis-adapter, bull (очереди email/push/image), ioredis, bcryptjs, jsonwebtoken, stripe, express-rate-limit, helmet, cors, winston, nodemailer, twilio, web-push, firebase-admin (FCM), multer (+multer-s3), sharp, @aws-sdk/client-s3, @sentry/node, prom-client, swagger-jsdoc + swagger-ui-express
- API :3002, фронт :8081, MySQL (Laragon). Демо: 50 юзеров, 30 мэтчей, 200 сообщений; admin@mail.ru / user2@mail.ru / user4..user50@mail.ru пароль demo123456; user1@mail.ru забанен (is_active=0)

## Модули сервера (server/src/)
index.js (сборка: rateLimit 100/мин + 60/мин для auth, cors, helmet, request-id
+ создаёт req.log, /metrics, /api/premium/webhook raw body, express.json, static /uploads,
idempotency на create-checkout, dev-login id=2, /api/content без авторизации,
adminAuth-прослойка, 22 роутера, /health с SELECT 1, error-handler, initSentry,
initIO + 2 cleanup-таймера), db.js (pool), ws.js, redis.js, cache.js, queue.js
(bull), jobs/{email,image,push}.job.js, middleware/{auth,adminAuth,idempotency}.js,
routes/{auth,profile,upload,push,social,premium,sms,moderation,iap,fcm,location,
schedule,date-checkin,referral,gdpr,report,admin-moderation}.js,
routes/admin/{dashboard,users,analytics,reports,content,features,messaging,monetization}.js,
utils: ai-moderation, banned-words, audit, sentry (PII-filter), metrics (prom-client),
mail, sms, fcm, swagger, logger (request-id), seed.js

## Роуты (группы)
- auth: POST /api/auth/login, /register, /refresh, /dev-login; GET /api/content
- profile: анкета/фото/интересы; upload: MIME-whitelist image/* max 10MB
- social: лайки, мэтчи, чаты, реакции, сторис, группы, посты, блоки, приглашения
- premium: /api/premium/create-checkout (idempotency), webhook raw body, тарифы Plus/Gold/Platinum
- admin/*: dashboard, users, analytics, reports, content, features (7 флагов), messaging, monetization, moderation
- sms (twilio-проверка кода), iap (Stripe In-App), fcm, gdpr, location (фоновый GPS), schedule, checkin, referral

## WS-события (server/src/ws.js)
JWT из handshake.auth.token; сокет join `user:{id}`; Redis adapter для масштабирования.
on: webrtc:call-user / call-accepted / call-rejected / ice-candidate / end-call;
emit: webrtc:incoming-call / call-accepted / call-rejected / ice-candidate /
call-ended (при disconnect — reason 'disconnected'); чат: chat:message-deleted
(TTL-очистка каждые 10 c: messages.ttl_seconds). Проверка чекинов: 30 c.
События чатов (typing/read receipts/online/reactions) реализуются поверх тех же комнат user:{id}.

## Таблицы MySQL (53, из mysql_schema.sql)
users, user_profiles, user_photos, user_stories, interests, user_interests,
likes, matches, chats, chat_participants, messages, message_reactions,
group_categories, chat_groups, group_members, group_posts, group_post_likes,
group_post_comments, posts, post_images, post_comments, post_likes,
notifications, reports, contest_entries, activity_log, invites, saved_filters,
feature_flags, content_config, icebreaker_*, poll_*, user_sessions,
analytics_events, subscriptions, moderation_log, user_blocks, user_titles,
compatibility_scores, campaigns, date_schedules + spatial (миграция
005_add_spatial_location.sql: POINT SRID 4326, ST_Distance_Sphere).

## Паттерны безопасности
JWT (expiresIn 24h, refresh через createRefreshToken→user_sessions), bcrypt,
rate-limit раздельно (общий/auth), helmet, request-id + winston, idempotency-key
на платёжные POST, upload-валидация (MIME/размер), мягкие баны (is_active=0),
модерация: banned-words → auto-escalation (1 отчёт → pending, 3+ → временный бан, 5+ → перманент),
audit_log (activity_log) на мутации, soft delete (deleted_at/даты), Sentry PII-фильтр.

## Offline-замены (без интернета)
Redis/Bull → in-memory Map + setInterval, S3 → локальная папка uploads/, Sentry →
winston, OpenAI/AWS модерация → banned-words + эвристики, Stripe → mock-checkout
(эмуляция сессии), FCM/web-push → выключить, twilio → логирование кода в консоль.
