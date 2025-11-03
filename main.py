import sys
import os
from decimal import Decimal

from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QDate, QTime, QDateTime, Qt
from PySide6.QtSql import QSqlQuery

from db import connect_db

ROLE_ALIASES = {
    "client": "client",
    "клиент": "client",
    "salon": "salon",
    "салон": "salon",
    "admin": "admin",
    "админ": "admin",
    "администратор": "admin",
}

ROLE_CONFIGS = {
    "client": {"tabs": ("catalog", "book"), "title": "Smart-SPA — Клиент"},
    "salon": {"tabs": ("salon", "catalog"), "title": "Smart-SPA — Салон"},
    "admin": {"tabs": ("admin",), "title": "Smart-SPA — Администратор"},
}

current_user = None
current_role = None

def load_ui(path):
    if not os.path.exists(path):
        print("Файл не найден:", path)
    f = QFile(path)
    if not f.open(QFile.ReadOnly):
        print("Ошибка открытия:", path)
    ui = QUiLoader().load(f)
    f.close()
    return ui


def format_cell(value):
    if value is None:
        return ""
    if isinstance(value, QDateTime):
        return value.toString("dd.MM.yyyy HH:mm")
    if isinstance(value, QDate):
        return value.toString("dd.MM.yyyy")
    if isinstance(value, QTime):
        return value.toString("HH:mm")
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def populate_table(table, headers, rows):
    if table is None:
        return

    table.clear()
    table.setRowCount(len(rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)

    for row_idx, row in enumerate(rows):
        for col_idx, cell in enumerate(row):
            item = QTableWidgetItem(format_cell(cell))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row_idx, col_idx, item)

    header = table.horizontalHeader()
    if header is not None:
        header.setStretchLastSection(True)
    table.resizeColumnsToContents()


def show_db_error(query, context):
    error_text = query.lastError().text() if query.lastError().isValid() else ""
    details = f"{context}." if context else "Ошибка выполнения запроса."
    if error_text:
        details = f"{details}\n{error_text}"
    parent = globals().get("main") or globals().get("login")
    QMessageBox.critical(parent, "Ошибка БД", details)


def execute_select(sql, params=None, context=""):
    query = QSqlQuery()
    if params:
        query.prepare(sql)
        for value in params:
            query.addBindValue(value)
        if not query.exec():
            show_db_error(query, context)
            return None
    else:
        if not query.exec(sql):
            show_db_error(query, context)
            return None
    return query


def find_user(login_text):
    login_text = (login_text or "").strip()
    if not login_text:
        return None

    sql = (
        "SELECT u.id, u.full_name, r.code AS role_code, r.name AS role_name "
        "FROM users u "
        "JOIN roles r ON r.id = u.role_id "
        "WHERE u.phone = ? OR u.email = ? OR lower(u.full_name) = lower(?) "
        "LIMIT 1"
    )
    query = execute_select(sql, [login_text, login_text, login_text], "Поиск пользователя")
    if query is None:
        return None
    if query.next():
        return {
            "id": query.value("id"),
            "full_name": query.value("full_name"),
            "role_code": query.value("role_code"),
            "role_name": query.value("role_name"),
        }
    return None


def load_catalog():
    table = getattr(main, "tblCatalog", None)
    headers = ["Наименование", "Город", "Цена"]

    sql = (
        "SELECT srv.name AS service_name, salons.city AS city, "
        "       COALESCE(ss.price, srv.base_price) AS price "
        "FROM salon_services ss "
        "JOIN salons ON salons.id = ss.salon_id "
        "JOIN services srv ON srv.id = ss.service_id "
        "ORDER BY srv.name"
    )
    query = execute_select(sql, context="Загрузка каталога услуг")
    rows = []
    if query is not None:
        while query.next():
            rows.append([
                query.value("service_name"),
                query.value("city"),
                query.value("price"),
            ])
    populate_table(table, headers, rows)


def load_bookings(user_id):
    table = getattr(main, "tblBookings", None)
    headers = ["Номер", "Салон", "Услуга", "Начало", "Статус"]

    if user_id is None:
        populate_table(table, headers, [])
        return

    sql = (
        "SELECT a.id, salons.name AS salon_name, srv.name AS service_name, "
        "       slots.start_ts AS start_ts, a.status AS status "
        "FROM appointments a "
        "JOIN salons ON salons.id = a.salon_id "
        "JOIN services srv ON srv.id = a.service_id "
        "JOIN schedule_slots slots ON slots.id = a.slot_id "
        "WHERE a.client_id = ? "
        "ORDER BY slots.start_ts"
    )
    query = execute_select(sql, [user_id], "Загрузка записей клиента")
    rows = []
    if query is not None:
        while query.next():
            rows.append([
                query.value("id"),
                query.value("salon_name"),
                query.value("service_name"),
                query.value("start_ts"),
                query.value("status"),
            ])
    populate_table(table, headers, rows)


