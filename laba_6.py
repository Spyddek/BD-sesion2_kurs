import psycopg2

def run_sql(sql, fetch=False):
    with psycopg2.connect(
        dbname="demo",
        user="postgres",
        password="23565471",
        host="localhost",
        port=5432
    ) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        if fetch:
            return cur.fetchall()
        conn.commit()

run_sql("""
CREATE TABLE IF NOT EXISTS bookings.logs (
    id SERIAL PRIMARY KEY,
    table_name TEXT,
    action TEXT,
    old_value TEXT,
    new_value TEXT,
    change_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

triggers_sql = """

-- 1.1 Проверка мест
CREATE OR REPLACE FUNCTION bookings.check_seats_before_insert()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM bookings.seats WHERE aircraft_code=NEW.aircraft_code) = 0 THEN
        RAISE EXCEPTION 'Нет мест для самолёта %', NEW.aircraft_code;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_check_seats
BEFORE INSERT ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.check_seats_before_insert();

-- 1.2 Автоматическая отмена рейса при удалении всех билетов
CREATE OR REPLACE FUNCTION bookings.cancel_flight_after_delete()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE bookings.flights SET status='Cancelled'
    WHERE flight_id = OLD.flight_id
      AND NOT EXISTS (SELECT 1 FROM bookings.ticket_flights WHERE flight_id=OLD.flight_id);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_cancel_flight
AFTER DELETE ON bookings.ticket_flights
FOR EACH ROW EXECUTE FUNCTION bookings.cancel_flight_after_delete();

-- 1.3–1.4 Проверка минимального времени между рейсами
CREATE OR REPLACE FUNCTION bookings.check_time_gap()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM bookings.flights
        WHERE ABS(EXTRACT(EPOCH FROM (NEW.scheduled_departure - scheduled_departure))) < 3600
    ) THEN
        RAISE EXCEPTION 'Интервал между рейсами меньше 1 часа!';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_time_gap
BEFORE INSERT ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.check_time_gap();

-- 1.5 Подсчёт пассажиров не попавших
CREATE OR REPLACE FUNCTION bookings.count_missed_passengers()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO bookings.logs(table_name, action, old_value, new_value)
    VALUES ('flights','missed_passengers',OLD.flight_id::TEXT,'...');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_missed
AFTER UPDATE ON bookings.flights
FOR EACH STATEMENT EXECUTE FUNCTION bookings.count_missed_passengers();

-- 1.6 Запись изменений в лог
CREATE OR REPLACE FUNCTION bookings.log_changes()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO bookings.logs(table_name, action, old_value, new_value)
    VALUES (TG_TABLE_NAME, TG_OP, OLD::TEXT, NEW::TEXT);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_log_changes
AFTER INSERT OR UPDATE OR DELETE ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.log_changes();

-- 1.7 Обновление информации о пользователе (tickets)
CREATE OR REPLACE FUNCTION bookings.update_user_info()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO bookings.logs(table_name, action, old_value, new_value)
    VALUES ('tickets','update_user',OLD.passenger_name,NEW.passenger_name);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_update_user
AFTER UPDATE ON bookings.tickets
FOR EACH ROW EXECUTE FUNCTION bookings.update_user_info();

-- 1.8 Уведомление о задержке
CREATE OR REPLACE FUNCTION bookings.notify_delay()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.scheduled_departure <> NEW.scheduled_departure THEN
        INSERT INTO bookings.logs(table_name, action, old_value, new_value)
        VALUES ('flights','delay',OLD.scheduled_departure::TEXT,NEW.scheduled_departure::TEXT);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_delay
AFTER UPDATE ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.notify_delay();

-- 1.9 Проверка возраста пассажира (условная логика)
CREATE OR REPLACE FUNCTION bookings.check_age_before_booking()
RETURNS TRIGGER AS $$
BEGIN
    IF length(NEW.passenger_id) < 2 THEN
        RAISE EXCEPTION 'Пассажир слишком молод (условная проверка)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_check_age
BEFORE INSERT ON bookings.tickets
FOR EACH ROW EXECUTE FUNCTION bookings.check_age_before_booking();

