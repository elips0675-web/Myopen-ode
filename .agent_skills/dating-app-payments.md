# Dating App — Payments (Stripe, idempotency)

Подписки как в SwiftMatch (server/src/routes/premium.js, middleware/idempotency.js,
index.js). Тарифы: Plus / Gold / Platinum. Для оффлайн-копий — mock-режим.

## Порядок в Express (важно)
1. app.use('/api/premium/webhook', express.raw({type:'application/json'})) — ДО express.json()
2. express.json() для остального
3. app.use('/api/premium/create-checkout', idempotency) — защита повторных POST

## idempotency middleware (паттерн)
- Клиент шлёт заголовок Idempotency-Key (UUID) на платёжные POST
- Проверка: ключ уже обработан → вернуть сохранённый ответ (код+body), без повторной оплаты
- Иначе выполнить handler, сохранить (key → {status, body}) в Redis (оффлайн: Map) с TTL

## Checkout Session
- POST /api/premium/create-checkout {plan}: stripe.checkout.sessions.create({mode:'subscription', line_items:[{price: PRICES[plan]}], success_url, cancel_url, client_reference_id: userId, customer_email})
- Ответ: {url} — фронт делает redirect
- PRICES: Map plan → stripe price id из process.env (не хардкодить)

## Webhook (проверка подписки)
- route: /api/premium/webhook, verify с stripe.webhooks.constructEvent(body, sig, WEBHOOK_SECRET)
- события: checkout.session.completed → создать/продлить subscriptions (user_id, plan, status, current_period_end)
- 400 при невалидной подписи

## Premium gating
- Проверка активной подписки: SELECT * FROM subscriptions WHERE user_id=? AND status='active' AND current_period_end > NOW()
- Free-лимиты: лимит лайков/дней без подписки; при превышении → 402/403 с message 'Upgrade required'
- feature_flags: 7+ тумблеров в БД (таблица feature_flags: name, enabled), /api/admin/features — CRUD

## Оффлайн (без интернета)
- Mock: POST /api/premium/create-checkout возвращает {url: 'http://localhost:3002/api/premium/mock/complete?plan=gold'}
- GET /api/premium/mock/complete → создать подписку сразу (status 'active', период +30 дней)
- webhook-эндпоинт оставить заглушкой (200 ok)

## Тесты
- create-checkout с дублирующимся Idempotency-Key → один ответ
- webhook с плохой подписью → 400
- gating: free-юзер с превышенным лимитом → 402
