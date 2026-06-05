import sys

from PyQt5.QtWidgets import QApplication

from modbus_master.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Modbus Master Simulator")
    app.setOrganizationName("ModbusMaster")

    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
