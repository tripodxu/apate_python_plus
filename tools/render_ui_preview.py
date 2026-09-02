"""UI 预览渲染工具：离屏渲染三个窗口并输出 PNG，用于界面改动的前后对比。

用法:
    python tools/render_ui_preview.py <tag>

说明:
- 通过 WA_DontShowOnScreen 渲染，窗口不会真实出现在屏幕上；
- PathManager.get_persist_dir 被重定向到临时目录，绝不读写真实 apluse_config.json；
- 样本文件名固定，列表条目文本可跨次对比（持久化目录路径等随机内容除外）。
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TAG = sys.argv[1] if len(sys.argv) > 1 else "preview"
OUT = Path(__file__).resolve().parent.parent / "ui_preview"
OUT.mkdir(exist_ok=True)

# 持久化隔离：引擎配置读写全部落到临时目录
_isolated_dir = Path(tempfile.mkdtemp(prefix="apluse_preview_cfg_"))
import core
core.PathManager.get_persist_dir = staticmethod(lambda: _isolated_dir)

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

sample_dir = Path(tempfile.mkdtemp(prefix="apluse_ui_sample_"))
(sample_dir / "子目录").mkdir()
targets = []
masks = []
for name, size in [
    ("项目资料汇总_2026年最终版_真珍贵.mp4", 5 * 1024 * 1024),
    ("短名.bin", 512),
    ("another_video_clip.avi", 128 * 1024 * 1024),
]:
    p = sample_dir / name
    p.write_bytes(os.urandom(min(size, 4096)))
    targets.append(str(p))
for i in range(6):
    p = sample_dir / "子目录" / f"面具素材_{i}_fraud_video_long_name.mp4"
    p.write_bytes(os.urandom(1024))
    masks.append(str(p))

app = QApplication.instance() or QApplication([])

from ui import MainWindow
from admin_ui import AdminWindow
from ui_dev import DeveloperWindow

main = MainWindow()
main.setAttribute(Qt.WA_DontShowOnScreen, True)
main.ui_add_mcpk_pack_paths(targets)
main.change_theme(0)
main.show()
app.processEvents()
main.grab().save(str(OUT / f"{TAG}_main.png"))

dev = DeveloperWindow(main.engine, main)
dev.setAttribute(Qt.WA_DontShowOnScreen, True)
dev.ui_add_target_paths(targets)
dev.ui_add_mask_paths(masks)
dev.show()
app.processEvents()
dev.grab().save(str(OUT / f"{TAG}_dev.png"))

admin = AdminWindow()
admin.setAttribute(Qt.WA_DontShowOnScreen, True)
admin.ui_add_target_paths(targets)
admin.ui_add_mask_paths(masks)
admin.change_theme(0)
admin.show()
app.processEvents()
admin.grab().save(str(OUT / f"{TAG}_admin.png"))

print(f"saved: {OUT}/{TAG}_main.png, {TAG}_dev.png, {TAG}_admin.png")
