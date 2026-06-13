import os
import struct
from pathlib import Path
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
