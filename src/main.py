import sys
from PySide6.QtWidgets import QApplication
from ui.frontend_main import main_window

def main():
    app = QApplication(sys.argv)

    window = main_window()
    window.show()

    sys.exit(app.exec())

main()