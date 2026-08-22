import sys
from PySide6.QtWidgets import QApplication
from ui.frontend_main import MainWindow

def main():
    app = QApplication(sys.argv)

    load_stylesheet(app, "src/ui/pages/style/overview_page.qss")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

def load_stylesheet(app, filepath):
    try:
        with open(filepath, "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print(f"Warning: Stylesheet file not found at {filepath}")

if __name__ == '__main__':
    main()