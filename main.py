import sys
import os
from db import connect_db
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

def load_ui(path):
    if not os.path.exists(path):
        print("Файл не найден:", path)
    f = QFile(path)
    if not f.open(QFile.ReadOnly):
        print("Ошибка открытия:", path)
    ui = QUiLoader().load(f)
    f.close()
    return ui

app = QApplication(sys.argv)

if not connect_db():
    sys.exit(1)

login = load_ui("ui/LoginWindow.ui")
main = load_ui("ui/MainWindow.ui")

def on_login():
    username = login.leUsername.text()
    role = login.cbRole.currentText()

    if not username:
        QMessageBox.warning(login, "Ошибка", "Введите логин!")
        return

    login.close()
    setup_role(role)
    main.show()

def setup_role(role):
    tabs = {
        "catalog": getattr(main, "tabCatalog", None),
        "book": getattr(main, "tabBookings", None),
        "salon": getattr(main, "tabSalon", None),
        "admin": getattr(main, "tabAdmin", None),
    }

    # Спрячем все вкладки и подготовим список, который нужно показать
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
        main.setWindowTitle(title)

    if role == "Client":
        show_tabs(("catalog", "book"), "Smart-SPA — Клиент")

    elif role == "Salon":
        show_tabs(("salon", "catalog"), "Smart-SPA — Салон")

    elif role == "Admin":
        show_tabs(("admin",), "Smart-SPA — Администратор")

login.btnLogin.clicked.connect(on_login)

login.show()
sys.exit(app.exec())