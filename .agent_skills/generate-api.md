# Generate API — few-shot шаблон нового модуля

Как генерировать новый API-домен по паттерну SwiftMatch. Применять для любого
нового модуля (referral, video-calls, contest, groups и т.п.).

## Шаблон: «Создай API для {feature}»
1. Изучи существующие роуты: list server/src/routes/ + read похожего файла (в
   образце E:\swiftmatch1bdnoutprod или в текущем проекте)
2. Схема БД: добавь миграцию database/migrations/NNN_add_{feature}.sql —
   CREATE TABLE IF NOT EXISTS + индексы (см. пример ниже)
3. Создай server/src/routes/{feature}.js:
   - router.get('/api/{feature}/...', requireAuth, handler)
   - handler: параметры из req.params/query/body, prepared statements (?),
     ответ res.json({...}), ошибки res.status(400/401/404/500)
4. Зарегистрируй в index.js: import + app.use(...)
5. Фронт: страница/компонент + lib/api.ts вызовы
6. Тесты (Vitest + supertest): 200 успех, 400 валидация, 401 без токена

## Пример миграции
CREATE TABLE IF NOT EXISTS referrals (
  id INT PRIMARY KEY AUTO_INCREMENT,
  referrer_id INT NOT NULL,
  referee_id INT NOT NULL,
  status ENUM('pending','completed') DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (referrer_id) REFERENCES users(id),
  FOREIGN KEY (referee_id) REFERENCES users(id)
);

## Пример роута (паттерн)
import { Router } from 'express'
import pool from '../db.js'
import { requireAuth } from '../middleware/auth.js'
const router = Router()

router.get('/api/{feature}/stats', requireAuth, async (req, res) => {
  try {
    const [rows] = await pool.query('SELECT ... WHERE user_id = ?', [req.userId])
    res.json(rows)
  } catch (err) {
    req.log?.error?.('{feature} error: ' + err.message)
    res.status(500).json({ message: 'Internal server error' })
  }
})
export default router

## SQL-схема (общие правила, как в test_bench сценарии sql-schema)
- Таблицы users + messages: users(id, email, password_hash) — email UNIQUE NOT NULL,
  password_hash TEXT NOT NULL; messages(id, user_id, text) с внешним ключом.
- Внешний ключ: годится и явный `FOREIGN KEY (user_id) REFERENCES users(id)`,
  и инлайн `user_id INTEGER REFERENCES users(id)` — проверка бенчмарка принимает оба.
- В MySQL: ENGINE=InnoDB для FK; в SQLite: PRAGMA foreign_keys=ON на уровне соединения.
- Индексы на все внешние ключи (WHERE user_id = ? и JOIN-ы) — обязательно.
- Миграции: database/migrations/NNN_*.sql + регистрация в migrate.js (порядок по номеру).

## Пример: полная схема с внешним ключом (SQLite/MySQL)
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL
);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  text TEXT NOT NULL
);
CREATE INDEX idx_messages_user ON messages(user_id);

## Чек-лист модуля
- [ ] миграция + migrate.js регистрация
- [ ] роут зарегистрирован в index.js
- [ ] requireAuth на всех непубличных
- [ ] prepared statements (без конкатенации)
- [ ] 3+ теста
- [ ] verify (node --check) + npm test
