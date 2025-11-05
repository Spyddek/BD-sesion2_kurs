import sys
import os
import base64
import hashlib
import hmac
from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QTableWidgetItem,
    QTableWidget,
    QInputDialog,
    QDialog,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
)
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
    "client": {"tabs": ("catalog", "book", "user"), "title": "Smart-SPA — Клиент"},
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

    table.blockSignals(True)
    table.setSortingEnabled(False)
    table.clear()
    table.setRowCount(len(rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)

    if isinstance(table, QTableWidget):
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)

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
    table.setSortingEnabled(True)
    table.blockSignals(False)


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


def execute_action(sql, params=None, context=""):
    query = QSqlQuery()
    if params:
        query.prepare(sql)
        for value in params:
            query.addBindValue(value)
        if not query.exec():
            show_db_error(query, context)
            return False
    else:
        if not query.exec(sql):
            show_db_error(query, context)
            return False
    return True


def find_user(login_text):
    login_text = (login_text or "").strip()
    if not login_text:
        return None

    sql = (
        "SELECT u.id, u.full_name, u.password_hash, r.code AS role_code, r.name AS role_name "
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
            "password_hash": query.value("password_hash"),
            "role_code": query.value("role_code"),
            "role_name": query.value("role_name"),
        }
    return None


def verify_password(plain_password, stored_hash):
    if not stored_hash:
        return False

    plain_password = plain_password or ""
    stored_hash = str(stored_hash)

    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _algorithm, iterations, salt, hash_value = stored_hash.split("$", 3)
            iterations = int(iterations)
        except (ValueError, TypeError):
            return False

        try:
            derived_key = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                iterations,
            )
        except ValueError:
            return False

        calculated = base64.b64encode(derived_key).decode("ascii")
        return hmac.compare_digest(calculated, hash_value)

    return hmac.compare_digest(stored_hash, plain_password)


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


def load_user_info(user_id):
    table = getattr(main, "tblUserInfo", None)
    headers = ["ФИО", "Email", "Тел"]

    if table is None:
        return

    if hasattr(table, "verticalHeader"):
        header = table.verticalHeader()
        if header is not None:
            header.setVisible(False)

    if user_id is None:
        populate_table(table, headers, [])
        return

    query = execute_select(
        "SELECT full_name, email, phone FROM users WHERE id = ?",
        [user_id],
        "Загрузка данных клиента",
    )

    rows = []
    if query is not None and query.next():
        rows.append([
            query.value("full_name"),
            query.value("email"),
            query.value("phone"),
        ])

    populate_table(table, headers, rows)


def fetch_available_slots(salon_id, limit=20):
    if salon_id is None:
        return []

    sql = (
        "SELECT slots.id AS slot_id, slots.start_ts AS start_ts, slots.end_ts AS end_ts, "
        "       m.id AS master_id, m.full_name AS master_name, m.specialization AS specialization "
        "FROM masters m "
        "JOIN schedule_slots slots ON slots.master_id = m.id "
        "LEFT JOIN appointments a ON a.slot_id = slots.id "
        "WHERE m.salon_id = ? AND m.active = TRUE AND slots.is_booked = FALSE "
        "      AND a.slot_id IS NULL AND slots.start_ts >= now() "
        "ORDER BY slots.start_ts "
        "LIMIT ?"
    )
    query = execute_select(sql, [salon_id, limit], "Поиск свободных слотов")
    slots = []
    if query is not None:
        while query.next():
            slots.append(
                {
                    "slot_id": query.value("slot_id"),
                    "start_ts": query.value("start_ts"),
                    "end_ts": query.value("end_ts"),
                    "master_id": query.value("master_id"),
                    "master_name": query.value("master_name"),
                    "specialization": query.value("specialization"),
                }
            )
    return slots


