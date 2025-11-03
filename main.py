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

    for t in tabs.values():
        if t:
            idx = main.twMain.indexOf(t)
            if idx != -1:
                main.twMain.setTabVisible(idx, False)

    if role == "Client":
        for key in ("catalog", "book"):
            t = tabs[key]
            if t:
                main.twMain.setTabVisible(main.twMain.indexOf(t), True)
        main.setWindowTitle("Smart-SPA — Клиент")

    elif role == "Salon":
        for key in ("salon", "catalog"):
            t = tabs[key]
            if t:
                main.twMain.setTabVisible(main.twMain.indexOf(t), True)
        main.setWindowTitle("Smart-SPA — Салон")

    elif role == "Admin":
        t = tabs["admin"]
        if t:
            main.twMain.setTabVisible(main.twMain.indexOf(t), True)
        main.setWindowTitle("Smart-SPA — Администратор")

login.btnLogin.clicked.connect(on_login)

login.show()
sys.exit(app.exec())