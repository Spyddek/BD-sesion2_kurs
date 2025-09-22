import sqlite3

conn = sqlite3.connect("smart_spa.db")
cursor = conn.cursor()

cursor.executescript("""
DROP TABLE IF EXISTS Отзывы;
DROP TABLE IF EXISTS Бронирования;
DROP TABLE IF EXISTS Услуги;
DROP TABLE IF EXISTS Мастера;
DROP TABLE IF EXISTS Салоны;
DROP TABLE IF EXISTS Клиенты;
""")

cursor.executescript("""

-- Клиенты
CREATE TABLE Клиенты (
    id_клиента      INTEGER PRIMARY KEY AUTOINCREMENT,
    фио             TEXT NOT NULL,
    телефон         TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    пароль          TEXT NOT NULL,
    дата_регистрации DATE DEFAULT CURRENT_DATE
);

-- Салоны
CREATE TABLE Салоны (
    id_салона   INTEGER PRIMARY KEY AUTOINCREMENT,
    название    TEXT NOT NULL,
    адрес       TEXT NOT NULL,
    город       TEXT NOT NULL,
    телефон     TEXT,
    email       TEXT
);

-- Мастера
CREATE TABLE Мастера (
    id_мастера    INTEGER PRIMARY KEY AUTOINCREMENT,
    фио           TEXT NOT NULL,
    специализация TEXT,
    id_салона     INTEGER NOT NULL,
    FOREIGN KEY (id_салона) REFERENCES Салоны(id_салона) ON DELETE CASCADE
);

-- Услуги
CREATE TABLE Услуги (
    id_услуги   INTEGER PRIMARY KEY AUTOINCREMENT,
    название    TEXT NOT NULL,
    описание    TEXT,
    цена        REAL NOT NULL,
    длительность INTEGER NOT NULL,
    id_салона   INTEGER NOT NULL,
    FOREIGN KEY (id_салона) REFERENCES Салоны(id_салона) ON DELETE CASCADE
);

-- Бронирования
CREATE TABLE Бронирования (
    id_бронирования INTEGER PRIMARY KEY AUTOINCREMENT,
    id_клиента      INTEGER NOT NULL,
    id_услуги       INTEGER NOT NULL,
    id_мастера      INTEGER,
    дата            DATE NOT NULL,
    время           TIME NOT NULL,
    статус          TEXT DEFAULT 'Подтверждено' CHECK (статус IN ('Подтверждено', 'Отменено', 'Выполнено')),
    FOREIGN KEY (id_клиента) REFERENCES Клиенты(id_клиента) ON DELETE CASCADE,
    FOREIGN KEY (id_услуги) REFERENCES Услуги(id_услуги) ON DELETE CASCADE,
    FOREIGN KEY (id_мастера) REFERENCES Мастера(id_мастера) ON DELETE SET NULL
);

-- Отзывы
CREATE TABLE Отзывы (
    id_отзыва   INTEGER PRIMARY KEY AUTOINCREMENT,
    id_клиента  INTEGER NOT NULL,
    id_салона   INTEGER NOT NULL,
    текст       TEXT NOT NULL,
    рейтинг     INTEGER CHECK (рейтинг BETWEEN 1 AND 5),
    дата        DATE DEFAULT CURRENT_DATE,
    FOREIGN KEY (id_клиента) REFERENCES Клиенты(id_клиента) ON DELETE CASCADE,
    FOREIGN KEY (id_салона) REFERENCES Салоны(id_салона) ON DELETE CASCADE
);

""")

conn.commit()
conn.close()

print("База данных Smart-SPA успешно создана!")