def fetch_salons():
    sql = "SELECT id, name, city FROM salons ORDER BY name"
    query = execute_select(sql, context="Загрузка списка салонов")
    salons = []
    if query is not None:
        while query.next():
            salons.append(
                {
                    "id": query.value("id"),
                    "name": query.value("name"),
                    "city": query.value("city"),
                }
            )
    return salons


def fetch_available_services_for_salon(salon_id):
    if salon_id is None:
        return []

    sql = (
        "SELECT s.id AS service_id, s.name AS service_name, s.duration_min, s.base_price "
        "FROM services s "
        "WHERE NOT EXISTS ("
        "    SELECT 1 FROM salon_services ss "
        "    WHERE ss.salon_id = ? AND ss.service_id = s.id"
        ") "
        "ORDER BY s.name"
    )
    query = execute_select(sql, [salon_id], "Доступные услуги для салона")
    services = []
    if query is not None:
        while query.next():
            services.append(
                {
                    "id": query.value("service_id"),
                    "name": query.value("service_name"),
                    "duration_min": query.value("duration_min"),
                    "base_price": query.value("base_price"),
                }
            )
    return services


def format_price(value):
    text = format_cell(value)
    if not text:
        text = "0.00"
    if "₽" not in text:
        text += " ₽"
    return text


def parse_decimal(value, fallback=Decimal("0")):
    if isinstance(value, (Decimal, float, int)):
        return Decimal(str(value))

    text = (value or "").strip()
    text = text.replace("₽", "").replace(" ", "").replace(",", ".")
    if not text:
        return fallback
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return fallback


def normalize_phone(phone):
    digits = (phone or "").strip()
    if not digits:
        return ""

    for ch in " ()-":
        digits = digits.replace(ch, "")

    if digits.startswith("+"):
        rest = digits[1:]
        if not rest.isdigit():
            return None
    elif not digits.isdigit():
        return None

    return digits


class EditUserDialog(QDialog):
    def __init__(self, parent=None, full_name="", email="", phone=""):
        super().__init__(parent)
        self.setWindowTitle("Изменение данных")
        self.setModal(True)

        layout = QFormLayout(self)

        self.full_name_edit = QLineEdit(full_name or "")
        self.full_name_edit.setObjectName("fullNameEdit")
        layout.addRow("ФИО", self.full_name_edit)

        self.email_edit = QLineEdit(email or "")
        self.email_edit.setObjectName("emailEdit")
        self.email_edit.setPlaceholderText("name@example.com")
        layout.addRow("Email", self.email_edit)

        self.phone_edit = QLineEdit(phone or "")
        self.phone_edit.setObjectName("phoneEdit")
        self.phone_edit.setPlaceholderText("+79991234567")
        layout.addRow("Телефон", self.phone_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._result = None

    def accept(self):
        full_name = self.full_name_edit.text().strip()
        if not full_name:
            QMessageBox.warning(self, "Ошибка", "Укажите ФИО.")
            self.full_name_edit.setFocus()
            return

        email = self.email_edit.text().strip()
        if email and "@" not in email:
            QMessageBox.warning(self, "Ошибка", "Введите корректный email.")
            self.email_edit.setFocus()
            self.email_edit.selectAll()
            return

        phone_text = self.phone_edit.text().strip()
        if phone_text:
            normalized = normalize_phone(phone_text)
            if normalized is None:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Телефон может содержать только цифры и, при необходимости, знак '+'.",
                )
                self.phone_edit.setFocus()
                self.phone_edit.selectAll()
                return
            phone_text = normalized

        self._result = {
            "full_name": full_name,
            "email": email,
            "phone": phone_text,
        }

        super().accept()

    def get_data(self):
        return self._result


