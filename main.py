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
catalog_filter_state = {"city": None, "search": ""}
catalog_filters_initialized = False

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


def populate_table(table, headers, rows, row_payloads=None):
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

        if row_payloads and row_idx < len(row_payloads):
            payload = row_payloads[row_idx]
            if payload is not None:
                item = table.item(row_idx, 0)
                if item is not None:
                    item.setData(Qt.UserRole, payload)

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


def populate_city_filter(selected_city=None):
    combo = getattr(main, "cbCity", None)
    if combo is None:
        return

    sql = "SELECT DISTINCT city FROM salons ORDER BY city"
    query = execute_select(sql, context="Загрузка списка городов")
    cities = []
    if query is not None:
        while query.next():
            city_value = query.value("city")
            if city_value:
                cities.append(city_value)

    combo.blockSignals(True)
    combo.clear()
    combo.addItem("Все города", "")
    for city in cities:
        combo.addItem(city, city)

    index = 0
    if selected_city:
        found_index = combo.findData(selected_city)
        if found_index != -1:
            index = found_index
    combo.setCurrentIndex(index)
    combo.blockSignals(False)


def load_catalog(update_filters=False):
    global catalog_filters_initialized

    table = getattr(main, "tblCatalog", None)
    headers = ["Наименование", "Город", "Цена"]
    search_edit = getattr(main, "leSearch", None)

    if update_filters or not catalog_filters_initialized:
        populate_city_filter(catalog_filter_state.get("city"))
        catalog_filters_initialized = True

    if search_edit is not None:
        current_text = catalog_filter_state.get("search", "")
        if search_edit.text() != current_text:
            search_edit.setText(current_text)

    sql = (
        "SELECT srv.name AS service_name, salons.name AS salon_name, salons.city AS city, "
        "       COALESCE(ss.price, srv.base_price) AS price, "
        "       salons.id AS salon_id, srv.id AS service_id "
        "FROM salon_services ss "
        "JOIN salons ON salons.id = ss.salon_id "
        "JOIN services srv ON srv.id = ss.service_id"
    )

    params = []
    conditions = []
    selected_city = catalog_filter_state.get("city")
    search_text = (catalog_filter_state.get("search", "") or "").strip()

    if selected_city:
        conditions.append("salons.city = ?")
        params.append(selected_city)

    if search_text:
        like_pattern = f"%{search_text}%"
        conditions.append("(srv.name ILIKE ? OR salons.name ILIKE ?)")
        params.extend([like_pattern, like_pattern])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY salons.city, salons.name, srv.name"

    query = execute_select(sql, params if params else None, context="Загрузка каталога услуг")
    rows = []
    payloads = []
    if query is not None:
        while query.next():
            rows.append([
                query.value("service_name"),
                query.value("city"),
                query.value("price"),
            ])
            payloads.append(
                {
                    "salon_id": query.value("salon_id"),
                    "service_id": query.value("service_id"),
                    "salon_name": query.value("salon_name"),
                    "service_name": query.value("service_name"),
                }
            )
    populate_table(table, headers, rows, payloads)


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


def find_next_available_slot(salon_id):
    if salon_id is None:
        return None

    sql = (
        "SELECT slots.id AS slot_id, slots.start_ts AS start_ts, m.id AS master_id "
        "FROM masters m "
        "JOIN schedule_slots slots ON slots.master_id = m.id "
        "WHERE m.salon_id = ? AND m.active = TRUE AND slots.is_booked = FALSE "
        "      AND slots.start_ts >= now() "
        "ORDER BY slots.start_ts "
        "LIMIT 1"
    )
    query = execute_select(sql, [salon_id], "Поиск свободного слота")
    if query is None:
        return None
    if query.next():
        return {
            "slot_id": query.value("slot_id"),
            "start_ts": query.value("start_ts"),
            "master_id": query.value("master_id"),
        }
    return None


def on_apply_filter():
    combo = getattr(main, "cbCity", None)
    search_edit = getattr(main, "leSearch", None)

    city_value = None
    if combo is not None and combo.count() > 0:
        data = combo.currentData()
        if data:
            city_value = data

    search_text = ""
    if search_edit is not None:
        search_text = search_edit.text().strip()

    catalog_filter_state["city"] = city_value
    catalog_filter_state["search"] = search_text

    load_catalog()


def on_book_now():
    if current_role != "client" or current_user is None:
        QMessageBox.information(
            main,
            "Запись недоступна",
            "Чтобы записаться, войдите как зарегистрированный клиент.",
        )
        return

    table = getattr(main, "tblCatalog", None)
    if table is None or table.rowCount() == 0:
        QMessageBox.information(main, "Запись", "Каталог пуст. Выберите услугу позже.")
        return

    selection_model = table.selectionModel()
    if selection_model is None or not selection_model.hasSelection():
        QMessageBox.information(main, "Запись", "Выберите услугу в каталоге.")
        return

    selected_rows = selection_model.selectedRows()
    if not selected_rows:
        QMessageBox.information(main, "Запись", "Выберите услугу в каталоге.")
        return

    row = selected_rows[0].row()
    item = table.item(row, 0)
    payload = item.data(Qt.UserRole) if item is not None else None
    if not payload:
        QMessageBox.warning(main, "Запись", "Не удалось определить выбранную услугу.")
        return

    salon_id = payload.get("salon_id")
    service_id = payload.get("service_id")
    if not salon_id or not service_id:
        QMessageBox.warning(main, "Запись", "Недостаточно данных для создания записи.")
        return

    slot_info = find_next_available_slot(salon_id)
    if slot_info is None:
        QMessageBox.information(
            main,
            "Свободные слоты",
            "Нет свободных времён для выбранного салона. Попробуйте выбрать другую услугу.",
        )
        return

    query = QSqlQuery()
    query.prepare("SELECT book_appointment(?, ?, ?, ?, ?)")
    query.addBindValue(current_user["id"])
    query.addBindValue(salon_id)
    query.addBindValue(slot_info["master_id"])
    query.addBindValue(service_id)
    query.addBindValue(slot_info["slot_id"])

    if not query.exec():
        show_db_error(query, "Создание записи")
        return

    appointment_id = None
    if query.next():
        appointment_id = query.value(0)

    load_bookings(current_user["id"])
    load_catalog()

    salon_name = payload.get("salon_name") or "салон"
    service_name = payload.get("service_name") or "услуга"
    start_text = format_cell(slot_info.get("start_ts"))

    message = (
        f"Вы записаны на {service_name} в {salon_name}."
        f"\nВремя начала: {start_text or 'уточните у администратора.'}"
    )
    if appointment_id:
        message = f"Запись №{appointment_id} создана.\n" + message

    QMessageBox.information(main, "Запись создана", message)

    bookings_tab = getattr(main, "tabBookings", None)
    if bookings_tab is not None:
        main.twMain.setCurrentWidget(bookings_tab)
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
        load_catalog(update_filters=True)
        load_bookings(user["id"] if user else None)
    elif role == "salon":
        load_catalog(update_filters=True)
        load_salon_services()
    elif role == "admin":
        load_catalog(update_filters=True)
        load_salon_services()
        load_users()
    else:
        load_catalog(update_filters=True)
        load_bookings(None)


def setup_role(role, user=None):
    global current_role, catalog_filters_initialized

    catalog_filters_initialized = False
    catalog_filter_state["city"] = None
    catalog_filter_state["search"] = ""

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
main.btnApply.clicked.connect(on_apply_filter)
main.btnBookNow.clicked.connect(on_book_now)

login.show()
sys.exit(app.exec())
