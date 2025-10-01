import psycopg2
import random
import string

DB_NAME = "staff_control"
DB_USER = "postgres"
DB_PASSWORD = "23565471"
DB_HOST = "localhost"
DB_PORT = "5432"

# Утилита для подключения
def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )

# 1. Фиксация транзакции
def transaction_commit_example():
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("INSERT INTO departments (name, phone, location) VALUES (%s, %s, %s)",
                            ("Тестовый отдел", "123-456", "Москва"))
                conn.commit()
                print("Транзакция успешно зафиксирована (COMMIT).")
            except Exception as e:
                conn.rollback()
                print("Ошибка, выполнен откат:", e)

# 2. Демонстрация отката
def transaction_rollback_example():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN;")
        cur.execute("INSERT INTO positions (title, hourly_rate) VALUES ('Ошибка-должность', -100)")
        # Ошибка из-за CHECK
        conn.commit()
    except Exception as e:
        print("Ошибка:", e)
        conn.rollback()
        print("Откат транзакции выполнен.")
    finally:
        cur.close()
        conn.close()

# 3. Использование точек сохранения
def savepoint_example():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN;")
        cur.execute("INSERT INTO departments (name, phone, location) VALUES ('Отдел A', '111', 'СПб');")
        cur.execute("SAVEPOINT sp1;")
        cur.execute("INSERT INTO departments (name, phone, location) VALUES ('Отдел B', '222', 'Екб');")
        # Ошибка — дублируем уникальное имя
        cur.execute("INSERT INTO departments (name, phone, location) VALUES ('Отдел B', '333', 'Казань');")
        conn.rollback()  # или можно rollback to savepoint sp1
    except Exception as e:
        print("Ошибка:", e)
        cur.execute("ROLLBACK TO SAVEPOINT sp1;")
        conn.commit()
        print("Откат к точке сохранения sp1.")
    finally:
        cur.close()
        conn.close()

# 4. Регистрация нового пользователя
def register_new_user(username):
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE USER {username} WITH PASSWORD %s;", (password,))
        cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {username};")
        print(f"Создан пользователь {username} с паролем {password}")
    except Exception as e:
        print("Ошибка при создании пользователя:", e)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    transaction_commit_example()
    transaction_rollback_example()
    savepoint_example()
    register_new_user("new_hr_user")