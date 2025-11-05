import sys
import os
import base64
import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from functools import lru_cache

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
    QSpinBox,
    QDoubleSpinBox,
    QPlainTextEdit,
    QComboBox,
    QLabel,
    QDateTimeEdit,
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

STATUS_ALIASES = {
    "ожидает подтверждения": "ожидает подтверждения",
    "ожидание подтверждения": "ожидает подтверждения",
    "ожидаетподтверждения": "ожидает подтверждения",
    "pending": "ожидает подтверждения",
    "pending confirmation": "ожидает подтверждения",
    "pending_confirmation": "ожидает подтверждения",
    "awaiting confirmation": "ожидает подтверждения",
    "awaiting_confirmation": "ожидает подтверждения",
    "подтверждена": "подтверждена",
    "подтвержден": "подтверждена",
    "подтверждено": "подтверждена",
    "confirmed": "подтверждена",
    "confirmed appointment": "подтверждена",
    "отменена": "отменена",
    "отменен": "отменена",
    "отменено": "отменена",
    "canceled": "отменена",
    "cancelled": "отменена",
    "declined": "отменена",
    "завершена": "завершена",
    "завершено": "завершена",
    "completed": "завершена",
    "finished": "завершена",
    "done": "завершена",
}

ALLOWED_CANCELLATION_STATUSES = {"ожидает подтверждения", "подтверждена"}

def load_ui(path):
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        path,
        os.path.join(base, path),
        os.path.join(base, "ui", os.path.basename(path)),
        os.path.join(os.getcwd(), "ui", os.path.basename(path)),
        os.path.join(base, os.path.basename(path)),
    ]
    for p in candidates:
        f = QFile(p)
        if f.exists() and f.open(QFile.ReadOnly):
            try:
                ui = QUiLoader().load(f)
                return ui
            finally:
                f.close()
    QMessageBox.critical(None, "UI", f"Файл не найден: {path}")
    return None
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


class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            left_key = self.data(Qt.UserRole + 1)
            right_key = other.data(Qt.UserRole + 1)
            if left_key is not None and right_key is not None:
                try:
                    return left_key < right_key
                except TypeError:
                    return str(left_key) < str(right_key)
        return super().__lt__(other)


def build_sort_key(value):
    if value is None:
        return None
    if isinstance(value, QDateTime):
        return value.toSecsSinceEpoch()
    if isinstance(value, QDate):
        start_dt = QDateTime(value, QTime(0, 0))
        return start_dt.toSecsSinceEpoch()
    if isinstance(value, QTime):
        return value.msecsSinceStartOfDay()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return value
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
            item = SortableTableWidgetItem(format_cell(cell))
            sort_key = build_sort_key(cell)
            if sort_key is not None:
                item.setData(Qt.UserRole + 1, sort_key)
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


def cleanup_client_related_data(user_id):
    status_select, status_join = build_status_select_clause("status_display")
    appointments_sql = (
        f"SELECT a.id, a.slot_id, {status_select} "
        "FROM appointments a "
        f"{status_join}"
        "WHERE a.client_id = ?"
    )

    appointments_query = execute_select(
        appointments_sql,
        [user_id],
        "Получение записей пользователя перед удалением",
    )
    if appointments_query is None:
        return False

    appointments = []
    cancellable_ids = []
    slots_to_release = set()

    while appointments_query.next():
        appointment_id = appointments_query.value("id")
        slot_id = appointments_query.value("slot_id")
        status_value = normalize_status(appointments_query.value("status_display"))

        if appointment_id is not None:
            try:
                appointments.append(int(appointment_id))
            except (TypeError, ValueError):
                pass

        if status_value in ALLOWED_CANCELLATION_STATUSES and appointment_id is not None:
            try:
                cancellable_ids.append(int(appointment_id))
            except (TypeError, ValueError):
                pass

        if slot_id is not None:
            try:
                slots_to_release.add(int(slot_id))
            except (TypeError, ValueError):
                pass

    if appointments:
        if not execute_action(
            (
                "DELETE FROM reviews "
                "WHERE appointment_id IN (SELECT id FROM appointments WHERE client_id = ?)"
            ),
            [user_id],
            "Удаление отзывов, связанных с записями пользователя",
        ):
            return False

    if not execute_action(
        "DELETE FROM reviews WHERE client_id = ?",
        [user_id],
        "Удаление отзывов пользователя",
    ):
        return False

    for appointment_id in cancellable_ids:
        query = QSqlQuery()
        query.prepare("SELECT cancel_appointment(?)")
        query.addBindValue(appointment_id)
        if not query.exec():
            show_db_error(query, "Отмена записей пользователя")
            return False

    if appointments:
        if not execute_action(
            "DELETE FROM appointments WHERE client_id = ?",
            [user_id],
            "Удаление записей пользователя",
        ):
            return False

    for slot_id in slots_to_release:
        if not execute_action(
            "UPDATE schedule_slots SET is_booked = FALSE WHERE id = ?",
            [slot_id],
            "Освобождение слота пользователя",
        ):
            return False

    return True


