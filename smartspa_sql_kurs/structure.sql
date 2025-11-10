SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;

CREATE SCHEMA IF NOT EXISTS smart_spa;
SET search_path TO smart_spa, public;

-- Роли и пользователи
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    phone VARCHAR(32) UNIQUE NOT NULL,
    email VARCHAR(200) UNIQUE,
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Салоны и мастера
CREATE TABLE IF NOT EXISTS salons (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    city VARCHAR(120) NOT NULL,
    address VARCHAR(300) NOT NULL,
    phone VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS masters (
    id BIGSERIAL PRIMARY KEY,
    salon_id BIGINT NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    full_name VARCHAR(200) NOT NULL,
    specialization VARCHAR(200),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Услуги и цены в салонах
CREATE TABLE IF NOT EXISTS services (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    base_price NUMERIC(10,2) NOT NULL CHECK (base_price >= 0),
    duration_min INTEGER NOT NULL CHECK (duration_min BETWEEN 15 AND 480)
);

CREATE TABLE IF NOT EXISTS salon_services (
    salon_id BIGINT NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    service_id BIGINT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    price NUMERIC(10,2) CHECK (price >= 0),
    PRIMARY KEY (salon_id, service_id)
);

-- Расписание и записи
CREATE TABLE IF NOT EXISTS schedule_slots (
    id BIGSERIAL PRIMARY KEY,
    master_id BIGINT NOT NULL REFERENCES masters(id) ON DELETE CASCADE,
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts   TIMESTAMPTZ NOT NULL,
    is_booked BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (end_ts > start_ts)
);

CREATE INDEX IF NOT EXISTS idx_schedule_master_start ON schedule_slots(master_id, start_ts);

CREATE TABLE IF NOT EXISTS appointments (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    salon_id  BIGINT NOT NULL REFERENCES salons(id) ON DELETE RESTRICT,
    master_id BIGINT NOT NULL REFERENCES masters(id) ON DELETE RESTRICT,
    service_id BIGINT NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    slot_id BIGINT NOT NULL UNIQUE REFERENCES schedule_slots(id) ON DELETE RESTRICT,
    status VARCHAR(30) NOT NULL CHECK (status IN ('ожидает подтверждения','подтверждена','отменена','завершена')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Отзывы
CREATE TABLE IF NOT EXISTS reviews (
    id BIGSERIAL PRIMARY KEY,
    salon_id BIGINT NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    client_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    appointment_id BIGINT UNIQUE REFERENCES appointments(id) ON DELETE SET NULL,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reviews_salon_created ON reviews (salon_id, created_at DESC);

-- Сервисные функции
CREATE OR REPLACE FUNCTION create_role(p_code VARCHAR, p_name VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
BEGIN
    INSERT INTO roles(code, name)
    VALUES (p_code, p_name)
    ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Проверка пересечения слотов
CREATE OR REPLACE FUNCTION запретить_пересечение_слотов()
RETURNS trigger AS $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM schedule_slots s
    WHERE s.master_id = NEW.master_id
      AND tstzrange(s.start_ts, s.end_ts, '[)') && tstzrange(NEW.start_ts, NEW.end_ts, '[)')
      AND s.id <> COALESCE(NEW.id, -1)
  ) THEN
    RAISE EXCEPTION 'Ошибка: данный слот пересекается с уже существующим временем работы мастера %', NEW.master_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_проверка_слотов ON schedule_slots;
CREATE TRIGGER trg_проверка_слотов
BEFORE INSERT OR UPDATE ON schedule_slots
FOR EACH ROW EXECUTE FUNCTION запретить_пересечение_слотов();

-- Бронирование
CREATE OR REPLACE FUNCTION забронировать_приём(
  p_клиент BIGINT,
  p_салон BIGINT,
  p_мастер BIGINT,
  p_услуга BIGINT,
  p_слот BIGINT
) RETURNS BIGINT AS $$
DECLARE
  v_id BIGINT;
BEGIN
  PERFORM 1 FROM schedule_slots WHERE id = p_слот AND master_id = p_мастер FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Ошибка: указанный слот не найден или не принадлежит выбранному мастеру.';
  END IF;

  IF EXISTS (SELECT 1 FROM schedule_slots WHERE id = p_слот AND is_booked) THEN
    RAISE EXCEPTION 'Ошибка: выбранный слот уже занят другим клиентом.';
  END IF;

  UPDATE schedule_slots SET is_booked = TRUE WHERE id = p_слот;

  INSERT INTO appointments(client_id, salon_id, master_id, service_id, slot_id, status)
  VALUES (p_клиент, p_салон, p_мастер, p_услуга, p_слот, 'подтверждена')
  RETURNING id INTO v_id;

  RAISE NOTICE 'Запись успешно создана. Номер записи: %', v_id;
  RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Отмена записи
CREATE OR REPLACE FUNCTION отменить_запись(p_id_записи BIGINT)
RETURNS void AS $$
DECLARE
  v_слот BIGINT;
BEGIN
  UPDATE appointments
     SET status = 'отменена'
   WHERE id = p_id_записи AND status IN ('ожидает подтверждения','подтверждена')
  RETURNING slot_id INTO v_слот;

  IF FOUND THEN
    UPDATE schedule_slots SET is_booked = FALSE WHERE id = v_слот;
    RAISE NOTICE 'Запись успешно отменена и слот освобождён.';
  ELSE
    RAISE NOTICE 'Отмена невозможна: запись не найдена или уже отменена/завершена.';
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Проверка отзыва после визита
CREATE OR REPLACE FUNCTION проверить_отзыв_после_визита()
RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM appointments a
    WHERE a.id = NEW.appointment_id
      AND a.client_id = NEW.client_id
      AND a.salon_id  = NEW.salon_id
      AND a.status    = 'завершена'
  ) THEN
    RAISE EXCEPTION 'Ошибка: отзыв можно оставить только после завершённого визита клиента.';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_проверка_отзыва ON reviews;
CREATE TRIGGER trg_проверка_отзыва
BEFORE INSERT OR UPDATE ON reviews
FOR EACH ROW EXECUTE FUNCTION проверить_отзыв_после_визита();

-- Базовые данные
SELECT create_role('client', 'Клиент');
SELECT create_role('salon', 'Салон');
SELECT create_role('admin', 'Администратор');

INSERT INTO users(full_name, phone, email, password_hash, role_id)
VALUES (
    'Иван Петров',
    '+79990000001',
    'ivan@example.com',
    'hash',
    (SELECT id FROM roles WHERE code = 'client')
)
ON CONFLICT (phone) DO NOTHING;

INSERT INTO salons(name, city, address, phone)
VALUES ('SPA «Лотос»','Москва','ул. Примерная, 1','+7 (499) 000-00-00')
ON CONFLICT (name) DO NOTHING;

INSERT INTO masters(salon_id, full_name, specialization)
VALUES (
    (SELECT id FROM salons WHERE name='SPA «Лотос»'),
    'Мария Смирнова',
    'Массаж'
)
ON CONFLICT (full_name, salon_id) DO NOTHING;

INSERT INTO services(name, description, base_price, duration_min)
VALUES ('Классический массаж','Расслабляющий массаж', 2500, 60)
ON CONFLICT (name) DO NOTHING;

INSERT INTO salon_services(salon_id, service_id, price)
VALUES (
    (SELECT id FROM salons WHERE name='SPA «Лотос»'),
    (SELECT id FROM services WHERE name='Классический массаж'),
    3000
)
ON CONFLICT (salon_id, service_id) DO NOTHING;

WITH params AS (
  SELECT
    (SELECT id FROM masters WHERE full_name='Мария Смирнова') AS master_id,
    (now()::date + 1) AS start_day,
    5 AS days,
    60 AS step_min
)
INSERT INTO schedule_slots(master_id, start_ts, end_ts)
SELECT p.master_id,
       ((p.start_day + d.dn) + t.ti)::timestamptz AS start_ts,
       ((p.start_day + d.dn) + t.ti + (p.step_min||' min')::interval)::timestamptz AS end_ts
FROM params p,
     generate_series(0, p.days-1) AS d(dn),
     generate_series(TIME '10:00', TIME '17:00', (p.step_min||' min')::interval) AS t(ti)
ON CONFLICT DO NOTHING;
