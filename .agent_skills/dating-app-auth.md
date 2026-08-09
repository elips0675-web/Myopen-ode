# Dating App — Auth (JWT flow)

Паттерн авторизации как в SwiftMatch (server/src/routes/auth.js, index.js).
Использовать для регистрации/login/refresh/logout/dev-login в любом клоне.

## Таблицы
- users: id, email (unique), password_hash, role ('user'|'admin'), is_active (1/0 — мягкий бан)
- user_sessions: user_id, refresh_token (hashed), expires_at, revoked_at

## Поток
1. register: bcrypt.hash(password, 10) → INSERT users (is_active=1) → access + refresh
2. login: SELECT ... WHERE email=? AND is_active=1 → bcrypt.compare → 401 "Invalid credentials" при ошибке
3. Access token: jwt.sign({userId, role}, JWT_SECRET, {expiresIn:'24h'})
4. Refresh: createRefreshToken(userId) — случайная строка, hash (sha256) в user_sessions, отдаём plain
5. POST /api/auth/refresh: принять refresh, sha256 → найти активную сессию → новые оба токена
6. logout: пометить revoked_at
7. dev-login (для демо/тестов): POST /api/auth/dev-login → jwt.sign({userId: 2, role:'user'}, JWT_SECRET, {expiresIn:'24h'}) — без пароля

## Middleware (server/src/middleware/)
- requireAuth: Authorization: Bearer <token> → jwt.verify → req.userId; 401 без/с плохим токеном
- requireAdmin: jwt.verify + SELECT role='admin' AND is_active=1 из users
- Admin-прослойка в index.js: если токена нет — пропускает (роуты сами решают), иначе проверяет role

## Rate limiting (обязательно)
- Общий: rateLimit({windowMs: 60_000, max: 100})
- На auth: rateLimit({windowMs: 60_000, max: 60})
- На платёжные POST: idempotency middleware

## Правила генерации
- Пароли хранить ТОЛЬКО как bcrypt hash. Секреты — из process.env (JWT_SECRET), не хардкодить.
- Все роуты кроме /api/content, /api/auth/* и /health — под requireAuth.
- Тесты: register 200, duplicate email 400, wrong password 401, refresh 200/401, dev-login 200.
