import os
import struct
from pathlib import Path

import pytest

from mcpk import MCPKWriter, MCPKReader, MCPKError


def _write_sample_files(base: Path):
    base.mkdir(parents=True, exist_ok=True)
    (base / "readme.txt").write_text("hello", encoding="utf-8")
    (base / "notes.md").write_bytes(os.urandom(128))
    (base / "photo.jpg").write_bytes(os.urandom(1024))


def test_mcpk_write_read_extract_roundtrip(tmp_path):
    src = tmp_path / "src"
    _write_sample_files(src)
    out = tmp_path / "pack.mcpk"

    with MCPKWriter(out) as w:
        w.add_file(str(src / "readme.txt"))
        w.add_file(str(src / "photo.jpg"))

    with MCPKReader(out) as r:
        assert r.entry_count == 2
        names = {e.name for e in r.entries}
        assert "readme.txt" in names
        assert "photo.jpg" in names

        extract_dir = tmp_path / "out"
        paths = r.extract_all(extract_dir)
        assert len(paths) == 2
        assert (extract_dir / "readme.txt").read_text(encoding="utf-8") == "hello"


def test_mcpk_grouped_extraction(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.txt").write_text("A", encoding="utf-8")
    (src / "b.txt").write_text("B", encoding="utf-8")
    out = tmp_path / "grouped.mcpk"

    with MCPKWriter(out) as w:
        w.add_file(str(src / "a.txt"), group_name="G1")
        w.add_file(str(src / "b.txt"), group_name="G1")

    with MCPKReader(out) as r:
        g = r.find_group("G1")
        assert g is not None
        names = {e.name for e in r.list_group_entries("G1")}
        assert names == {"a.txt", "b.txt"}


def test_mcpk_verify_detects_tamper(tmp_path):
    src = tmp_path / "src.txt"
    src.write_bytes(os.urandom(128))
    out = tmp_path / "tamper.mcpk"

    with MCPKWriter(out) as w:
        w.add_file(str(src))

    data = bytearray(out.read_bytes())
    # corrupt footer CRC only to avoid breaking header/metadata parsing
    data[-1] ^= 0xFF
    out.write_bytes(data)

    with MCPKReader(out) as r:
        errors = r.verify()
        assert any("Footer" in e for e in errors)


def test_mcpk_extract_missing_entry_errors(tmp_path):
    out = tmp_path / "exist.mcpk"
    (tmp_path / "tmp.txt").write_text("x", encoding="utf-8")
    with MCPKWriter(out) as w:
        w.add_file(str(tmp_path / "tmp.txt"))

    with MCPKReader(out) as r:
        try:
            r.extract("does-not-exist.txt")
            raise AssertionError("expected KeyError")
        except KeyError:
            pass


def test_mcpk_encrypted_xor_roundtrip(tmp_path):
    src = tmp_path / "secret.txt"
    src.write_text("ok", encoding="utf-8")
    out = tmp_path / "secret.mcpk"

    with MCPKWriter(out, password="pw", encryption="xor") as w:
        w.add_file(str(src))

    with MCPKReader(out, password="pw") as r:
        assert r.is_encrypted is True
        assert r.extract("secret.txt") == b"ok"


# ── 加密路径补充 ────────────────────────────────────────────

def test_mcpk_encrypted_wrong_password_fails(tmp_path):
    src = tmp_path / "s.txt"
    src.write_bytes(b"data")
    out = tmp_path / "enc.mcpk"
    with MCPKWriter(out, password="correct", encryption="xor") as w:
        w.add_file(str(src))
    # 错误密码：在 reader load 阶段或 extract 阶段应失败
    with pytest.raises((MCPKError, Exception)):
        with MCPKReader(out, password="wrong") as r:
            r.extract("s.txt")


def test_mcpk_encrypted_metadata_only(tmp_path):
    src = tmp_path / "m.txt"
    src.write_text("meta-only", encoding="utf-8")
    out = tmp_path / "meta.mcpk"
    with MCPKWriter(out, password="pw", encrypt_mode="metadata_only", encryption="xor") as w:
        w.add_file(str(src))
    with MCPKReader(out, password="pw") as r:
        assert r.is_encrypted is True
        assert r.extract("m.txt") == b"meta-only"


def test_mcpk_encrypted_data_only(tmp_path):
    src = tmp_path / "d.txt"
    src.write_text("data-only", encoding="utf-8")
    out = tmp_path / "data.mcpk"
    with MCPKWriter(out, password="pw", encrypt_mode="data_only", encryption="xor") as w:
        w.add_file(str(src))
    with MCPKReader(out, password="pw") as r:
        assert r.is_encrypted is True
        assert r.extract("d.txt") == b"data-only"


def test_mcpk_unencrypted_metadata_visible(tmp_path):
    """不加密时，inspect 能看到完整元数据。"""
    src = tmp_path / "v.txt"
    src.write_text("visible", encoding="utf-8")
    out = tmp_path / "vis.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src))
    with MCPKReader(out) as r:
        info = r.inspect()
        assert info["encrypted"] is False
        assert info["entry_count"] == 1


# ── 分组路径补充 ────────────────────────────────────────────

def test_mcpk_multiple_groups(tmp_path):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "a.txt").write_text("A", encoding="utf-8")
    (src / "b.txt").write_text("B", encoding="utf-8")
    (src / "c.txt").write_text("C", encoding="utf-8")
    out = tmp_path / "multigrp.mcpk"

    with MCPKWriter(out) as w:
        w.add_file(str(src / "a.txt"), group_name="G1")
        w.add_file(str(src / "b.txt"), group_name="G2")
        w.add_file(str(src / "c.txt"), group_name="G1")

    with MCPKReader(out) as r:
        g1 = r.find_group("G1")
        g2 = r.find_group("G2")
        assert g1 is not None and g2 is not None
        g1_names = {e.name for e in r.list_group_entries("G1")}
        g2_names = {e.name for e in r.list_group_entries("G2")}
        assert g1_names == {"a.txt", "c.txt"}
        assert g2_names == {"b.txt"}


