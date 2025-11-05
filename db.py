from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QMessageBox
import os

def connect_db():
    db = QSqlDatabase.addDatabase("QPSQL")
    db.setHostName(os.getenv("PGHOST", "localhost"))
    db.setDatabaseName(os.getenv("PGDATABASE", "smart_spa"))
    db.setUserName(os.getenv("PGUSER", "postgres"))
    db.setPassword(os.getenv("PGPASSWORD", "23565471"))
    db.setPort(int(os.getenv("PGPORT", "5432")))

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