def choose_slot_for_booking(slots, salon_name="", service_name=""):
    if not slots:
        return None

    options = []
    for index, slot in enumerate(slots, start=1):
        start_text = format_cell(slot.get("start_ts"))
        end_text = format_cell(slot.get("end_ts"))
        time_text = start_text
        if start_text and end_text and end_text != start_text:
            time_text = f"{start_text} – {end_text}"

        master_parts = []
        master_name = slot.get("master_name")
        specialization = slot.get("specialization")
        if master_name:
            master_parts.append(master_name)
        if specialization:
            master_parts.append(specialization)
        master_text = " — ".join(master_parts)

        option_text = f"{index}. {time_text}"
        if master_text:
            option_text += f" • {master_text}"
        options.append(option_text)

    label_parts = []
    if salon_name:
        label_parts.append(f"Салон: {salon_name}")
    if service_name:
        label_parts.append(f"Услуга: {service_name}")
    label_parts.append("Выберите время:")
    label = "\n".join(label_parts)

    selection, accepted = QInputDialog.getItem(
        main,
        "Выбор времени",
        label,
        options,
        0,
        False,
    )
    if not accepted:
        return None
    try:
        selected_index = options.index(selection)
    except ValueError:
        return None
    return slots[selected_index]


def read_catalog_filters_from_ui():
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

    return city_value, search_text


def on_apply_filter():
    city_value, search_text = read_catalog_filters_from_ui()
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

    available_slots = fetch_available_slots(salon_id)
    if not available_slots:
        QMessageBox.information(
            main,
            "Свободные слоты",
            "Нет свободных времён для выбранного салона. Попробуйте выбрать другую услугу.",
        )
        return

    slot_info = choose_slot_for_booking(
        available_slots,
        payload.get("salon_name"),
        payload.get("service_name"),
    )
    if slot_info is None:
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
    end_text = format_cell(slot_info.get("end_ts"))
    if end_text and end_text != start_text:
        message += f"\nВремя окончания: {end_text}"

    master_name = slot_info.get("master_name")
    if master_name:
        specialization = slot_info.get("specialization")
        master_line = master_name
        if specialization:
            master_line += f" ({specialization})"
        message += f"\nМастер: {master_line}"
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
        "SELECT salons.id AS salon_id, salons.name AS salon_name, salons.city AS city, "
        "       srv.id AS service_id, srv.name AS service_name, "
        "       srv.duration_min AS duration_min, COALESCE(ss.price, srv.base_price) AS price "
        "FROM salon_services ss "
        "JOIN salons ON salons.id = ss.salon_id "
        "JOIN services srv ON srv.id = ss.service_id "
        "ORDER BY salons.name, srv.name"
    )
    query = execute_select(sql, context="Загрузка услуг салона")
    rows = []
    payloads = []
    if query is not None:
        while query.next():
            salon_name = query.value("salon_name")
            city = query.value("city")
            display_name = salon_name
            if city and city not in (salon_name or ""):
                display_name = f"{salon_name} ({city})"
            rows.append([
                display_name,
                query.value("service_name"),
                query.value("duration_min"),
                query.value("price"),
            ])
            payloads.append(
                {
                    "salon_id": query.value("salon_id"),
                    "service_id": query.value("service_id"),
                    "salon_name": salon_name,
                    "city": city,
                    "service_name": query.value("service_name"),
                    "price": query.value("price"),
                }
            )
    populate_table(table, headers, rows, payloads)


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


def get_selected_row_payload(table):
    if table is None or table.rowCount() == 0:
        return None

    selection_model = table.selectionModel()
    if selection_model is None or not selection_model.hasSelection():
        return None

    selected_rows = selection_model.selectedRows()
    if not selected_rows:
        return None

    row = selected_rows[0].row()
    item = table.item(row, 0)
    if item is None:
        return None
    payload = item.data(Qt.UserRole)
    if payload is None:
        return None
    return row, payload


def load_data_for_role(role, user):
    if role == "client":
        load_catalog(update_filters=True)
        load_bookings(user["id"] if user else None)
        load_user_info(user["id"] if user else None)
    elif role == "salon":
        load_catalog(update_filters=True)
        load_salon_services()
        load_user_info(None)
    elif role == "admin":
        load_catalog(update_filters=True)
        load_salon_services()
        load_users()
        load_user_info(None)
    else:
        load_catalog(update_filters=True)
        load_bookings(None)
        load_user_info(None)