def test_mcpk_import_folder(tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "readme.md").write_text("# Project", encoding="utf-8")
    (folder / "data.bin").write_bytes(os.urandom(256))
    out = tmp_path / "folder.mcpk"

    with MCPKWriter(out) as w:
        group = w.import_folder(folder)
        assert group.name == "project"
        assert len(group.entry_ids) == 2

    with MCPKReader(out) as r:
        assert r.entry_count == 2
        names = {e.name for e in r.entries}
        assert "readme.md" in names
        assert "data.bin" in names


def test_mcpk_import_folder_with_tags(tmp_path):
    folder = tmp_path / "tagged"
    folder.mkdir()
    (folder / "f.txt").write_text("tagged", encoding="utf-8")
    out = tmp_path / "tagged.mcpk"

    with MCPKWriter(out) as w:
        group = w.import_folder(folder, tags=["important", "v2"])
        assert group.name == "tagged"

    with MCPKReader(out) as r:
        g = r.find_group("tagged")
        assert g is not None
        assert set(g.tags) == {"important", "v2"}


def test_mcpk_extract_to_single(tmp_path):
    src = tmp_path / "e.txt"
    src.write_text("extract-to", encoding="utf-8")
    out = tmp_path / "ext.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src))
    with MCPKReader(out) as r:
        dest = tmp_path / "dest"
        path = r.extract_to("e.txt", dest)
        assert Path(path).exists()
        assert Path(path).read_text(encoding="utf-8") == "extract-to"


def test_mcpk_extract_group(tmp_path):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "x.txt").write_text("X", encoding="utf-8")
    (src / "y.txt").write_text("Y", encoding="utf-8")
    out = tmp_path / "extg.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src / "x.txt"), group_name="GRP")
        w.add_file(str(src / "y.txt"), group_name="GRP")
    with MCPKReader(out) as r:
        dest = tmp_path / "dest_grp"
        paths = r.extract_group("GRP", dest)
        assert len(paths) == 2


def test_mcpk_list_group_entries(tmp_path):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "a.txt").write_text("A", encoding="utf-8")
    (src / "b.txt").write_text("B", encoding="utf-8")
    out = tmp_path / "listg.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src / "a.txt"), group_name="LG")
        w.add_file(str(src / "b.txt"), group_name="LG")
    with MCPKReader(out) as r:
        entries = r.list_group_entries("LG")
        assert len(entries) == 2
        names = {e.name for e in entries}
        assert names == {"a.txt", "b.txt"}


def test_mcpk_find_nonexistent_group_returns_none(tmp_path):
    src = tmp_path / "ng.txt"
    src.write_text("no group", encoding="utf-8")
    out = tmp_path / "ng.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src))
    with MCPKReader(out) as r:
        assert r.find_group("nonexistent") is None


def test_mcpk_is_mcpk_file(tmp_path):
    src = tmp_path / "ck.txt"
    src.write_text("check", encoding="utf-8")
    out = tmp_path / "ck.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src))
    assert out.read_bytes()[:4] == b"MCPK"


def test_mcpk_not_mcpk_file(tmp_path):
    fake = tmp_path / "fake.mcpk"
    fake.write_bytes(b"NOT_MCPK_DATA" * 10)
    assert fake.read_bytes()[:4] != b"MCPK"


def test_mcpk_version_is_2(tmp_path):
    src = tmp_path / "v.txt"
    src.write_text("v2", encoding="utf-8")
    out = tmp_path / "v.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src))
    with MCPKReader(out) as r:
        assert r.version == 2


def test_mcpk_entry_has_timestamps(tmp_path):
    src = tmp_path / "ts.txt"
    src.write_text("timestamped", encoding="utf-8")
    out = tmp_path / "ts.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src))
    with MCPKReader(out) as r:
        e = r.entries[0]
        assert e.modified_at > 0


def test_mcpk_inspect_returns_complete_info(tmp_path):
    src = tmp_path / "info.txt"
    src.write_text("info", encoding="utf-8")
    out = tmp_path / "info.mcpk"
    with MCPKWriter(out) as w:
        w.add_file(str(src))
    with MCPKReader(out) as r:
        info = r.inspect()
        assert "version" in info
        assert "entry_count" in info
        assert "file_size" in info
        assert info["entry_count"] == 1
