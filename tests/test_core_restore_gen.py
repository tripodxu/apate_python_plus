"""core.generate_restore_exe / generate_restore_apk 测试。

用 monkeypatch 假掉 subprocess/PyInstaller/Gradle，只测逻辑分支，
不真打包。覆盖：_get_real_python、_ensure_pyinstaller、
generate_restore_exe（成功/失败/图标）、generate_restore_apk（无Gradle/成功/失败）。
"""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import DisguiseEngine, DisguiseError, PathManager, _build_restore_script


def _mkengine(tmp_path):
    engine = DisguiseEngine()
    engine.parse_and_set_magic("AABB")
    return engine


# ── _get_real_python ──────────────────────────────────────────

def test_get_real_python_normal(tmp_path):
    e = _mkengine(tmp_path)
    result = e._get_real_python()
    assert result == sys.executable


def test_get_real_python_frozen(tmp_path, monkeypatch):
    e = _mkengine(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/python" if x == "python" else None)
    assert e._get_real_python() == "python"


def test_get_real_python_frozen_falls_back_to_py(tmp_path, monkeypatch):
    e = _mkengine(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("shutil.which", lambda x: "py" if x == "py" else None)
    assert e._get_real_python() == "py"


def test_get_real_python_frozen_no_python_raises(tmp_path, monkeypatch):
    e = _mkengine(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("shutil.which", lambda x: None)
    with pytest.raises(DisguiseError, match="Python"):
        e._get_real_python()


# ── _ensure_pyinstaller ──────────────────────────────────────

def test_ensure_pyinstaller_already_installed(tmp_path):
    e = _mkengine(tmp_path)
    logs = []
    mock_completed = SimpleNamespace(returncode=0)
    mock_run = MagicMock(return_value=mock_completed)
    with patch("core.subprocess.run", mock_run):
        e._ensure_pyinstaller(logs.append, lambda: None, "python")
    assert mock_run.call_count == 1
    assert not logs  # 不应有安装日志


def test_ensure_pyinstaller_installs_when_missing(tmp_path):
    e = _mkengine(tmp_path)
    logs = []
    # 第一次 run (--version) 失败，触发安装
    mock_run = MagicMock(return_value=SimpleNamespace(returncode=1))
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["Installing...", "Done"])
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0
    mock_popen = MagicMock(return_value=mock_proc)
    with patch("core.subprocess.run", mock_run), \
         patch("core.subprocess.Popen", mock_popen):
        e._ensure_pyinstaller(logs.append, lambda: None, "python")
    assert any("自动安装" in l for l in logs)


def test_ensure_pyinstaller_install_fails_raises(tmp_path):
    e = _mkengine(tmp_path)
    logs = []
    mock_run = MagicMock(return_value=SimpleNamespace(returncode=1))
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["Error"])
    mock_proc.wait.return_value = 1
    mock_proc.returncode = 1
    mock_popen = MagicMock(return_value=mock_proc)
    with patch("core.subprocess.run", mock_run), \
         patch("core.subprocess.Popen", mock_popen):
        with pytest.raises(DisguiseError, match="安装"):
            e._ensure_pyinstaller(logs.append, lambda: None, "python")


# ── generate_restore_exe ──────────────────────────────────────

def test_generate_restore_exe_success(tmp_path):
    e = _mkengine(tmp_path)
    output_dir = tmp_path / "dist"
    logs = []

    mock_run = MagicMock(return_value=SimpleNamespace(returncode=0))
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["Building...", "Success"])
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0
    mock_popen = MagicMock(return_value=mock_proc)

    with patch("core.subprocess.run", mock_run), \
         patch("core.subprocess.Popen", mock_popen), \
         patch("core.PathManager.get_resource_dir", return_value=tmp_path):
        result = e.generate_restore_exe(output_dir, logs.append)

    assert result.name == f"{e.get_magic_bytes().hex()}_restore.exe"
    assert result.parent == output_dir
    assert any("PyInstaller" in l for l in logs)


