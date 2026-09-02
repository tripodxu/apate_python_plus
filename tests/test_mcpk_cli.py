"""mcpk CLI 命令覆盖测试：直接调用 cmd_* 函数（无需 subprocess）。

覆盖：cmd_pack（普通/分组/加密）、cmd_list（文本/JSON/类型过滤）、
cmd_groups、cmd_extract（单个/全部/分组）、cmd_inspect、cmd_verify、_fmt_size。
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from apluse.mcpk.cli import (
    cmd_pack, cmd_list, cmd_groups, cmd_extract,
    cmd_inspect, cmd_verify, _fmt_size,
)


def _sample_files(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.txt").write_text("hello", encoding="utf-8")
    (d / "b.md").write_bytes(os.urandom(128))
    (d / "photo.jpg").write_bytes(os.urandom(512))
    return d


def _args(**kwargs):
    return SimpleNamespace(**kwargs)


# ── _fmt_size ─────────────────────────────────────────────────

def test_fmt_size_units():
    assert _fmt_size(0) == "0B"
    assert "KB" in _fmt_size(2048)
    assert "MB" in _fmt_size(1024 * 1024)
    assert "GB" in _fmt_size(1024 ** 3)
    assert "TB" in _fmt_size(1024 ** 4)


# ── cmd_pack ──────────────────────────────────────────────────

def test_cmd_pack_single_file(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "out.mcpk"
    args = _args(sources=[str(src / "a.txt")], output=str(out),
                 prefix=None, group=None, auto_group=False,
                 index=None, base_dir=".", password=None,
                 encrypt_mode="full", encryption="xor")
    cmd_pack(args)
    assert out.exists()
    assert out.stat().st_size > 0
    captured = capsys.readouterr()
    assert "打包完成" in captured.out


def test_cmd_pack_directory(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "dir.mcpk"
    args = _args(sources=[str(src)], output=str(out),
                 prefix=None, group=None, auto_group=False,
                 index=None, base_dir=".", password=None,
                 encrypt_mode="full", encryption="xor")
    cmd_pack(args)
    assert out.exists()
    captured = capsys.readouterr()
    assert "打包完成" in captured.out


def test_cmd_pack_with_group(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "grp.mcpk"
    args = _args(sources=[str(src / "a.txt")], output=str(out),
                 prefix=None, group="G1", auto_group=False,
                 index=None, base_dir=".", password=None,
                 encrypt_mode="full", encryption="xor")
    cmd_pack(args)
    assert out.exists()


def test_cmd_pack_encrypted(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "enc.mcpk"
    args = _args(sources=[str(src / "a.txt")], output=str(out),
                 prefix=None, group=None, auto_group=False,
                 index=None, base_dir=".", password="pw",
                 encrypt_mode="full", encryption="xor")
    cmd_pack(args)
    assert out.exists()
    captured = capsys.readouterr()
    assert "加密" in captured.out


def test_cmd_pack_nonexistent_source_exits(tmp_path):
    out = tmp_path / "fail.mcpk"
    args = _args(sources=[str(tmp_path / "nope.txt")], output=str(out),
                 prefix=None, group=None, auto_group=False,
                 index=None, base_dir=".", password=None,
                 encrypt_mode="full", encryption="xor")
    with pytest.raises(SystemExit):
        cmd_pack(args)


# ── cmd_list ──────────────────────────────────────────────────

def test_cmd_list_text(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "l.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    cmd_list(_args(file=str(out), type=None, json=False, password=None))
    captured = capsys.readouterr()
    assert "a.txt" in captured.out
    assert "条目数: 1" in captured.out


def test_cmd_list_json(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "lj.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    cmd_list(_args(file=str(out), type=None, json=True, password=None))
    captured = capsys.readouterr()
    # cmd_list --json 输出可能含前导非 JSON 行（加密信息等），找到 JSON 开头
    json_start = captured.out.index("{")
    data = json.loads(captured.out[json_start:])
    assert data["entry_count"] == 1


def test_cmd_list_type_filter(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "lt.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    cmd_list(_args(file=str(out), type="doc", json=False, password=None))
    captured = capsys.readouterr()
    assert "a.txt" in captured.out
    cmd_list(_args(file=str(out), type="video", json=False, password=None))
    captured = capsys.readouterr()
    assert "条目数: 0" in captured.out


# ── cmd_groups ────────────────────────────────────────────────

def test_cmd_groups(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "g.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group="MyGroup", auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    cmd_groups(_args(file=str(out), password=None))
    captured = capsys.readouterr()
    assert "MyGroup" in captured.out


# ── cmd_extract ───────────────────────────────────────────────

def test_cmd_extract_single(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "e.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    dest = tmp_path / "out"
    cmd_extract(_args(file=str(out), output_dir=str(dest), name="a.txt", group=None, password=None))
    assert (dest / "a.txt").read_text(encoding="utf-8") == "hello"
    captured = capsys.readouterr()
    assert "已提取" in captured.out


def test_cmd_extract_all(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "ea.mcpk"
    cmd_pack(_args(sources=[str(src)], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    dest = tmp_path / "out_all"
    cmd_extract(_args(file=str(out), output_dir=str(dest), name=None, group=None, password=None))
    captured = capsys.readouterr()
    assert "已提取" in captured.out


def test_cmd_extract_nonexistent_exits(tmp_path):
    src = _sample_files(tmp_path)
    out = tmp_path / "ef.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    dest = tmp_path / "out_fail"
    with pytest.raises(SystemExit):
        cmd_extract(_args(file=str(out), output_dir=str(dest), name="missing.txt", group=None, password=None))


# ── cmd_inspect ───────────────────────────────────────────────

def test_cmd_inspect(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "i.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    cmd_inspect(_args(file=str(out), password=None))
    captured = capsys.readouterr()
    json_start = captured.out.index("{")
    data = json.loads(captured.out[json_start:])
    assert data["entry_count"] == 1


# ── cmd_verify ────────────────────────────────────────────────

def test_cmd_verify_clean(tmp_path, capsys):
    src = _sample_files(tmp_path)
    out = tmp_path / "v.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    cmd_verify(_args(file=str(out), password=None))
    captured = capsys.readouterr()
    assert "验证通过" in captured.out


def test_cmd_verify_tampered_exits(tmp_path):
    src = _sample_files(tmp_path)
    out = tmp_path / "vt.mcpk"
    cmd_pack(_args(sources=[str(src / "a.txt")], output=str(out),
                   prefix=None, group=None, auto_group=False,
                   index=None, base_dir=".", password=None,
                   encrypt_mode="full", encryption="xor"))
    # 篡改文件尾部
    data = bytearray(out.read_bytes())
    data[-1] ^= 0xFF
    out.write_bytes(data)
    with pytest.raises(SystemExit):
        cmd_verify(_args(file=str(out), password=None))
