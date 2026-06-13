import os
import json
from pathlib import Path
from core import (
    PathManager,
    normalize_config,
    load_config,
    save_config,
    format_file_size,
    magic_to_display_text,
    build_non_conflicting_path,
    collect_files_from_paths,
)


def test_normalize_config_returns_defaults_for_invalid_input():
    result = normalize_config("not-a-dict")
    assert result["mask_library"] == []
    assert isinstance(result["magic_hex"], str)
    assert result["theme_index"] == 0


def test_normalize_config_rejects_long_magic():
    data = {"magic_hex": "aa" * 64}
    result = normalize_config(data)
    assert len(bytes.fromhex(result["magic_hex"])) <= 32


def test_save_then_load_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(PathManager, "get_persist_dir", staticmethod(lambda: tmp_path))
    cfg = {"mask_library": [], "magic_hex": "AABB", "theme_index": 2}
    save_config(cfg)
    loaded = load_config()
    assert loaded["magic_hex"] == "AABB"
    assert loaded["theme_index"] == 2


def test_load_config_migrates_old_config(tmp_path, monkeypatch):
    monkeypatch.setattr(PathManager, "get_persist_dir", staticmethod(lambda: tmp_path))
    old = tmp_path / "mask_config.json"
    old.write_text(json.dumps({"mask_library": [], "magic_hex": "1122"}), encoding="utf-8")
    loaded = load_config()
    assert (tmp_path / "apluse_config.json").exists()
    assert loaded["magic_hex"] == "1122"


def test_format_file_size_units():
    assert format_file_size(0) == "0 B"
    assert "KB" in format_file_size(2048)
    assert "MB" in format_file_size(1024 * 1024)
    assert "GB" in format_file_size(1024 ** 3 + 1)


def test_magic_display_contains_text_for_ascii():
    text = magic_to_display_text(b"TEST")
    assert "TEST" in text
    assert "HEX=" in text


def test_build_non_conflicting_path_prefers_original(tmp_path):
    target = tmp_path / "a.mp4"
    result = build_non_conflicting_path(target, "x")
    assert result == target


def test_build_non_conflicting_path_avoids_existing(tmp_path):
    target = tmp_path / "a.mp4"
    target.write_bytes(b"1")
    result = build_non_conflicting_path(target, "tag")
    assert result != target
    assert "a_tag_" in result.name


def test_collect_files_from_paths_deduplicates(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    result = collect_files_from_paths([str(f), str(f)])
    assert result == [str(f.resolve())]


def test_collect_files_from_paths_recurses_dir(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    (d / "a.txt").write_text("a", encoding="utf-8")
    (d / "b.txt").write_text("b", encoding="utf-8")
    result = collect_files_from_paths([str(d)])
    assert len(result) == 2