@lru_cache(maxsize=None)
def get_table_columns(table_name):
    query = execute_select(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ?",
        [table_name],
        context=f"Получение списка колонок таблицы {table_name}",
    )
    columns = set()
    if query is not None:
        while query.next():
            column_name = query.value(0)
            if column_name:
                columns.add(str(column_name).lower())
    return columns


def build_status_select_clause(alias="status_display"):
    appointment_columns = get_table_columns("appointments")
    status_table_columns = get_table_columns("appointment_statuses")

    join_clause = ""
    if status_table_columns:
        if "status_id" in appointment_columns and "id" in status_table_columns:
            join_clause = " LEFT JOIN appointment_statuses st ON st.id = a.status_id "
        elif "status_code" in appointment_columns and "code" in status_table_columns:
            join_clause = " LEFT JOIN appointment_statuses st ON st.code = a.status_code "

    parts = []
    if join_clause:
        for column in ("display_name", "name", "title", "label", "code"):
            if column in status_table_columns:
                parts.append(f"st.{column}")

    for column, expression in (
        ("status", "a.status"),
        ("status_text", "a.status_text"),
        ("status_code", "a.status_code"),
    ):
        if column in appointment_columns:
            parts.append(expression)

    if "status_id" in appointment_columns:
        parts.append("CAST(a.status_id AS TEXT)")

    if not parts:
        parts.append("'неизвестно'")

    seen = set()
    unique_parts = []
    for expr in parts:
        if expr not in seen:
            unique_parts.append(expr)
            seen.add(expr)

    if len(unique_parts) == 1:
        select_expr = f"{unique_parts[0]} AS {alias}"
    else:
        select_expr = f"COALESCE({', '.join(unique_parts)}) AS {alias}"

    return select_expr, join_clause


def normalize_status(value):
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    key = text.lower()
    return STATUS_ALIASES.get(key, text)


