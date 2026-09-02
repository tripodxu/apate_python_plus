"""GUI 入口公共引导：自检、QApplication、图标与主循环，供 main.py / admin_main.py 复用。"""
import sys
import ctypes

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from core import PathManager


def self_check():
    """
    基础的程序自检与环境校验。
    防止程序被逆向人员使用调试器（如 PySnooper, PDB 等）动态调试分析。
    仅在 Windows 下启用（ctypes.windll 仅 Windows 可用）。
    """
    if sys.platform != "win32":
        return
    if sys.gettrace() is not None:
        ctypes.windll.user32.MessageBoxW(
            0,
            "安全自检未通过：检测到非法调试环境！\n程序即将退出。",
            "安全拦截",
            0x10,
        )
        sys.exit(1)


def run_app(window_cls):
    """启动指定主窗口类（在创建 QApplication 前先执行自检，与原入口行为一致）。"""
    self_check()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 使用 PathManager.get_resource_dir() 精准寻找 Nuitka/PyInstaller 的资源解压目录
    icon_path = PathManager.get_resource_dir() / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = window_cls()
    win.show()
    sys.exit(app.exec_())
