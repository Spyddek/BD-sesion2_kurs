import psycopg2
import random
import string

conn = psycopg2.connect(
    dbname="staff_control",
    user="postgres",
    password="23565471",
    host="localhost",
    port="5432"
)

def example_commit():
    cur = conn.cursor()
    cur.execute("BEGIN;")
    cur.execute("INSERT INTO departments (name, phone, location) VALUES ('Учебный отдел', '123-456', 'Москва');")
    conn.commit()
    cur.close()

def example_rollback():
    cur = conn.cursor()
    cur.execute("BEGIN;")
    cur.execute("INSERT INTO positions (title, hourly_rate) VALUES ('Ошибка должность', -100);")
    conn.commit()
    cur.close()

def example_savepoint():
    cur = conn.cursor()
    cur.execute("BEGIN;")
    cur.execute("INSERT INTO departments (name, phone, location) VALUES ('Отдел А', '111', 'СПб');")
    cur.execute("SAVEPOINT sp1;")
    cur.execute("INSERT INTO departments (name, phone, location) VALUES ('Отдел Б', '222', 'Екатеринбург');")
    cur.execute("INSERT INTO departments (name, phone, location) VALUES ('Отдел Б', '333', 'Казань');")
    conn.commit()
    cur.close()

def register_user(username):
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    cur = conn.cursor()
    conn.autocommit = True
    cur.execute(f"CREATE USER {username} WITH PASSWORD %s;", (password,))
    cur.execute(f"GRANT CONNECT ON DATABASE staff_control TO {username};")
    print(f"Создан пользователь {username}, пароль: {password}")
    cur.close()

if __name__ == "__main__":
    example_commit()
    example_rollback()
    example_savepoint()
    register_user("student1")
