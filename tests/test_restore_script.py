"""恢复脚本模板回归测试。

core._RESTORE_SCRIPT_TEMPLATE 决定生成的 Windows .exe / Android apk 能否真正还原文件，
一旦被改坏会静默影响所有下游恢复工具，因此必须验证：
1. 生成的脚本语法合法、占位符全部替换；
2. 模板内的 is_disguised_file / reveal_file 与 core 主引擎的 disguise_file 互通（往返一致）。
"""
import os
from pathlib import Path

import pytest

from apluse.core import _build_restore_script, disguise_file, is_disguised_file

MAGIC_HEX = "7e3c9a55"
MAGIC = bytes.fromhex(MAGIC_HEX)


def _load_template_namespace():
    script = _build_restore_script(MAGIC_HEX, "x_restore.py")
    assert "__MAGIC_HEX__" not in script and "__SELF_NAMES_SET__" not in script
    # __name__ 不能是 "__main__"，否则会触发模板末尾的 main()（内含 input() 阻塞）
    namespace = {"__name__": "restore_script_under_test"}
    exec(compile(script, "restore_script_under_test.py", "exec"), namespace)
    return namespace


def test_restore_script_compiles_and_replaces_placeholders():
    namespace = _load_template_namespace()
    assert namespace["MAGIC"] == MAGIC
    assert callable(namespace["reveal_file"])
    assert callable(namespace["parse_metadata"])


def test_restore_script_reveals_core_disguised_file(tmp_path):
    namespace = _load_template_namespace()

    src = tmp_path / "doc.txt"
    src.write_text("hello-restore-template", encoding="utf-8")
    mask = tmp_path / "cover.mp4"
    mask.write_bytes(os.urandom(2048))

    disguised = Path(disguise_file(str(src), str(mask), MAGIC))
    assert is_disguised_file(str(disguised), MAGIC)
    assert namespace["is_disguised_file"](disguised) is True

    restored = namespace["reveal_file"](disguised, set())
    assert Path(restored).name == "doc.txt"
    assert Path(restored).read_text(encoding="utf-8") == "hello-restore-template"


def test_restore_script_rejects_wrong_magic(tmp_path):
    namespace = _load_template_namespace()
    # 文件足够大（>= 1+4+len(MAGIC)）以越过尺寸捷径，真正走到魔术字比较分支
    foreign = tmp_path / "x.bin"
    foreign.write_bytes(b"0123456789abcdef")
    assert namespace["is_disguised_file"](foreign) is False


@pytest.mark.parametrize("magic_hex", ["05", "7e3c9a55", "aa" * 32])
def test_restore_script_roundtrip_various_magic_lengths(tmp_path, magic_hex):
    """引擎允许 1~32 字节魔术字，模板在各长度下都应能往返还原。"""
    script = _build_restore_script(magic_hex, "x_restore.py")
    namespace = {"__name__": "restore_script_under_test"}
    exec(compile(script, "restore_script_under_test.py", "exec"), namespace)
    magic = bytes.fromhex(magic_hex)

    src = tmp_path / "var.txt"
    src.write_text(f"roundtrip-{len(magic)}", encoding="utf-8")
    mask = tmp_path / "cover.mp4"
    mask.write_bytes(os.urandom(1024))

    disguised = Path(disguise_file(str(src), str(mask), magic))
    restored = namespace["reveal_file"](disguised, set())
    assert Path(restored).name == "var.txt"
    assert Path(restored).read_text(encoding="utf-8") == f"roundtrip-{len(magic)}"
