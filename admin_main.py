import sys
import os
import ctypes
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from core import PathManager
from admin_ui import AdminWindow


def self_check():
    if sys.gettrace() is not None:
        ctypes.windll.user32.MessageBoxW(
            0,
            "安全自检未通过：检测到非法调试环境！\n程序即将退出。",
            "安全拦截",
            0x10,
        )
        sys.exit(1)


if __name__ == "__main__":
    self_check()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    icon_path = os.path.join(PathManager.get_resource_dir(), "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = AdminWindow()
    win.show()
    sys.exit(app.exec_())