def configure_role_controls(role):
    role = role or ""

    client_only = role == "client"
    manage_services = role in {"salon", "admin"}
    is_admin = role == "admin"

    if hasattr(main, "btnBookNow"):
        main.btnBookNow.setEnabled(client_only)
    if hasattr(main, "btnAddBooking"):
        main.btnAddBooking.setEnabled(client_only)
    if hasattr(main, "btnCancelBooking"):
        main.btnCancelBooking.setEnabled(client_only)

    if hasattr(main, "btnAddService"):
        main.btnAddService.setEnabled(manage_services)
    if hasattr(main, "btnDeleteService"):
        main.btnDeleteService.setEnabled(manage_services)
    if hasattr(main, "btnSaveService"):
        main.btnSaveService.setEnabled(manage_services)
    if hasattr(main, "btnResetInfo"):
        can_edit_profile = client_only and current_user is not None and current_user.get("id")
        main.btnResetInfo.setEnabled(bool(can_edit_profile))

    if hasattr(main, "btnDeleteUser"):
        main.btnDeleteUser.setEnabled(is_admin)
    if hasattr(main, "btnApproveReview"):
        main.btnApproveReview.setEnabled(False)


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
        "user": getattr(main, "tabUser", None),
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
    configure_role_controls(canonical_role)
    load_data_for_role(canonical_role, user)


def on_login():
    global current_user

    username = login.leUsername.text().strip()
    role_text = login.cbRole.currentText()

    if not username:
        QMessageBox.warning(login, "Ошибка", "Введите логин!")
        return

    user_record = find_user(username)
    password = login.lePassword.text()
    user = None
    if user_record is None:
        QMessageBox.information(
            login,
            "Информация",
            "Пользователь не найден в базе данных. Будут показаны общие данные.",
        )
        resolved_role = role_text
    else:
        if not password:
            QMessageBox.warning(login, "Ошибка", "Введите пароль!")
            login.lePassword.setFocus()
            return

        stored_hash = user_record.get("password_hash")
        if not verify_password(password, stored_hash):
            QMessageBox.warning(login, "Ошибка", "Неверный пароль.")
            login.lePassword.selectAll()
            login.lePassword.setFocus()
            return

        user = {key: value for key, value in user_record.items() if key != "password_hash"}
        resolved_role = user.get("role_code") or role_text

    current_user = user
    login.close()
    login.lePassword.clear()
    setup_role(resolved_role, user)
    main.show()


app = QApplication(sys.argv)

if not connect_db():
    sys.exit(1)

login = load_ui("ui/LoginWindow.ui")
main = load_ui("ui/MainWindow.ui")