def test_generate_restore_exe_pyinstaller_fails(tmp_path):
    e = _mkengine(tmp_path)
    output_dir = tmp_path / "dist"
    logs = []

    mock_run = MagicMock(return_value=SimpleNamespace(returncode=0))
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["Error: build failed"])
    mock_proc.wait.return_value = 1
    mock_proc.returncode = 1
    mock_popen = MagicMock(return_value=mock_proc)

    with patch("core.subprocess.run", mock_run), \
         patch("core.subprocess.Popen", mock_popen), \
         patch("core.PathManager.get_resource_dir", return_value=tmp_path):
        with pytest.raises(DisguiseError, match="打包过程失败"):
            e.generate_restore_exe(output_dir, logs.append)


def test_generate_restore_exe_cleanup_removes_temp_script(tmp_path):
    e = _mkengine(tmp_path)
    output_dir = tmp_path / "dist"
    logs = []

    mock_run = MagicMock(return_value=SimpleNamespace(returncode=0))
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["OK"])
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0
    mock_popen = MagicMock(return_value=mock_proc)

    with patch("core.subprocess.run", mock_run), \
         patch("core.subprocess.Popen", mock_popen), \
         patch("core.PathManager.get_resource_dir", return_value=tmp_path):
        e.generate_restore_exe(output_dir, logs.append)

    # 临时脚本应已被清理
    script = PathManager.get_persist_dir() / f"{e.get_magic_bytes().hex()}_restore.py"
    assert not script.exists()


# ── generate_restore_apk ──────────────────────────────────────

def test_generate_restore_apk_no_gradle(tmp_path):
    e = _mkengine(tmp_path)
    output_dir = tmp_path / "apk_out"
    logs = []

    with patch("shutil.which", return_value=None), \
         patch("core.PathManager.get_resource_dir", return_value=tmp_path):
        result = e.generate_restore_apk(output_dir, logs.append)

    # 无 Gradle 时应返回项目目录
    assert result.is_dir()
    assert any("Android Studio" in l for l in logs)


def test_generate_restore_apk_gradle_success(tmp_path):
    e = _mkengine(tmp_path)
    output_dir = tmp_path / "apk_out"
    logs = []

    def fake_which(name):
        return "/usr/bin/gradle" if "gradle" in name.lower() else None

    mock_proc = MagicMock()
    mock_proc.stdout = iter(["BUILD SUCCESSFUL"])
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0

    def fake_popen(*args, **kwargs):
        # 模拟 APK 文件被创建
        project_dir = output_dir / "apluse_restore_android"
        apk_dir = project_dir / "app" / "build" / "outputs" / "apk" / "release"
        apk_dir.mkdir(parents=True, exist_ok=True)
        (apk_dir / "app-release-unsigned.apk").write_bytes(b"fake apk")
        return mock_proc

    with patch("shutil.which", fake_which), \
         patch("core.subprocess.Popen", side_effect=fake_popen), \
         patch("core.PathManager.get_resource_dir", return_value=tmp_path):
        result = e.generate_restore_apk(output_dir, logs.append)

    assert result.name == "apluse_restore.apk"
    assert any("编译成功" in l for l in logs)


def test_generate_restore_apk_gradle_fails(tmp_path):
    e = _mkengine(tmp_path)
    output_dir = tmp_path / "apk_out"
    logs = []

    def fake_which(name):
        return "/usr/bin/gradle" if "gradle" in name.lower() else None

    mock_proc = MagicMock()
    mock_proc.stdout = iter(["BUILD FAILED"])
    mock_proc.wait.return_value = 1
    mock_proc.returncode = 1
    mock_popen = MagicMock(return_value=mock_proc)

    with patch("shutil.which", fake_which), \
         patch("core.subprocess.Popen", mock_popen), \
         patch("core.PathManager.get_resource_dir", return_value=tmp_path):
        result = e.generate_restore_apk(output_dir, logs.append)

    # Gradle 失败应返回项目目录
    assert result.is_dir()
    assert any("Android Studio" in l for l in logs)
