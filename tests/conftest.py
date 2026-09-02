"""共享测试夹具：将 PathManager 指向临时目录，避免测试读写仓库根目录的真实 apluse_config.json。"""
import pytest

from core import PathManager


@pytest.fixture(autouse=True)
def isolated_persist_dir(tmp_path, monkeypatch):
    """每条测试自动隔离持久化目录；DisguiseEngine 的配置读写只落在 tmp_path。"""
    monkeypatch.setattr(PathManager, "get_persist_dir", staticmethod(lambda: tmp_path))
    return tmp_path
