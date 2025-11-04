import os

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QMessageBox


def _read_port(value: str, default: int = 5432) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        QMessageBox.warning(
            None,
            "Настройки БД",
            "Некорректное значение порта в переменной SMARTSPA_DB_PORT."
            f" Используется значение по умолчанию {default}.",
        )
        return default


def connect_db():
    db = QSqlDatabase.addDatabase("QPSQL")
    db.setHostName(os.getenv("SMARTSPA_DB_HOST", "localhost"))
    db.setDatabaseName(os.getenv("SMARTSPA_DB_NAME", "smart_spa"))
    db.setUserName(os.getenv("SMARTSPA_DB_USER", "postgres"))

    password = os.getenv("SMARTSPA_DB_PASSWORD")
    if password is None:
        QMessageBox.warning(
            None,
            "Настройки БД",
            "Переменная SMARTSPA_DB_PASSWORD не установлена."
            " Подключение может завершиться неудачей.",
        )
        password = ""
    db.setPassword(password)

    db_port = _read_port(os.getenv("SMARTSPA_DB_PORT", "5432"))
    db.setPort(db_port)

    if not db.open():
        QMessageBox.critical(None, "Ошибка БД", db.lastError().text())
        return False

    query = QSqlQuery()
    if not query.exec("SET search_path TO smart_spa, public;"):
        QMessageBox.warning(None, "Предупреждение БД", query.lastError().text())

    suppress_notice_query = QSqlQuery()
    if not suppress_notice_query.exec("SET client_min_messages TO warning;"):
        QMessageBox.warning(
            None,
            "Предупреждение БД",
            suppress_notice_query.lastError().text(),
        )
    return True
