import psycopg2

conn = psycopg2.connect(
    dbname="smart_spa",
    user="postgres",
    password="23565471",
    host="localhost",
    port="5432"
)

cur = conn.cursor()

cur.execute("""
DROP TABLE IF EXISTS Отзывы CASCADE;
DROP TABLE IF EXISTS Бронирования CASCADE;
DROP TABLE IF EXISTS Услуги CASCADE;
DROP TABLE IF EXISTS Мастера CASCADE;
DROP TABLE IF EXISTS Салоны CASCADE;
DROP TABLE IF EXISTS Клиенты CASCADE;
""")

cur.execute("""

CREATE TABLE Клиенты (
    id_клиента      SERIAL PRIMARY KEY,
    фио             VARCHAR(100) NOT NULL,
    телефон         VARCHAR(20) UNIQUE NOT NULL,
    email           VARCHAR(100) UNIQUE NOT NULL,
    пароль          VARCHAR(255) NOT NULL,
    дата_регистрации DATE DEFAULT CURRENT_DATE
);

CREATE TABLE Салоны (
    id_салона   SERIAL PRIMARY KEY,
    название    VARCHAR(100) NOT NULL,
    адрес       VARCHAR(200) NOT NULL,
    город       VARCHAR(100) NOT NULL,
    телефон     VARCHAR(20),
    email       VARCHAR(100)
);

CREATE TABLE Мастера (
    id_мастера    SERIAL PRIMARY KEY,
    фио           VARCHAR(100) NOT NULL,
    специализация VARCHAR(100),
    id_салона     INT NOT NULL,
    CONSTRAINT fk_салон FOREIGN KEY (id_салона)
        REFERENCES Салоны(id_салона)
        ON DELETE CASCADE
);

CREATE TABLE Услуги (
    id_услуги    SERIAL PRIMARY KEY,
    название     VARCHAR(100) NOT NULL,
    описание     TEXT,
    цена         NUMERIC(10,2) NOT NULL,
    длительность INT NOT NULL,
    id_салона    INT NOT NULL,
    CONSTRAINT fk_услуга_салон FOREIGN KEY (id_салона)
        REFERENCES Салоны(id_салона)
        ON DELETE CASCADE
);

CREATE TABLE Бронирования (
    id_бронирования SERIAL PRIMARY KEY,
    id_клиента      INT NOT NULL,
    id_услуги       INT NOT NULL,
    id_мастера      INT,
    дата            DATE NOT NULL,
    время           TIME NOT NULL,
    статус          VARCHAR(20) DEFAULT 'Подтверждено'
                     CHECK (статус IN ('Подтверждено', 'Отменено', 'Выполнено')),
    CONSTRAINT fk_брон_клиент FOREIGN KEY (id_клиента)
        REFERENCES Клиенты(id_клиента)
        ON DELETE CASCADE,
    CONSTRAINT fk_брон_услуга FOREIGN KEY (id_услуги)
        REFERENCES Услуги(id_услуги)
        ON DELETE CASCADE,
    CONSTRAINT fk_брон_мастер FOREIGN KEY (id_мастера)
        REFERENCES Мастера(id_мастера)
        ON DELETE SET NULL
);

CREATE TABLE Отзывы (
    id_отзыва   SERIAL PRIMARY KEY,
    id_клиента  INT NOT NULL,
    id_салона   INT NOT NULL,
    текст       TEXT NOT NULL,
    рейтинг     INT CHECK (рейтинг BETWEEN 1 AND 5),
    дата        DATE DEFAULT CURRENT_DATE,
    CONSTRAINT fk_отзыв_клиент FOREIGN KEY (id_клиента)
        REFERENCES Клиенты(id_клиента)
        ON DELETE CASCADE,
    CONSTRAINT fk_отзыв_салон FOREIGN KEY (id_салона)
        REFERENCES Салоны(id_салона)
        ON DELETE CASCADE
);
""")

conn.commit()
cur.close()
conn.close()

print("База данных Smart-SPA успешно создана в PostgreSQL!")