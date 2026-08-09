# Dating App — Admin Panel

Админка как в SwiftMatch (server/src/routes/admin/*, src/pages/admin-*.tsx).
Модули: dashboard, users, analytics, reports, content, features, messaging,
monetization, moderation.

## Сервер
- Все роуты под app.use('/api/admin', adminAuth): если нет Bearer-токена — пропускает;
  иначе jwt.verify + SELECT role='admin' AND is_active=1 → req.admin
- admin/users: список с пагинацией и поиском, GET /api/admin/users?search=&page=&limit=;
  POST /api/admin/users/:id/ban → UPDATE users SET is_active=0 (мягкий бан);
  POST /api/admin/users/:id/unban; роль: role='admin'
- admin/dashboard: счётчики (users, matches, messages, revenue) + тренды за 7/30 дней
- admin/analytics: retention, revenue-mix по тарифам, активность по часам (prom-client /metrics для инфраструктуры)
- admin/reports: очередь модерации: отчёты (reports: reporter_id, reported_id, reason, status 'pending'|'resolved')
- admin/content: редактирование content_config (interests, dating_goals, education, banned_words, cities — JSON-поля)
- admin/features: CRUD feature_flags (name, enabled) — тумблеры фич
- admin/messaging: рассылка (сообщения всем / по фильтру)
- admin/monetization: сводка подписок, план-распределение
- Модерация: 1 отчёт → status pending; 3+ отчёта → временный бан; 5+ → перманент (is_active=0)

## Фронт (src/pages/admin*.tsx)
- Layout: sidebar-навигация по модулям, таблицы (TanStack Table или нативный table), 
  дашборд с recharts (LineChart/BarChart/PieChart), формы с zod + react-hook-form
- Auth: только role=admin (роут-гард; при 401 → redirect на /admin/login)

## Правила
- Никогда не возвращать password_hash в API-ответах (SELECT без этого поля).
- Все мутации писать в audit/activity_log: admin_id, action, target, timestamp.
- Кнопки «удалить» = мягкое удаление (is_active=0 / deleted_at), не DELETE из БД.
- Тесты: admin без токена 401; ban → юзер не может залогиниться (is_active=0).