-- 1.10 Автоматическое начисление миль
CREATE OR REPLACE FUNCTION bookings.add_miles()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO bookings.logs(table_name, action, old_value, new_value)
    VALUES ('ticket_flights','miles','+',NEW.amount::TEXT);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_add_miles
AFTER INSERT ON bookings.ticket_flights
FOR EACH ROW EXECUTE FUNCTION bookings.add_miles();

-- 1.11 Проверка билетов перед удалением рейса
CREATE OR REPLACE FUNCTION bookings.check_tickets_before_delete()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM bookings.ticket_flights WHERE flight_id=OLD.flight_id) THEN
        RAISE EXCEPTION 'Нельзя удалить рейс с билетами!';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_check_tickets
BEFORE DELETE ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.check_tickets_before_delete();

-- 1.12 Уведомление за сутки до рейса
CREATE OR REPLACE FUNCTION bookings.notify_day_before()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.scheduled_departure - now() < interval '24 hours' THEN
        INSERT INTO bookings.logs(table_name, action, old_value, new_value)
        VALUES ('flights','notify_day','-',NEW.flight_id::TEXT);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_notify_day
AFTER INSERT ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.notify_day_before();

-- 1.13 Проверка статуса при изменении времени
CREATE OR REPLACE FUNCTION bookings.check_status_on_time_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.scheduled_departure <> NEW.scheduled_departure THEN
        NEW.status := 'Rescheduled';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_status_time
BEFORE UPDATE ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.check_status_on_time_change();

-- 1.14 Автоштраф за отмену
CREATE OR REPLACE FUNCTION bookings.penalty_on_cancel()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status='Cancelled' THEN
        INSERT INTO bookings.logs(table_name, action, old_value, new_value)
        VALUES ('flights','penalty',OLD.flight_id::TEXT,'cancelled');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_penalty
AFTER UPDATE ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.penalty_on_cancel();

-- 1.15 Автоуведомление об изменении расписания
CREATE OR REPLACE FUNCTION bookings.schedule_change_notice()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO bookings.logs(table_name, action, old_value, new_value)
    VALUES ('flights','schedule_change',OLD.scheduled_departure::TEXT,NEW.scheduled_departure::TEXT);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_schedule
AFTER UPDATE ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.schedule_change_notice();

-- 1.16 Проверка бизнес-класса
CREATE OR REPLACE FUNCTION bookings.check_business_seats()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.fare_conditions='Business'
       AND NOT EXISTS (
           SELECT 1 FROM bookings.seats s
           JOIN bookings.flights f ON f.aircraft_code=s.aircraft_code
           WHERE f.flight_id=NEW.flight_id AND s.fare_conditions='Business'
       ) THEN
        RAISE EXCEPTION 'Нет мест бизнес-класса!';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_business
BEFORE INSERT ON bookings.ticket_flights
FOR EACH ROW EXECUTE FUNCTION bookings.check_business_seats();

-- 1.17 Скидки постоянным пассажирам
CREATE OR REPLACE FUNCTION bookings.discount_regulars()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM bookings.ticket_flights tf
        JOIN bookings.tickets t ON t.ticket_no=tf.ticket_no
        WHERE t.passenger_id=NEW.ticket_no
          AND tf.flight_id=NEW.flight_id) >= 3 THEN
        NEW.amount := NEW.amount * 0.9;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_discount
BEFORE INSERT ON bookings.ticket_flights
FOR EACH ROW EXECUTE FUNCTION bookings.discount_regulars();

-- 2. Каскадное удаление
CREATE OR REPLACE FUNCTION bookings.cascade_delete()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM bookings.ticket_flights WHERE flight_id=OLD.flight_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_cascade_delete
BEFORE DELETE ON bookings.flights
FOR EACH ROW EXECUTE FUNCTION bookings.cascade_delete();

-- 3. Логирование изменений (tickets)
CREATE OR REPLACE FUNCTION bookings.full_log()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO bookings.logs(table_name, action, old_value, new_value)
    VALUES (TG_TABLE_NAME, TG_OP, OLD::TEXT, NEW::TEXT);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_full_log
AFTER INSERT OR UPDATE OR DELETE ON bookings.tickets
FOR EACH ROW EXECUTE FUNCTION bookings.full_log();

"""
run_sql(triggers_sql)

print("✅ Все триггеры успешно созданы в demo.bookings")