def find_user(login_text):
    login_text = (login_text or "").strip()
    if not login_text:
        return None

    phone = normalize_phone(login_text)
    email = login_text if "@" in login_text else None

    where_clauses = []
    params = []

    if phone:
        where_clauses.append("u.phone = ?")
        params.append(phone)
    if email:
        where_clauses.append("lower(u.email) = lower(?)")
        params.append(email)

    if not where_clauses:
        return None

    sql = (
        "SELECT u.id, u.full_name, u.password_hash, r.code AS role_code, r.name AS role_name "
        "FROM users u "
        "JOIN roles r ON r.id = u.role_id "
        "WHERE " + " OR ".join(where_clauses) + " "
        "LIMIT 1"
    )
    query = execute_select(sql, params, "Поиск пользователя")
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
    headers = ["Салон", "Услуга", "Начало", "Статус"]

    if user_id is None:
        populate_table(table, headers, [])
        return

    status_select, status_join = build_status_select_clause()
    sql = (
        "SELECT a.id, salons.name AS salon_name, srv.name AS service_name, "
        f"       slots.start_ts AS start_ts, {status_select} "
        "FROM appointments a "
        "JOIN salons ON salons.id = a.salon_id "
        "JOIN services srv ON srv.id = a.service_id "
        "JOIN schedule_slots slots ON slots.id = a.slot_id "
        f"{status_join}"
        "WHERE a.client_id = ? "
        "ORDER BY slots.start_ts"
    )
    query = execute_select(sql, [user_id], "Загрузка записей клиента")
    rows = []
    payloads = []
    if query is not None:
        while query.next():
            appointment_id = query.value("id")
            status_value = query.value("status_display")
            status_text = normalize_status(status_value)
            if not status_text:
                status_text = format_cell(status_value)
            rows.append([
                query.value("salon_name"),
                query.value("service_name"),
                query.value("start_ts"),
                status_text,
            ])
            payloads.append({"appointment_id": appointment_id})
    populate_table(table, headers, rows, payloads)


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
    if current_role == "salon" and current_user:
        sql = (
            "SELECT s.id, s.name, s.city "
            "FROM salons s "
            "JOIN salon_users su ON su.salon_id = s.id "
            "WHERE su.user_id = ? "
            "ORDER BY s.name"
        )
        query = execute_select(sql, [current_user.get("id")], context="Загрузка списка салонов")
    else:
        sql = "SELECT id, name, city FROM salons ORDER BY name"
        query = execute_select(sql, context="Загрузка списка салонов")
    salons = []
    if query is not None:
        while query.next():
            salons.append(
                {"id": query.value("id"), "name": query.value("name"), "city": query.value("city")}
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


def fetch_masters_for_salon(salon_id):
    if salon_id is None:
        return []
def fetch_masters_for_salon_and_service(salon_id, service_id):
    if salon_id is None or service_id is None:
        return []
    sql = (
        "SELECT m.id, m.full_name, m.specialization "
        "FROM masters m "
        "JOIN master_services ms ON ms.master_id = m.id "
        "WHERE m.salon_id = ? AND m.active = TRUE AND ms.service_id = ? "
        "ORDER BY m.full_name"
    )
    query = execute_select(sql, [salon_id, service_id], "Загрузка мастеров для услуги салона")
    masters = []
    if query is not None:
        while query.next():
            masters.append(
                {
                    "id": query.value("id"),
                    "full_name": query.value("full_name"),
                    "specialization": query.value("specialization"),
                }
            )
    return masters


    sql = (
        "SELECT id, full_name, specialization "
        "FROM masters "
        "WHERE salon_id = ? AND active = TRUE "
        "ORDER BY full_name"
    )
    query = execute_select(sql, [salon_id], "Загрузка мастеров салона")
    masters = []
    if query is not None:
        while query.next():
            masters.append(
                {
                    "id": query.value("id"),
                    "full_name": query.value("full_name"),
                    "specialization": query.value("specialization"),
                }
            )
    return masters


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


class CreateServiceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая услуга")
        self.setModal(True)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("serviceNameEdit")
        layout.addRow("Название", self.name_edit)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setObjectName("serviceDescriptionEdit")
        self.description_edit.setPlaceholderText("Опишите услугу (необязательно)")
        self.description_edit.setMaximumHeight(90)
        layout.addRow("Описание", self.description_edit)

        self.duration_spin = QSpinBox()
        self.duration_spin.setObjectName("serviceDurationSpin")
        self.duration_spin.setRange(15, 480)
        self.duration_spin.setSingleStep(5)
        self.duration_spin.setValue(60)
        layout.addRow("Длительность (мин)", self.duration_spin)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setObjectName("servicePriceSpin")
        self.price_spin.setRange(0.0, 1_000_000.0)
        self.price_spin.setDecimals(2)
        self.price_spin.setSingleStep(100.0)
        self.price_spin.setValue(1000.0)
        layout.addRow("Базовая цена", self.price_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._result = None

    def accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Укажите название услуги.")
            self.name_edit.setFocus()
            return

        description = self.description_edit.toPlainText().strip()
        duration = int(self.duration_spin.value())
        base_price = Decimal(str(self.price_spin.value()))

        self._result = {
            "name": name,
            "description": description or None,
            "duration_min": duration,
            "base_price": base_price,
        }

        super().accept()

    def get_data(self):
        return self._result


class CreateSlotDialog(QDialog):
    def __init__(self, parent=None, context=None, masters=None):
        super().__init__(parent)
        self.setWindowTitle("Новое время")
        self.setModal(True)

        context = context or {}
        masters = masters or []

        layout = QFormLayout(self)

        salon_name = context.get("salon_name") or context.get("salon")
        if salon_name:
            salon_label = QLabel(salon_name)
            salon_label.setWordWrap(True)
            layout.addRow("Салон", salon_label)

        service_name = context.get("service_name") or context.get("name")
        service_label = QLabel(service_name or "—")
        service_label.setWordWrap(True)
        layout.addRow("Услуга", service_label)

        self.master_combo = QComboBox()
        self.master_combo.setObjectName("slotMasterCombo")
        for master in masters:
            if not master:
                continue
            label = master.get("full_name") or "Мастер"
            specialization = master.get("specialization")
            if specialization:
                label = f"{label} ({specialization})"
            self.master_combo.addItem(label, master)
        layout.addRow("Мастер", self.master_combo)

        self.duration_min = int(context.get("duration_min") or 0)
        if self.duration_min <= 0:
            self.duration_min = 60

        self.start_edit = QDateTimeEdit()
        self.start_edit.setObjectName("slotStartEdit")
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        now = QDateTime.currentDateTime()
        aligned = now.addSecs(0)
        minute = aligned.time().minute()
        if minute % 5:
            delta = 5 - (minute % 5)
            aligned = aligned.addSecs(delta * 60)
        if aligned < now.addSecs(300):
            aligned = aligned.addSecs(300)
        self.start_edit.setDateTime(aligned)
        self.start_edit.setMinimumDateTime(now)
        layout.addRow("Начало", self.start_edit)

        self.duration_label = QLabel(f"{self.duration_min} мин")
        layout.addRow("Длительность", self.duration_label)

        self.end_label = QLabel()
        layout.addRow("Окончание", self.end_label)

        self.start_edit.dateTimeChanged.connect(self._update_end_label)
        self._update_end_label()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if self.master_combo.count() == 0:
            save_button = buttons.button(QDialogButtonBox.Save)
            if save_button is not None:
                save_button.setEnabled(False)

        self._result = None

    def _update_end_label(self):
        start_dt = self.start_edit.dateTime()
        end_dt = start_dt.addSecs(int(self.duration_min) * 60)
        self.end_label.setText(end_dt.toString("dd.MM.yyyy HH:mm"))
class AssignMastersDialog(QDialog):
    def __init__(self, parent=None, salon=None, service=None):
        super().__init__(parent)
        self.setWindowTitle("Назначение мастеров на услугу")
        self._salon = salon or {}
        self._service = service or {}
        self._result = None

        layout = QFormLayout(self)

        label = QLabel(f"Салон: {self._salon.get('name') or self._salon.get('id')}\n"
                       f"Услуга: {self._service.get('name') or self._service.get('id')}")
        layout.addRow(label)

        self._masters = fetch_masters_for_salon(self._salon.get('id'))
        assigned_ids = set(fetch_assigned_master_ids(self._salon.get('id'), self._service.get('id')))

        self._checkboxes = []
        for m in self._masters:
            cb = QCheckBox((m.get("full_name") or "Мастер") + (f" ({m.get('specialization')})" if m.get("specialization") else ""))
            cb.setChecked(m.get("id") in assigned_ids)
            cb.master_id = m.get("id")
            self._checkboxes.append(cb)
            layout.addRow(cb)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self):
        return self._result

    def accept(self):
        selected = [cb.master_id for cb in self._checkboxes if cb.isChecked()]
        self._result = {"selected_master_ids": selected}
        super().accept()


def fetch_assigned_master_ids(salon_id, service_id):
    sql = (
        "SELECT ms.master_id "
        "FROM master_services ms "
        "JOIN masters m ON m.id = ms.master_id "
        "WHERE m.salon_id = ? AND ms.service_id = ? "
        "ORDER BY ms.master_id"
    )
    q = execute_select(sql, [salon_id, service_id], "Назначенные мастера на услугу")
    result = []
    if q is not None:
        while q.next():
            result.append(q.value(0))
    return result


def save_master_assignments(salon_id, service_id, master_ids):
    # Simple approach: replace assignments
    if not execute_action("DELETE FROM master_services WHERE master_id IN (SELECT id FROM masters WHERE salon_id = ?) AND service_id = ?",
                          [salon_id, service_id],
                          "Очистка старых назначений мастеров"):
        return False
    for mid in master_ids:
        if not execute_action("INSERT INTO master_services(master_id, service_id) VALUES (?, ?)",
                              [mid, service_id],
                              "Назначение мастера на услугу"):
            return False
    return True


def on_assign_masters_button():
    table = getattr(main, "tblServices", None)
    selection = get_selected_row_payload(table)
    if not selection:
        QMessageBox.information(main, "Назначение мастеров", "Выберите услугу салона в таблице.")
        return
    _, payload = selection
    salon = {"id": payload.get("salon_id"), "name": payload.get("salon_name")}
    service = {"id": payload.get("service_id"), "name": payload.get("service_name")}
    on_assign_masters_to_service(salon, service)


def on_assign_masters_to_service(salon, service):
    if not salon or not service or not salon.get("id") or not service.get("id"):
        QMessageBox.warning(main, "Назначение мастеров", "Не удалось определить салон или услугу.")
        return
    dlg = AssignMastersDialog(main, salon=salon, service=service)
    if dlg.exec() != QDialog.Accepted:
        return
    data = dlg.get_data() or {}
    master_ids = data.get("selected_master_ids") or []
    if not save_master_assignments(salon.get("id"), service.get("id"), master_ids):
        return
    QMessageBox.information(main, "Назначение мастеров", "Назначения сохранены.")


    def accept(self):
        master_data = self.master_combo.currentData()
        if not master_data or not master_data.get("id"):
            QMessageBox.warning(self, "Добавление времени", "Выберите мастера.")
            return

        start_dt = self.start_edit.dateTime()
        if start_dt < QDateTime.currentDateTime():
            QMessageBox.warning(
                self,
                "Добавление времени",
                "Нельзя создать слот в прошлом. Выберите другое время.",
            )
            return

        seconds = start_dt.time().second()
        if seconds:
            start_dt = start_dt.addSecs(-seconds)

        end_dt = start_dt.addSecs(int(self.duration_min) * 60)

        self._result = {
            "master": master_data,
            "master_id": master_data.get("id"),
            "start_ts": start_dt,
            "end_ts": end_dt,
        }

        super().accept()

    def get_data(self):
        return self._result


def create_service_via_dialog(parent):
    dialog = CreateServiceDialog(parent)
    if dialog.exec() != QDialog.Accepted:
        return None

    data = dialog.get_data()
    if not data:
        return None

    query = QSqlQuery()
    query.prepare(
        "INSERT INTO services (name, description, base_price, duration_min) "
        "VALUES (?, ?, ?, ?) RETURNING id"
    )
    query.addBindValue(data.get("name"))
    query.addBindValue(data.get("description"))
    query.addBindValue(float(data.get("base_price", Decimal("0"))))
    query.addBindValue(data.get("duration_min"))

    if not query.exec():
        show_db_error(query, "Создание новой услуги")
        return None

    service_id = None
    if query.next():
        service_id = query.value(0)

    if not service_id:
        QMessageBox.warning(parent, "Создание услуги", "Не удалось сохранить услугу.")
        return None

    return {
        "id": service_id,
        "name": data.get("name"),
        "duration_min": data.get("duration_min"),
        "base_price": data.get("base_price"),
    }


def create_slot_for_service(context):
    if context is None:
        return False

    salon_id = context.get("salon_id")
    if salon_id is None and isinstance(context.get("salon"), dict):
        salon_id = context["salon"].get("id")

    service_id = context.get("service_id")
    if service_id is None and isinstance(context.get("service"), dict):
        service_id = context["service"].get("id")

    if not salon_id or not service_id:
        QMessageBox.warning(
            main,
            "Добавление времени",
            "Не удалось определить салон или услугу для создания слота.",
        )
        return False

    if context.get("duration_min") is None:
        duration_query = execute_select(
            "SELECT duration_min FROM services WHERE id = ?",
            [service_id],
            "Получение длительности услуги",
        )
        if duration_query is not None and duration_query.next():
            context["duration_min"] = duration_query.value(0)

    masters = fetch_masters_for_salon_and_service(salon_id, service_id)
    if not masters:
        QMessageBox.information(
            main,
            "Добавление времени",
            "Ни один мастер не назначен на эту услугу. Сначала назначьте мастера на услугу.",
        )
        on_assign_masters_to_service({"id": salon_id, "name": context.get("salon_name")}, {"id": service_id, "name": context.get("service_name")})
        masters = fetch_masters_for_salon_and_service(salon_id, service_id)
        if not masters:
            QMessageBox.information(
                main,
                "Добавление времени",
                "В салоне нет активных мастеров. Добавьте мастеров прежде, чем создавать время.",
            )
        return False

    dialog = CreateSlotDialog(main, context=context, masters=masters)
    if dialog.exec() != QDialog.Accepted:
        return False

    slot_data = dialog.get_data() or {}
    master = slot_data.get("master") or {}
    master_id = slot_data.get("master_id")
    start_dt = slot_data.get("start_ts")
    end_dt = slot_data.get("end_ts")
    if not master_id or start_dt is None or end_dt is None:
        QMessageBox.warning(
            main,
            "Добавление времени",
            "Недостаточно данных для сохранения нового слота.",
        )
        return False

    query = QSqlQuery()
    query.prepare(
        "INSERT INTO schedule_slots (master_id, start_ts, end_ts, is_booked) VALUES (?, ?, ?, FALSE)"
    )
    query.addBindValue(master_id)
    query.addBindValue(start_dt)
    query.addBindValue(end_dt)

    if not query.exec():
        show_db_error(query, "Добавление нового слота в расписание")
        return False

    start_text = format_cell(start_dt)
    end_text = format_cell(end_dt)
    time_text = start_text
    if end_text and end_text != start_text:
        time_text = f"{start_text} – {end_text}"

    service_name = context.get("service_name") or context.get("name")
    salon_name = context.get("salon_name") or context.get("salon")
    master_name = master.get("full_name")

    message_parts = []
    if service_name:
        message_parts.append(f"Для услуги «{service_name}»")
    else:
        message_parts.append("Создан свободный слот")

    message_parts.append(f"назначено время {time_text}.")

    if master_name:
        message_parts.append(f"Мастер: {master_name}.")

    if salon_name:
        message_title = f"Салон «{salon_name}»"
    else:
        message_title = "Время добавлено"

    QMessageBox.information(main, message_title, " ".join(message_parts))
    return True


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
                    "duration_min": query.value("duration_min"),
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
    if hasattr(main, "btnAddSlot"):
        main.btnAddSlot.setEnabled(manage_services)
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

    if not username:
        QMessageBox.warning(login, "Ошибка", "Введите логин!")
        return

    user_record = find_user(username)
    if user_record is None:
        QMessageBox.warning(login, "Ошибка", "Пользователь не найден.")
        return

    password = login.lePassword.text()
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
    resolved_role = user.get("role_code") or "client"

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

    payload = id_item.data(Qt.UserRole)
    appointment_id = None
    if isinstance(payload, dict):
        appointment_id = payload.get("appointment_id")
    elif payload is not None:
        appointment_id = payload

    if appointment_id is None:
        try:
            appointment_id = int(id_item.text())
        except (TypeError, ValueError):
            appointment_id = None

    if not isinstance(appointment_id, int):
        try:
            appointment_id = int(appointment_id)
        except (TypeError, ValueError):
            appointment_id = None

    if appointment_id is None:
        QMessageBox.warning(main, "Отмена записи", "Некорректный идентификатор записи.")
        return

    status_select, status_join = build_status_select_clause()
    status_sql = (
        f"SELECT {status_select} "
        "FROM appointments a "
        f"{status_join}"
        "WHERE a.id = ?"
    )
    status_query = execute_select(status_sql, [appointment_id], "Проверка статуса записи")
    if status_query is None or not status_query.next():
        QMessageBox.warning(main, "Отмена записи", "Запись не найдена в базе данных.")
        return

    current_status = status_query.value("status_display")
    normalized_status = normalize_status(current_status)
    if normalized_status not in ALLOWED_CANCELLATION_STATUSES:
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
    service = None

    if available:
        service_options = []
        for svc in available:
            details = [svc.get("name") or "Услуга"]
            duration = svc.get("duration_min")
            if duration:
                details.append(f"{duration} мин")
            base_price = svc.get("base_price")
            if base_price is not None:
                details.append(format_price(base_price))
            service_options.append(" — ".join(details))

        create_option = "Создать новую услугу…"
        service_options.append(create_option)

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

        if selection == create_option:
            service = create_service_via_dialog(main)
            if not service:
                return
        else:
            try:
                service = available[service_options.index(selection)]
            except ValueError:
                return
    else:
        QMessageBox.information(
            main,
            "Добавление услуги",
            "Для выбранного салона нет доступных услуг. Создайте новую услугу.",
        )
        service = create_service_via_dialog(main)
        if not service:
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

    slot_context = {
        "salon_id": salon.get("id"),
        "salon_name": salon.get("name"),
        "service_id": service.get("id"),
        "service_name": service.get("name"),
        "duration_min": service.get("duration_min"),
    }

    ask_slot = QMessageBox.question(
        main,
        "Добавление времени",
        (
            f"Создать свободное время для услуги «{service.get('name')}»\n"
            f"в салоне «{salon.get('name')}» прямо сейчас?"
        ),
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )

    if ask_slot == QMessageBox.Yes:
        create_slot_for_service(slot_context)

    QMessageBox.information(
        main,
        "Услуга добавлена",
        f"Услуга «{service.get('name')}» добавлена в салон «{salon.get('name')}».",
    )


def on_add_slot():
    table = getattr(main, "tblServices", None)
    selection = get_selected_row_payload(table)
    if not selection:
        QMessageBox.information(
            main,
            "Добавление времени",
            "Выберите услугу в таблице салона, для которой нужно создать время.",
        )
        return

    _, payload = selection
    salon_id = payload.get("salon_id")
    service_id = payload.get("service_id")
    if not salon_id or not service_id:
        QMessageBox.warning(
            main,
            "Добавление времени",
            "Не удалось определить выбранную услугу.",
        )
        return

    duration = payload.get("duration_min")
    if duration is not None:
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = None

    context = {
        "salon_id": salon_id,
        "salon_name": payload.get("salon_name"),
        "service_id": service_id,
        "service_name": payload.get("service_name"),
        "duration_min": duration,
    }

    create_slot_for_service(context)


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

    user_query = execute_select(
        (
            "SELECT u.full_name, r.code AS role_code "
            "FROM users u JOIN roles r ON r.id = u.role_id "
            "WHERE u.id = ?"
        ),
        [user_id],
        "Получение информации о пользователе перед удалением",
    )

    if user_query is None or not user_query.next():
        QMessageBox.warning(
            main,
            "Удаление пользователя",
            "Не удалось получить текущие данные пользователя.",
        )
        return

    user_name = name_item.text() if name_item else "пользователь"
    db_full_name = user_query.value("full_name")
    if db_full_name:
        user_name = db_full_name

    role_code = user_query.value("role_code")

    confirm = QMessageBox.question(
        main,
        "Удаление пользователя",
        f"Удалить {user_name}?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if confirm != QMessageBox.Yes:
        return

    if isinstance(role_code, str) and role_code.strip().lower() == "client":
        if not cleanup_client_related_data(user_id):
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

if hasattr(main, "btnAddSlot"):
    main.btnAddSlot.clicked.connect(on_add_slot)

if hasattr(main, "btnAssignMasters"):
    main.btnAssignMasters.clicked.connect(on_assign_masters_button)

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
