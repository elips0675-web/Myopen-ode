# Dating App — WebSocket (Socket.IO)

Реалтайм-архитектура как в SwiftMatch (server/src/ws.js). Чаты, онлайн-статус,
typing, read receipts, эмодзи-реакции, WebRTC-сигналинг.

## Подключение
- io = new Server(httpServer, { cors: {origin: CORS_ORIGIN||'*'}, pingInterval: 10000, pingTimeout: 5000 })
- Auth в middleware io.use: токен из socket.handshake.auth.token || query.token → jwt.verify → socket.userId; иначе next(new Error('Authentication required'|'Invalid token'))
- Каждый сокет join `user:{userId}` — это комната для адресной доставки
- Redis adapter (масштабирование): createAdapter(pubClient, subClient), если Redis недоступен — без адаптера (оффлайн-режим)

## Шаблон эвентов
- Отправка в комнату юзера: io.to(`user:${targetId}`).emit(event, payload)
- onAny → счётчик метрик (trackWsMessage)

## WebRTC-сигналинг (копировать паттерн)
- socket.on('webrtc:call-user', {targetUserId, sdp, type}): найти таргет-сокет, отметить socket.callPartnerId у обоих, emit 'webrtc:incoming-call'; если офлайн — emit 'webrtc:user-unavailable'
- 'webrtc:call-accepted' / 'call-rejected' / 'ice-candidate' — форвард в комнату user:{targetUserId}
- 'webrtc:end-call' → emit 'webrtc:call-ended' {from, reason}
- disconnect: если callPartnerId — emit 'webrtc:call-ended' {reason:'disconnected'}

## Чат-события (типовой набор поверх той же схемы)
- typing:start / typing:stop (payload: chatId, userId)
- chat:message:new (message object), chat:read-receipts {chatId, userId, lastReadAt}
- chat:reaction {messageId, userId, emoji}
- online: online-status {userId, online: bool}
- chat:message-deleted {chatId, messageIds} — при TTL-очистке (см. ниже)

## TTL-очистка сообщений (pattern из ws.js)
setInterval каждые 10 c: SELECT сообщения с ttl_seconds, где created_at <
NOW() - ttl_seconds → DELETE → для каждого чата io.to(`user:${userId}`).emit
'chat:message-deleted'. Плюс periodic-клинеры (напр. expiry check-in'ов раз в 30 c).

## Оффлайн
Redis adapter и Bull — опциональны: в локальном режиме без интернета использовать
in-memory Map<userId, Socket[]> и setInterval-очереди вместо bull/ioredis.

## Правила
- Валидировать payload на сервере (chatId число, текст ≤ N символов).
- Не принимать произвольные emit'ы от клиента для чужих комнат — всегда проверять членство (chat_participants).
- Тесты: подключение без токена 401, подписка на комнату, форвард call-user.
