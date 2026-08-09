# WebApp Skill (production-grade web apps, SwiftMatch-class)

Use this skill when the user asks to create, extend, or fix a production
web application (dating app, marketplace, dashboard, SaaS) — especially
when they say "like the app in E:\swiftmatch1bdnoutprod" or want a web app
with auth, matching, chat, payments, admin panel.

SIBLING SKILLS — chain them by task:
- `swiftmatch_arch` — полная архитектурная сводка образца (стек, модули, роуты, WS, таблицы)
- `dating-app-auth` / `dating-app-websocket` / `dating-app-payments` / `dating-app-geo` / `dating-app-admin` — доменные паттерны
- `dating-app-architecture` — слои бэкенда + паттерны (soft delete, audit, idempotency, rate-limit)
- `react-patterns` — фронтенд-паттерны (API-клиент, формы, свайп, чат, i18n)
- `generate-api` — few-shot шаблон нового API-модуля
- `offline-ollama` — замена внешних сервисов для ПОЛНОСТЬЮ локальной работы (без интернета)

## Reference project (study it before creating anything)
`E:\swiftmatch1bdnoutprod` — SwiftMatch1BD, a production dating app.
Read these files first (use read/glob):
- README.md — feature overview, run instructions, demo accounts
- package.json — exact frontend stack + versions
- server/package.json + server/src/index.js — backend stack, routes
- database/mysql_schema.sql — full schema (users, profiles, photos,
  interests, matches, chats, messages, reactions, subscriptions, reports,
  feature_flags)
- src/pages/ — page inventory (login, register, onboarding, Home swipe,
  search+filters, matches, chats, profile, premium, groups, contest,
  admin-*)

## Production stack to replicate (versions from the reference)
Frontend:
- React 18 + TypeScript 5 + Vite (dev/build), react-router-dom v6
- Tailwind CSS 3 + shadcn/ui (Radix primitives: dialog, tabs, select,
  toast, avatar, dropdown-menu, switch) + class-variance-authority
- framer-motion (swipe cards), recharts (admin analytics), sonner (toasts),
  zod + react-hook-form (forms), lucide-react (icons), date-fns
- i18n: Russian + English (src/locales/), all strings as translation keys
- State: TanStack React Query; realtime chat: socket.io-client

Backend (server/):
- Node.js + Express, MySQL via mysql2 pool (Laragon local, port 3002)
- Socket.IO: typing indicator, read receipts, online status, user:banned
- Auth: JWT (Bearer) + refresh tokens; dev-login for admin
- Monetization: Stripe Checkout (Plus/Gold/Platinum), idempotency middleware
- Rate limiting (express-rate-limit), Helmet security headers, request-id
- Uploads: MIME whitelist (image/*, 10MB) + S3 lazy-init fallback to disk
- Notifications: Nodemailer SMTP (retry 1s/2s/3s), web-push VAPID, FCM
- Moderation: banned-words regex + auto-escalation (1 report → pending,
  3+ → temp ban, 5+ → permanent)

Database (MySQL): schema.sql + numbered migrations (database/migrations/)
with migrate.js runner. Demo seed: 50 users, 30 matches, 200 messages.

## How to create a new app of this class
1. Read the reference stack files (above) — copy the architecture, NOT code.
2. Scaffold: write package.json, vite.config.ts, tailwind.config.ts,
   tsconfig, index.html; create src/ (pages/, components/, lib/, hooks/,
   types/, contexts/), server/ (src/routes/, src/middleware/), database/
   (schema + migrations + seed).
3. Backend first: db pool → auth (JWT) → core entities (users/profiles/
   matches/messages) → then features (search, chat, admin).
4. Frontend: layout + routing → auth pages → main flows (cards, matches,
   chat) → admin → polish (i18n, premium gating).
5. Verify: npm install + build (npm run build) in both server/ and root;
   run the API (node server/src/index.js) and check key endpoints return
   200; run unit tests when present (npm test / vitest run).
6. Keep the same quality bar: rate limiting, validation, backup before
   destructive edits, .env.example without secrets.

## Rules
- Never invent versions — read package.json of the reference.
- If the target folder is outside the agent workspace, use absolute paths
  (EXTRA_ROOTS must include it) and verify each write succeeded.
- Create README.md with run instructions and demo accounts like the
  reference does.
