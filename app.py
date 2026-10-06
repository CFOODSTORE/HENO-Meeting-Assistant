import sys

from PySide6.QtWidgets import QApplication

from heno.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HENO Meeting Assistant")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
