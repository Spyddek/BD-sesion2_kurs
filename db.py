import os

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QMessageBox

def connect_db():
    db = QSqlDatabase.addDatabase("QPSQL")
    db.setHostName(os.environ.get("SMARTSPA_DB_HOST", "localhost"))
    db.setDatabaseName(os.environ.get("SMARTSPA_DB_NAME", "smart_spa"))

    username = os.environ.get("SMARTSPA_DB_USER")
    password = os.environ.get("SMARTSPA_DB_PASSWORD")
    if username:
        db.setUserName(username)
    if password:
        db.setPassword(password)

    port = os.environ.get("SMARTSPA_DB_PORT")
    try:
        db.setPort(int(port) if port else 5432)
    except (TypeError, ValueError):
        db.setPort(5432)

    if not db.open():
        error = db.lastError().text()
        if not username:
            error = (
                "Не задан пользователь базы данных. "
                "Укажите переменную окружения SMARTSPA_DB_USER.\n"
                f"{error}"
            )
        QMessageBox.critical(None, "Ошибка БД", error)
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