login.btnLogin.clicked.connect(on_login)
def on_cancel_booking():
    if current_user is None:
        QMessageBox.information(
            main,
            "Отмена записи",
            "Чтобы отменить запись, сначала войдите в систему.",
        )
        return

    table = getattr(main, "tblBookings", None)
    if table is None or table.rowCount() == 0:
        QMessageBox.information(main, "Отмена записи", "У вас пока нет записей.")
        return

    selection_model = table.selectionModel()
    if selection_model is None or not selection_model.hasSelection():
        QMessageBox.information(
            main,
            "Отмена записи",
            "Выберите запись в таблице, которую нужно отменить.",
        )
        return

    selected_rows = selection_model.selectedRows()
    if not selected_rows:
        QMessageBox.information(
            main,
            "Отмена записи",
            "Выберите запись в таблице, которую нужно отменить.",
        )
        return

    row = selected_rows[0].row()
    id_item = table.item(row, 0)
    if id_item is None:
        QMessageBox.warning(main, "Отмена записи", "Не удалось определить выбранную запись.")
        return

    try:
        appointment_id = int(id_item.text())
    except (TypeError, ValueError):
        QMessageBox.warning(main, "Отмена записи", "Некорректный идентификатор записи.")
        return

    status_query = execute_select(
        "SELECT status FROM appointments WHERE id = ?", [appointment_id], "Проверка статуса записи"
    )
    if status_query is None or not status_query.next():
        QMessageBox.warning(main, "Отмена записи", "Запись не найдена в базе данных.")
        return

    current_status = status_query.value("status")
    if current_status not in {"ожидает подтверждения", "подтверждена"}:
        QMessageBox.information(
            main,
            "Отмена записи",
            "Отменить можно только будущие или ожидающие подтверждения записи.",
        )
        return

    confirm = QMessageBox.question(
        main,
        "Подтверждение отмены",
        "Отменить выбранную запись и освободить слот?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if confirm != QMessageBox.Yes:
        return

    query = QSqlQuery()
    query.prepare("SELECT cancel_appointment(?)")
    query.addBindValue(appointment_id)

    if not query.exec():
        show_db_error(query, "Отмена записи")
        return

    load_bookings(current_user.get("id"))
    load_catalog()

    QMessageBox.information(main, "Запись отменена", "Выбранная запись успешно отменена.")


def on_add_booking():
    if current_user is None or current_role != "client":
        QMessageBox.information(
            main,
            "Добавление записи",
            "Добавлять записи может только авторизованный клиент.",
        )
        return

    catalog_tab = getattr(main, "tabCatalog", None)
    if catalog_tab is not None:
        main.twMain.setCurrentWidget(catalog_tab)

    catalog_table = getattr(main, "tblCatalog", None)
    if catalog_table is None or catalog_table.rowCount() == 0:
        QMessageBox.information(main, "Добавление записи", "Каталог пока пуст, выбирать нечего.")
        return

    selection_model = catalog_table.selectionModel()
    if selection_model is None or not selection_model.hasSelection():
        QMessageBox.information(
            main,
            "Добавление записи",
            "Выберите услугу в каталоге и повторно нажмите «Добавить».",
        )
        catalog_table.setFocus()
        return

    on_book_now()


def on_edit_user_info():
    if current_user is None or current_role != "client" or not current_user.get("id"):
        QMessageBox.information(
            main,
            "Изменение данных",
            "Редактировать профиль может только авторизованный клиент.",
        )
        return

    user_id = current_user.get("id")
    query = execute_select(
        "SELECT full_name, email, phone FROM users WHERE id = ?",
        [user_id],
        "Загрузка данных клиента",
    )

    if query is None or not query.next():
        QMessageBox.warning(
            main,
            "Изменение данных",
            "Не удалось получить текущие данные пользователя.",
        )
        return

    dialog = EditUserDialog(
        main,
        full_name=query.value("full_name"),
        email=query.value("email"),
        phone=query.value("phone"),
    )

    if dialog.exec() != QDialog.Accepted:
        return

    data = dialog.get_data() or {}
    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()

    if not full_name:
        QMessageBox.warning(main, "Изменение данных", "ФИО не может быть пустым.")
        return

    params = [full_name, email or None, phone or None, user_id]
    if not execute_action(
        "UPDATE users SET full_name = ?, email = ?, phone = ? WHERE id = ?",
        params,
        "Обновление данных клиента",
    ):
        return

    current_user["full_name"] = full_name
    if email or "email" in current_user:
        current_user["email"] = email
    if phone or "phone" in current_user:
        current_user["phone"] = phone

    load_user_info(user_id)
    configure_role_controls(current_role)

    if current_role in ROLE_CONFIGS:
        base_title = ROLE_CONFIGS[current_role]["title"]
    else:
        role_label = None
        if current_user and current_user.get("role_name"):
            role_label = current_user.get("role_name")
        if not role_label:
            role_label = current_role or "Пользователь"
        base_title = f"Smart-SPA — {role_label}"

    window_title = base_title
    if current_user and current_user.get("full_name"):
        window_title = f"{base_title} ({current_user['full_name']})"
    main.setWindowTitle(window_title)

    QMessageBox.information(main, "Изменение данных", "Ваши данные успешно сохранены.")


def on_add_service():
    salons = fetch_salons()
    if not salons:
        QMessageBox.information(main, "Добавление услуги", "В базе пока нет салонов.")
        return

    salon = salons[0]
    if len(salons) > 1:
        options = [
            f"{item['name']} ({item['city']})" if item.get("city") else item["name"]
            for item in salons
        ]
        selection, accepted = QInputDialog.getItem(
            main,
            "Выбор салона",
            "Выберите салон, куда добавить услугу:",
            options,
            0,
            False,
        )
        if not accepted:
            return
        try:
            salon = salons[options.index(selection)]
        except ValueError:
            return

    available = fetch_available_services_for_salon(salon.get("id"))
    if not available:
        QMessageBox.information(
            main,
            "Добавление услуги",
            "Для выбранного салона уже подключены все услуги или база услуг пуста.",
        )
        return

    service_options = []
    for service in available:
        details = [service.get("name") or "Услуга"]
        duration = service.get("duration_min")
        if duration:
            details.append(f"{duration} мин")
        base_price = service.get("base_price")
        if base_price is not None:
            details.append(format_price(base_price))
        service_options.append(" — ".join(details))

    selection, accepted = QInputDialog.getItem(
        main,
        "Выбор услуги",
        "Выберите услугу, которую нужно добавить:",
        service_options,
        0,
        False,
    )
    if not accepted:
        return

    try:
        service = available[service_options.index(selection)]
    except ValueError:
        return

    base_price = parse_decimal(service.get("base_price"), Decimal("0"))
    price_value, ok = QInputDialog.getDouble(
        main,
        "Цена услуги",
        f"Укажите стоимость для «{service.get('name')}»:",
        float(base_price),
        0.0,
        1_000_000.0,
        2,
    )
    if not ok:
        return

    if not execute_action(
        "INSERT INTO salon_services (salon_id, service_id, price) VALUES (?, ?, ?)",
        [salon.get("id"), service.get("id"), round(price_value, 2)],
        "Добавление услуги в салон",
    ):
        return

    load_salon_services()
    load_catalog()

    QMessageBox.information(
        main,
        "Услуга добавлена",
        f"Услуга «{service.get('name')}» добавлена в салон «{salon.get('name')}».",
    )


def on_delete_service():
    table = getattr(main, "tblServices", None)
    selection = get_selected_row_payload(table)
    if not selection:
        QMessageBox.information(
            main,
            "Удаление услуги",
            "Выберите услугу из списка, которую нужно удалить.",
        )
        return

    _, payload = selection
    confirm = QMessageBox.question(
        main,
        "Удаление услуги",
        (
            f"Удалить услугу «{payload.get('service_name')}» из салона «{payload.get('salon_name')}»?\n"
            "Записи клиентов, связанные с этой услугой, могут стать недоступны."
        ),
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if confirm != QMessageBox.Yes:
        return

    if not execute_action(
        "DELETE FROM salon_services WHERE salon_id = ? AND service_id = ?",
        [payload.get("salon_id"), payload.get("service_id")],
        "Удаление услуги салона",
    ):
        return

    load_salon_services()
    load_catalog()

    QMessageBox.information(main, "Услуга удалена", "Услуга успешно удалена из салона.")


def on_save_service():
    table = getattr(main, "tblServices", None)
    selection = get_selected_row_payload(table)
    if not selection:
        QMessageBox.information(
            main,
            "Изменение цены",
            "Выберите услугу, для которой нужно изменить стоимость.",
        )
        return

    row, payload = selection
    price_item = table.item(row, 3) if table else None
    current_price = parse_decimal(payload.get("price"), Decimal("0"))
    if price_item is not None:
        current_price = parse_decimal(price_item.text(), current_price)

    new_price, ok = QInputDialog.getDouble(
        main,
        "Изменение цены",
        (
            f"Укажите новую цену для «{payload.get('service_name')}»\n"
            f"в салоне «{payload.get('salon_name')}»."
        ),
        float(current_price),
        0.0,
        1_000_000.0,
        2,
    )
    if not ok:
        return

    if not execute_action(
        "UPDATE salon_services SET price = ? WHERE salon_id = ? AND service_id = ?",
        [round(new_price, 2), payload.get("salon_id"), payload.get("service_id")],
        "Обновление цены услуги",
    ):
        return

    load_salon_services()
    load_catalog()

    QMessageBox.information(main, "Цена обновлена", "Стоимость услуги успешно изменена.")


def on_delete_user():
    table = getattr(main, "tblUsers", None)
    if table is None or table.rowCount() == 0:
        QMessageBox.information(main, "Удаление пользователя", "Список пользователей пуст.")
        return

    selection_model = table.selectionModel()
    if selection_model is None or not selection_model.hasSelection():
        QMessageBox.information(
            main,
            "Удаление пользователя",
            "Выберите пользователя из таблицы, чтобы удалить его.",
        )
        return

    row = selection_model.selectedRows()[0].row()
    id_item = table.item(row, 0)
    name_item = table.item(row, 1)
    if id_item is None:
        QMessageBox.warning(main, "Удаление пользователя", "Не удалось определить пользователя.")
        return

    try:
        user_id = int(id_item.text())
    except (TypeError, ValueError):
        QMessageBox.warning(main, "Удаление пользователя", "Некорректный идентификатор пользователя.")
        return

    if current_user and current_user.get("id") == user_id:
        QMessageBox.warning(
            main,
            "Удаление пользователя",
            "Нельзя удалить себя из системы во время активной сессии.",
        )
        return

    user_name = name_item.text() if name_item else "пользователь"
    confirm = QMessageBox.question(
        main,
        "Удаление пользователя",
        f"Удалить {user_name}?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if confirm != QMessageBox.Yes:
        return

    if not execute_action(
        "DELETE FROM users WHERE id = ?",
        [user_id],
        "Удаление пользователя",
    ):
        return

    load_users()
    QMessageBox.information(main, "Пользователь удалён", "Пользователь успешно удалён.")


def on_approve_review():
    QMessageBox.information(
        main,
        "Отзывы",
        "Функция модерации отзывов пока недоступна в клиентском приложении.",
    )


apply_button = getattr(main, "btnApply", None)
if apply_button is not None:
    apply_button.clicked.connect(on_apply_filter)
main.btnBookNow.clicked.connect(on_book_now)

if hasattr(main, "btnCancelBooking"):
    main.btnCancelBooking.clicked.connect(on_cancel_booking)

if hasattr(main, "btnAddBooking"):
    main.btnAddBooking.clicked.connect(on_add_booking)

if hasattr(main, "btnResetInfo"):
    main.btnResetInfo.clicked.connect(on_edit_user_info)

if hasattr(main, "btnAddService"):
    main.btnAddService.clicked.connect(on_add_service)

if hasattr(main, "btnDeleteService"):
    main.btnDeleteService.clicked.connect(on_delete_service)

if hasattr(main, "btnSaveService"):
    main.btnSaveService.clicked.connect(on_save_service)

if hasattr(main, "btnDeleteUser"):
    main.btnDeleteUser.clicked.connect(on_delete_user)

if hasattr(main, "btnApproveReview"):
    main.btnApproveReview.clicked.connect(on_approve_review)

if hasattr(main, "leSearch"):
    main.leSearch.returnPressed.connect(on_apply_filter)

if hasattr(main, "cbCity"):
    main.cbCity.currentIndexChanged.connect(lambda *_: on_apply_filter())

configure_role_controls(None)

login.show()
sys.exit(app.exec())