def load_salon_services():
    table = getattr(main, "tblServices", None)
    headers = ["Салон", "Услуга", "Длительность (мин)", "Цена"]

    sql = (
        "SELECT salons.name AS salon_name, srv.name AS service_name, "
        "       srv.duration_min AS duration_min, COALESCE(ss.price, srv.base_price) AS price "
        "FROM salon_services ss "
        "JOIN salons ON salons.id = ss.salon_id "
        "JOIN services srv ON srv.id = ss.service_id "
        "ORDER BY salons.name, srv.name"
    )
    query = execute_select(sql, context="Загрузка услуг салона")
    rows = []
    if query is not None:
        while query.next():
            rows.append([
                query.value("salon_name"),
                query.value("service_name"),
                query.value("duration_min"),
                query.value("price"),
            ])
    populate_table(table, headers, rows)


def load_users():
    table = getattr(main, "tblUsers", None)
    headers = ["ID", "ФИО", "Телефон", "Email", "Роль"]

    sql = (
        "SELECT u.id, u.full_name, u.phone, u.email, r.name AS role_name "
        "FROM users u "
        "JOIN roles r ON r.id = u.role_id "
        "ORDER BY u.created_at DESC"
    )
    query = execute_select(sql, context="Загрузка пользователей")
    rows = []
    if query is not None:
        while query.next():
            rows.append([
                query.value("id"),
                query.value("full_name"),
                query.value("phone"),
                query.value("email"),
                query.value("role_name"),
            ])
    populate_table(table, headers, rows)


def load_data_for_role(role, user):
    if role == "client":
        load_catalog()
        load_bookings(user["id"] if user else None)
    elif role == "salon":
        load_catalog()
        load_salon_services()
    elif role == "admin":
        load_catalog()
        load_salon_services()
        load_users()
    else:
        load_catalog()
        load_bookings(None)


def setup_role(role, user=None):
    global current_role

    tabs = {
        "catalog": getattr(main, "tabCatalog", None),
        "book": getattr(main, "tabBookings", None),
        "salon": getattr(main, "tabSalon", None),
        "admin": getattr(main, "tabAdmin", None),
    }

    for widget in tabs.values():
        if widget:
            index = main.twMain.indexOf(widget)
            if index != -1:
                main.twMain.setTabVisible(index, False)

    def show_tabs(keys, title):
        first_visible = None
        for key in keys:
            widget = tabs.get(key)
            if not widget:
                continue
            index = main.twMain.indexOf(widget)
            if index == -1:
                continue
            main.twMain.setTabVisible(index, True)
            if first_visible is None:
                first_visible = widget

        if first_visible is not None:
            main.twMain.setCurrentWidget(first_visible)

        window_title = title
        if user and user.get("full_name"):
            window_title = f"{title} ({user['full_name']})"
        main.setWindowTitle(window_title)

    role_key = (role or "").strip().casefold()
    canonical_role = ROLE_ALIASES.get(role_key)

    if canonical_role:
        config = ROLE_CONFIGS[canonical_role]
        show_tabs(config["tabs"], config["title"])
    else:
        available_tabs = tuple(key for key, widget in tabs.items() if widget)
        title = f"Smart-SPA — {role or 'Пользователь'}"
        show_tabs(available_tabs, title)

    current_role = canonical_role
    load_data_for_role(canonical_role, user)


def on_login():
    global current_user

    username = login.leUsername.text().strip()
    role_text = login.cbRole.currentText()

    if not username:
        QMessageBox.warning(login, "Ошибка", "Введите логин!")
        return

    user = find_user(username)
    if user is None:
        QMessageBox.information(
            login,
            "Информация",
            "Пользователь не найден в базе данных. Будут показаны общие данные.",
        )
        resolved_role = role_text
    else:
        resolved_role = user.get("role_code") or role_text

    current_user = user
    login.close()
    setup_role(resolved_role, user)
    main.show()


app = QApplication(sys.argv)

if not connect_db():
    sys.exit(1)

login = load_ui("ui/LoginWindow.ui")
main = load_ui("ui/MainWindow.ui")

login.btnLogin.clicked.connect(on_login)

login.show()
sys.exit(app.exec())
