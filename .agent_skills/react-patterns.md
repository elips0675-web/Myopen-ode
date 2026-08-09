# React Patterns (фронт продакшен-приложения)

Фронтенд-паттерны как в SwiftMatch (src/). Применять для страниц, API-клиента,
форм, чата, i18n.

## Структура src/
pages/ (по файлу на страницу: Home, search, matches, chats, profile, admin-*),
components/ (переиспользуемые: Card, SwipeCard, ChatBubble, Toast...),
hooks/ (useAuth, useSocket, useQuery-хуки), lib/ (api.ts, utils, native.ts),
contexts/ (AuthContext), locales/ (ru.ts, en.ts), types/ (d.ts), test/

## API-клиент
- fetch обёртка lib/api.ts с baseURL из import.meta.env.VITE_API_URL (дефолт http://localhost:3002)
- Интерцептор: Authorization: Bearer <token> из localStorage; при 401 → refresh → retry, при провале refresh → logout
- На мобиле: токен через @capacitor/preferences вместо localStorage (native.ts-адаптер)

## Роутинг и формы
- react-router-dom v6; роут-гарды: requireAuth (redirect /login), requireAdmin
- Формы: react-hook-form + zod resolver; ошибки с сервера в form state
- Данные: TanStack Query (useQuery/useMutation) с кэшем и инвалидацией
- UI: shadcn/ui (Radix): Button, Dialog, Tabs, Select, Toast(sonner), Avatar, DropdownMenu, Switch
- Стили: Tailwind (tailwind.config.ts), иконки lucide-react, анимации framer-motion
- Админ-графики: recharts (LineChart, BarChart, PieChart)

## Свайп-карточки (Home, pattern)
- framer-motion: drag='x', onDragEnd → если |offset.x| > 100 → лайк/дизлайк → POST /api/likes
- После каждого ответа — следующая карточка из очереди; при ~45% взаимных лайков — мэтч (toast + переход в чат)

## Чат (realtime)
- socket.io-client: подключение с {auth: {token}}, комнаты user:{id} на сервере
- useSocket хук: подписки на chat:message:new, typing:start/stop, chat:read-receipts, chat:reaction
- Оптимистичный UI: сообщение в список сразу + сброс при ошибке
- Печатающий индикатор по таймеру (emit typing:start раз в N сек, stop через 2-3 с)

## i18n
- locales/ru.ts, en.ts; объект переводов с ключами; выбор языка в настройках
- НЕ хардкодить строки UI — только ключи переводов

## Правила
- TypeScript strict; типы для всех API-ответов в types/.
- Никогда не показывать пароль/токен в localStorage как plain (минимум — httpOnly cookie на проде; в демо допустим localStorage с флагом).
- Страницы < 400 строк; крупные — разбивать на компоненты.
- Проверка: npm run build (tsc + vite) до завершения задачи.
