import os
from pathlib import Path
from apluse.core import disguise_file, reveal_file, is_disguised_file, DisguiseError


def _write(path: Path, size: int):
    path.write_bytes(os.urandom(size))


def test_disguise_and_reveal_roundtrip(tmp_path):
    src = tmp_path / "data.txt"
    mask = tmp_path / "cover.mp4"
    src.write_text("hello", encoding="utf-8")
    _write(mask, 512)

    out = disguise_file(str(src), str(mask), b"KEY1")
    assert is_disguised_file(out, b"KEY1")

    restored = reveal_file(out, b"KEY1")
    assert Path(restored).read_text(encoding="utf-8") == "hello"


def test_disguise_rejects_missing_target(tmp_path):
    mask = tmp_path / "mask.mp4"
    _write(mask, 32)
    try:
        disguise_file(str(tmp_path / "missing.txt"), str(mask), b"K")
        raise AssertionError("expected error")
    except FileNotFoundError:
        pass


def test_disguise_rejects_empty_mask(tmp_path):
    src = tmp_path / "a.bin"
    mask = tmp_path / "empty.mp4"
    src.write_bytes(b"abc")
    mask.write_bytes(b"")
    try:
        disguise_file(str(src), str(mask), b"K")
        raise AssertionError("expected error")
    except DisguiseError:
        pass


def test_disguise_rejects_already_disguised(tmp_path):
    src = tmp_path / "a.bin"
    mask = tmp_path / "m.mp4"
    src.write_bytes(b"abc")
    mask.write_bytes(b"maskdata")
    out = disguise_file(str(src), str(mask), b"K")
    try:
        disguise_file(out, str(mask), b"K")
        raise AssertionError("expected error")
    except DisguiseError:
        pass


def test_reveal_rejects_wrong_magic(tmp_path):
    src = tmp_path / "a.bin"
    mask = tmp_path / "m.mp4"
    src.write_bytes(b"abc")
    mask.write_bytes(b"mask")
    out = disguise_file(str(src), str(mask), b"A")
    try:
        reveal_file(out, b"B")
        raise AssertionError("expected error")
    except DisguiseError:
        pass


def test_roundtrip_preserves_utf8_name(tmp_path):
    src = tmp_path / "中文名.txt"
    mask = tmp_path / "m.mp4"
    src.write_text("ok", encoding="utf-8")
    _write(mask, 64)

    out = disguise_file(str(src), str(mask), b"U8")
    restored = reveal_file(out, b"U8")
    assert Path(restored).name == "中文名.txt"


def test_mask_larger_than_original(tmp_path):
    src = tmp_path / "tiny.bin"
    mask = tmp_path / "big.mp4"
    src.write_bytes(b"ab")
    _write(mask, 8192)

    out = disguise_file(str(src), str(mask), b"MX")
    restored = reveal_file(out, b"MX")
    assert Path(restored).read_bytes() == b"ab"


def test_reserved_outputs_force_restored_suffix(tmp_path):
    src = tmp_path / "a.txt"
    mask = tmp_path / "m.mp4"
    src.write_text("x", encoding="utf-8")
    mask.write_bytes(b"mm")
    out = disguise_file(str(src), str(mask), b"R")
    restored = reveal_file(out, b"R", reserved_output_paths=[str(tmp_path / "a.txt")])
    assert "restored" in Path(restored).name
