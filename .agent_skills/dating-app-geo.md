# Dating App — Geo (MySQL Spatial)

Геопоиск как в SwiftMatch (миграция 005_add_spatial_location.sql).
Поиск пользователей по радиусу + фоновое обновление GPS.

## Схема (миграция)
ALTER TABLE user_profiles ADD COLUMN location POINT SRID 4326 NULL;
- SRID 4326 обязателен для ST_Distance_Sphere в метрах
- CREATE SPATIAL INDEX idx_user_profiles_location ON user_profiles(location)
- При вставке: ST_SRID(POINT(lng, lat), 4326)

## Запрос «найти в радиусе R метров»
SELECT u.id, up.display_name,
       ST_Distance_Sphere(up.location, ST_SRID(POINT(?, ?), 4326)) AS dist_m
FROM users u
JOIN user_profiles up ON u.id = up.id
WHERE u.is_active = 1
  AND ST_Distance_Sphere(up.location, ST_SRID(POINT(?, ?), 4326)) <= ?
  AND u.id != ?
ORDER BY dist_m
LIMIT 50

## Сортировка/фильтры
- По возрастанию расстояния; join с likes для исключения уже лайкнутых
- saved_filters: сохранённые фильтры пользователя (возраст, город, цель знакомства)

## Фоновое обновление GPS
- POST /api/location (requireAuth): UPDATE user_profiles SET location=ST_SRID(POINT(?,?),4326) WHERE id=?
- Фронт: navigator.geolocation.watchPosition → throttle (напр. 5 мин) → POST
- На Android через Capacitor: @capacitor/geolocation с фоновым режимом

## Оффлайн
MySQL Spatial работает локально (Laragon/MySQL 8) — внешних сервисов не нужно.
Если MySQL нет вообще — fallback: колонки lat/lng DECIMAL(10,7) + формула
Хаверсина в SQL, индекс не нужен (медленнее, но работает).

## Правила
- Обрабатывать NULL location (пользователь не дал гео) — исключать из выборки.
- Не раскрывать точную точку другим юзерам — отдавать только dist_m и город.
- Тесты: вставка с координатами, выборка в радиусе (близкий есть, далёкого нет).
