"""GUI 离屏冒烟测试：不弹真实窗口，验证三个窗口类的完整构建与主题切换路径。"""
import pytest

# 必须先检查依赖再导入 ui/admin_ui/ui_dev（它们顶层就 import PyQt5）
pytest.importorskip("PyQt5")


def _ensure_app():
    from PyQt5.QtWidgets import QApplication
    try:
        return QApplication.instance() or QApplication([])
    except Exception as e:  # 无 offscreen 插件等环境限制时跳过，不算失败
        pytest.skip(f"QApplication unavailable: {e}")


def test_main_window_builds_and_switches_theme(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from apluse.ui import MainWindow
    app = _ensure_app()
    win = MainWindow()
    win.show()
    app.processEvents()
    win.change_theme(3)
    app.processEvents()
    win.close()


def test_admin_window_builds(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from apluse.admin_ui import AdminWindow
    app = _ensure_app()
    win = AdminWindow()
    win.show()
    app.processEvents()
    win.close()


def test_developer_window_builds(monkeypatch, isolated_persist_dir):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace
    from apluse.core import DisguiseEngine
    from apluse.ui_dev import DeveloperWindow
    app = _ensure_app()
    engine = DisguiseEngine()
    # DeveloperWindow 会读取 main_window 的 log_file_path 与 styleSheet() 以继承主题
    parent = SimpleNamespace(log_file_path=isolated_persist_dir / "apluse.log", styleSheet=lambda: "")
    win = DeveloperWindow(engine, parent)
    win.show()
    app.processEvents()
    win.close()


# ── 列表条目与密钥信息的展示回归 ──────────────────────────────

def _sample_file(tmp_path, name="样本_中文长文件名_2026最终版.mp4", size=2048):
    f = tmp_path / name
    f.write_bytes(b"x" * size)
    return f


def test_main_window_item_shows_name_with_tooltip(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from pathlib import Path
    from PyQt5.QtCore import Qt
    from apluse.ui import MainWindow
    app = _ensure_app()
    win = MainWindow()
    f = _sample_file(tmp_path)
    win.ui_add_mcpk_pack_paths([str(f)])
    item = win.mcpk_pack_list.item(0)
    assert item is not None
    assert item.text() == f"{f.name}    [2.0 KB]"
    assert item.data(Qt.UserRole) == str(f)
    assert item.toolTip() == str(f)
    win.close()


def test_dev_window_item_shows_name_with_tooltip(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace
    from PyQt5.QtCore import Qt
    from apluse.core import DisguiseEngine
    from apluse.ui_dev import DeveloperWindow
    app = _ensure_app()
    engine = DisguiseEngine()
    parent = SimpleNamespace(log_file_path=tmp_path / "apluse.log", styleSheet=lambda: "")
    win = DeveloperWindow(engine, parent)
    f = _sample_file(tmp_path)
    win.ui_add_target_paths([str(f)])
    item = win.target_list.item(0)
    assert item.text() == f"{f.name}    [2.0 KB]"
    assert item.data(Qt.UserRole) == str(f)
    assert item.toolTip() == str(f)
    win.close()


def test_dev_magic_label_compact_and_tooltip(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace
    from apluse.core import DisguiseEngine
    from apluse.ui_dev import DeveloperWindow
    app = _ensure_app()
    engine = DisguiseEngine()
    parent = SimpleNamespace(log_file_path=tmp_path / "apluse.log", styleSheet=lambda: "")
    win = DeveloperWindow(engine, parent)

    # 可打印 ASCII：显示 文本= 段；非 UTF-8 可打印字节：只显示 HEX，BYTES 原始串只存在于 tooltip
    engine.parse_and_set_magic("DGSK")
    win.refresh_magic_ui()
    assert win.magic_info_label.text() == "生效指令：HEX=4447534B ｜ 文本=DGSK"
    full = win.magic_info_label.toolTip()
    assert "HEX=" in full and "BYTES=" in full

    engine.parse_and_set_magic("AB09")
    win.refresh_magic_ui()
    assert win.magic_info_label.text() == "生效指令：HEX=AB09"
    assert "文本=" not in win.magic_info_label.text()
    assert "BYTES=" in win.magic_info_label.toolTip()
    win.close()


def test_admin_delete_removes_exact_path_not_same_name(monkeypatch, tmp_path):
    """两个不同目录下的同名文件，只应删除被选中的那一个（旧实现按文件名匹配会误删两个）。"""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import Qt
    from apluse.admin_ui import AdminWindow
    app = _ensure_app()
    win = AdminWindow()
    d1 = tmp_path / "dir1"; d1.mkdir()
    d2 = tmp_path / "dir2"; d2.mkdir()
    f1 = d1 / "same.mp4"; f1.write_bytes(b"1" * 1024)
    f2 = d2 / "same.mp4"; f2.write_bytes(b"2" * 1024)
    win.ui_add_target_paths([str(f1), str(f2)])
    assert len(win.engine.target_files) == 2

    win.target_list.item(1).setSelected(True)  # 只选中第二个
    win._delete_selected()
    assert win.engine.target_files == [str(f1)]

    # 悬停提示与大小容错：不存在的文件显示 (?) 而不是崩溃
    missing = tmp_path / "gone.mp4"
    win.engine.target_files.append(str(missing))
    win.refresh_target_list()
    item = win.target_list.item(1)
    assert item.text() == "gone.mp4  (?)"
    assert item.toolTip() == str(missing)
    win.close()
