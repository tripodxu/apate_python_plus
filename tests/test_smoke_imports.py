"""冒烟测试：确保所有模块在当前解释器下可编译、可导入。

专防"语法级"回归（例如 f-string 表达式含反斜杠在 Python 3.8~3.11 直接 SyntaxError）。
"""
import importlib

import pytest


def test_core_modules_import():
    for name in ("apluse.core", "apluse.themes", "apluse.android_templates", "apluse.mcpk"):
        importlib.import_module(name)


def test_gui_modules_import():
    pytest.importorskip("PyQt5")
    pytest.importorskip("PyQt5.QtMultimedia")
    for name in ("apluse.ui", "apluse.ui_dev", "apluse.admin_ui"):
        importlib.import_module(name)
