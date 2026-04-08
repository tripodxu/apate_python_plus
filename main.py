import sys
import os
import ctypes
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from ui import MainWindow

# =================== 核心机制 1：动态资源路径解析 ===================
def resource_path(relative_path):
    """
    获取程序运行时的绝对路径。
    解决 PyInstaller 打包成单文件 exe 后，资源被解压到临时目录导致找不到图标的问题。
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# =================== 核心机制 2：程序基础自校验 ===================
def self_check():
    """
    基础的程序自检与环境校验。
    防止程序被逆向人员使用调试器（如 PySnooper, PDB 等）动态调试分析。
    """
    # 检测是否被附加 Python 层面的调试器
    if sys.gettrace() is not None:
        # 使用 Windows 底层 API 弹窗报错，避免依赖可能被篡改的 GUI 库
        ctypes.windll.user32.MessageBoxW(0, "安全自检未通过：检测到非法调试环境！\n程序即将退出。", "安全拦截", 0x10)
        sys.exit(1)
        
    # 如果你有附加的核心授权文件或配置，也可以在这里计算它的 MD5 进行比对
    # 例如：
    # expected_md5 = "e10adc3949ba59abbe56e057f20f883e"
    # actual_md5 = hashlib.md5(open(resource_path('config.bin'), 'rb').read()).hexdigest()
    # if actual_md5 != expected_md5: sys.exit(1)

# =================== 主程序入口 ===================
if __name__ == "__main__":
    # 1. 启动前先执行自检
    self_check()
    
    # 2. 初始化应用
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 3. 设置全局应用图标 (包括窗口左上角和 Windows 任务栏)
    icon_path = resource_path('icon.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        
    # 4. 加载并显示主窗口
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())