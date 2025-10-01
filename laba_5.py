import psycopg2

def create_connection():
    return psycopg2.connect(
        dbname="demo",
        user="postgres",
        password="23565471",
        host="localhost",
        port="5432"
    )

def run_and_show(conn, sql_create, sql_select, title):
    with conn.cursor() as cur:
        print(f"\n=== {title} ===")
        if sql_create.strip():
            cur.execute(sql_create)
            conn.commit()
        cur.execute(sql_select)
        rows = cur.fetchall()
        for r in rows:
            print(r)

def task1(conn):
    run_and_show(conn,
        """CREATE OR REPLACE VIEW available_flights AS
           SELECT * FROM bookings.flights WHERE status = 'On Time';""",
        "SELECT * FROM available_flights LIMIT 5;",
        "Задание 1"
    )

def task2(conn):
    run_and_show(conn,
        """CREATE TEMP VIEW airlines_avg_price AS
           SELECT f.aircraft_code AS plane_type, AVG(tf.amount) AS avg_price
           FROM bookings.ticket_flights tf
           JOIN bookings.flights f ON tf.flight_id = f.flight_id
           GROUP BY f.aircraft_code;""",
        "SELECT * FROM airlines_avg_price LIMIT 5;",
        "Задание 2"
    )

def task3(conn, min_price, max_price):
    run_and_show(conn,
        f"""CREATE TEMP VIEW flights_in_price AS
            SELECT f.flight_id, tf.amount
            FROM bookings.flights f
            JOIN bookings.ticket_flights tf ON f.flight_id=tf.flight_id
            WHERE tf.amount BETWEEN {min_price} AND {max_price};""",
        "SELECT * FROM flights_in_price LIMIT 5;",
        "Задание 3"
    )

def task4(conn, flight_id):
    run_and_show(conn,
        f"""CREATE TEMP VIEW seats_available AS
            SELECT seat_no
            FROM bookings.seats
            WHERE aircraft_code = (
                SELECT aircraft_code FROM bookings.flights WHERE flight_id={flight_id}
            )
            EXCEPT
            SELECT seat_no
            FROM bookings.boarding_passes
            WHERE flight_id={flight_id};""",
        "SELECT * FROM seats_available LIMIT 5;",
        "Задание 4"
    )

def task5(conn):
    run_and_show(conn,
        """CREATE TEMP VIEW passengers_next_month AS
           SELECT DISTINCT t.passenger_name
           FROM bookings.tickets t
           JOIN bookings.ticket_flights tf ON t.ticket_no=tf.ticket_no
           JOIN bookings.flights f ON tf.flight_id=f.flight_id
           WHERE f.scheduled_departure BETWEEN CURRENT_DATE
                 AND CURRENT_DATE + interval '1 month';""",
        "SELECT * FROM passengers_next_month LIMIT 5;",
        "Задание 5"
    )

def task6(conn):
    run_and_show(conn,
        """CREATE MATERIALIZED VIEW flights_by_season AS
           SELECT
             CASE
               WHEN EXTRACT(MONTH FROM scheduled_departure) IN (12,1,2) THEN 'Winter'
               WHEN EXTRACT(MONTH FROM scheduled_departure) IN (6,7,8) THEN 'Summer'
               ELSE 'Other'
             END AS season,
             COUNT(*) as total_flights
           FROM bookings.flights
           GROUP BY season;""",
        "SELECT * FROM flights_by_season;",
        "Задание 6"
    )

def task7(conn):
    run_and_show(conn,
        """CREATE TEMP VIEW low_occupancy AS
           SELECT f.flight_id,
                  COUNT(tf.ticket_no)::float / s.total_seats AS occupancy
           FROM bookings.flights f
           LEFT JOIN bookings.ticket_flights tf ON f.flight_id=tf.flight_id
           JOIN (
                SELECT aircraft_code, COUNT(*) AS total_seats
                FROM bookings.seats
                GROUP BY aircraft_code
           ) s ON f.aircraft_code = s.aircraft_code
           GROUP BY f.flight_id, s.total_seats
           HAVING COUNT(tf.ticket_no)::float / s.total_seats < 0.5;""",
        "SELECT * FROM low_occupancy LIMIT 5;",
        "Задание 7"
    )

