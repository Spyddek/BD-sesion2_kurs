from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QMessageBox

def connect_db():
    db = QSqlDatabase.addDatabase("QPSQL")
    db.setHostName("localhost")
    db.setDatabaseName("smart_spa")
    db.setUserName("postgres")
    db.setPassword("23565471")
    db.setPort(5432)

    if not db.open():
        QMessageBox.critical(None, "Ошибка БД", db.lastError().text())
        return False

    query = QSqlQuery()
    if not query.exec("SET search_path TO smart_spa, public;"):
        QMessageBox.warning(None, "Предупреждение БД", query.lastError().text())
    return True
