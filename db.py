import os


_ENV_LOADED = False


def _ensure_env_loaded():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    env_path = os.environ.get("SMARTSPA_ENV_FILE", ".env")
    if not env_path:
        return

    if not os.path.isfile(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for line in env_file:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                if not key or key.startswith("#"):
                    continue
                value = value.strip().strip('"\'')
                os.environ.setdefault(key, value)
    except OSError:
        # Невалидный или недоступный .env — игнорируем, используем окружение процесса.
        pass

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QMessageBox

def connect_db():
    _ensure_env_loaded()
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
        hints = []
        if not username:
            hints.append(
                "Не задан пользователь базы данных (SMARTSPA_DB_USER)."
            )
        if not password and username:
            hints.append(
                "Для указанного пользователя отсутствует пароль (SMARTSPA_DB_PASSWORD)."
            )
        hints.append(
            "Можно создать файл .env рядом с приложением и указать в нём, например:\n"
            "SMARTSPA_DB_HOST=localhost\n"
            "SMARTSPA_DB_NAME=smart_spa\n"
            "SMARTSPA_DB_USER=app_user\n"
            "SMARTSPA_DB_PASSWORD=секретный_пароль"
        )
        hint_text = "\n\n".join(hints)
        if hint_text:
            error = f"{error}\n\n{hint_text}" if error else hint_text
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