def task8(conn):
    run_and_show(conn,
        """CREATE TEMP VIEW airlines_cancelled AS
           SELECT f.aircraft_code, COUNT(*) AS cancelled
           FROM bookings.flights f
           WHERE f.status='Cancelled'
           GROUP BY f.aircraft_code;""",
        "SELECT * FROM airlines_cancelled LIMIT 5;",
        "Задание 8"
    )

def task9(conn):
    run_and_show(conn,
        """CREATE MATERIALIZED VIEW flights_by_weekday AS
           SELECT EXTRACT(DOW FROM scheduled_departure) AS weekday, COUNT(*) AS total
           FROM bookings.flights
           GROUP BY weekday;""",
        "SELECT * FROM flights_by_weekday;",
        "Задание 9"
    )

def task10(conn):
    run_and_show(conn,
        """CREATE TEMP VIEW passengers_next_week AS
           SELECT DISTINCT t.passenger_name
           FROM bookings.tickets t
           JOIN bookings.ticket_flights tf ON t.ticket_no=tf.ticket_no
           JOIN bookings.flights f ON tf.flight_id=f.flight_id
           WHERE f.scheduled_departure BETWEEN CURRENT_DATE AND CURRENT_DATE + interval '7 days';""",
        "SELECT * FROM passengers_next_week LIMIT 5;",
        "Задание 10"
    )

def task11(conn):
    run_and_show(conn,
        """CREATE MATERIALIZED VIEW avg_flight_time AS
           SELECT departure_airport, arrival_airport,
                  AVG(actual_arrival - actual_departure) as avg_time
           FROM bookings.flights
           WHERE actual_arrival IS NOT NULL AND actual_departure IS NOT NULL
           GROUP BY departure_airport, arrival_airport;""",
        "SELECT * FROM avg_flight_time LIMIT 5;",
        "Задание 11"
    )

def task12(conn):
    run_and_show(conn,
        """CREATE MATERIALIZED VIEW busiest_airports AS
           SELECT arrival_airport, COUNT(*) as total_arrivals
           FROM bookings.flights
           GROUP BY arrival_airport
           ORDER BY total_arrivals DESC;""",
        "SELECT * FROM busiest_airports LIMIT 5;",
        "Задание 12"
    )

def task13(conn):
    with conn.cursor() as cur:
        cur.execute("""CREATE OR REPLACE RECURSIVE VIEW nums_1_10(n) AS
                        SELECT 1 UNION ALL SELECT n+1 FROM nums_1_10 WHERE n<10;""")
        cur.execute("""CREATE OR REPLACE RECURSIVE VIEW nums_even(n) AS
                        SELECT 2 UNION ALL SELECT n+2 FROM nums_even WHERE n<20;""")
        cur.execute("""CREATE OR REPLACE RECURSIVE VIEW fib(n, a, b) AS
                        SELECT 1, 0, 1 UNION ALL SELECT n+1, b, a+b FROM fib WHERE n<10;""")
        cur.execute("""CREATE OR REPLACE RECURSIVE VIEW pow2(n, val) AS
                        SELECT 1, 2 UNION ALL SELECT n+1, val*2 FROM pow2 WHERE n<10;""")
        cur.execute("""CREATE OR REPLACE RECURSIVE VIEW countdown(n) AS
                        SELECT 10 UNION ALL SELECT n-1 FROM countdown WHERE n>0;""")
        conn.commit()
    run_and_show(conn, "", "SELECT * FROM nums_1_10;", "Задание 13: nums_1_10")
    run_and_show(conn, "", "SELECT * FROM fib;", "Задание 13: fib")

if __name__ == "__main__":
    conn = create_connection()
    task1(conn)
    task2(conn)
    task3(conn, 100, 500)
    task4(conn, 1)
    task5(conn)
    task6(conn)
    task7(conn)
    task8(conn)
    task9(conn)
    task10(conn)
    task11(conn)
    task12(conn)
    task13(conn)
    conn.close()