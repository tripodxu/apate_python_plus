"""恢复脚本模板：core._build_restore_script 以 .replace() 填充占位符后写出。

此文件内容会被原样写入生成的 {魔术字}_restore.py，修改需同步 tests/test_restore_script.py 的回归。
"""

RESTORE_SCRIPT_TEMPLATE = '''import sys
import os
import struct
from pathlib import Path

MAGIC = bytes.fromhex("__MAGIC_HEX__")
CHUNK_SIZE = 4 * 1024 * 1024
SELF_NAMES = {__SELF_NAMES_SET__}


def xor_bytes(data: bytes, key: bytes) -> bytes:
    if not key:
        return data
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent


def is_disguised_file(p: Path) -> bool:
    try:
        if p.stat().st_size < (1 + 4 + len(MAGIC)):
            return False
        with open(p, "rb") as f:
            f.seek(-len(MAGIC), os.SEEK_END)
            return f.read(len(MAGIC)) == MAGIC
    except Exception:
        return False


def _try_parse_name(raw_bytes, magic):
    """尝试从原始字节中解析文件名，优先 XOR 解密，回退明文。"""
    try:
        decoded = xor_bytes(raw_bytes, magic).decode("utf-8")
        if decoded and decoded == Path(decoded).name and decoded not in (".", ".."):
            return decoded
    except Exception:
        pass
    try:
        decoded = raw_bytes.decode("utf-8")
        if decoded and decoded == Path(decoded).name and decoded not in (".", ".."):
            return decoded
    except Exception:
        pass
    return None


def parse_metadata(f, sz):
    f.seek(-len(MAGIC), os.SEEK_END)
    if f.read(len(MAGIC)) != MAGIC:
        raise Exception("标记无效")

    # v4: 加密元数据  name_len(1B XOR) + head_len(4B XOR) + original_size(8B XOR) + magic
    try:
        if sz >= len(MAGIC) + 13:
            f.seek(-(len(MAGIC) + 13), os.SEEK_END)
            dec_meta = xor_bytes(f.read(13), MAGIC)
            nlen = dec_meta[0]
            hlen = struct.unpack("<I", dec_meta[1:5])[0]
            osize = struct.unpack("<Q", dec_meta[5:13])[0]
            npos = sz - len(MAGIC) - 13 - nlen
            hpos = npos - hlen
            if 0 <= npos <= sz and 0 <= hpos <= sz:
                f.seek(npos)
                raw = f.read(nlen)
                name = _try_parse_name(raw, MAGIC)
                if name:
                    return {"hlen": hlen, "hpos": hpos, "name": name, "osize": osize}
    except Exception:
        pass

    # v2/v3: 明文元数据  name_len(1B) + head_len(4B) + original_size(8B) + magic
    try:
        if sz >= len(MAGIC) + 13:
            f.seek(-(len(MAGIC) + 8), os.SEEK_END)
            osize = struct.unpack("<Q", f.read(8))[0]
            f.seek(-(len(MAGIC) + 12), os.SEEK_END)
            hlen = struct.unpack("<I", f.read(4))[0]
            f.seek(-(len(MAGIC) + 13), os.SEEK_END)
            nlen = struct.unpack("B", f.read(1))[0]
            npos = sz - len(MAGIC) - 13 - nlen
            hpos = npos - hlen
            if 0 <= npos <= sz and 0 <= hpos <= sz:
                f.seek(npos)
                raw_name = f.read(nlen)
                name = _try_parse_name(raw_name, MAGIC)
                if name:
                    return {"hlen": hlen, "hpos": hpos, "name": name, "osize": osize}
    except Exception:
        pass

    # v1:  name_len(1B) + head_len(4B) + magic  (无 original_size)
    f.seek(-(len(MAGIC) + 4), os.SEEK_END)
    hlen = struct.unpack("<I", f.read(4))[0]
    f.seek(-(len(MAGIC) + 5), os.SEEK_END)
    nlen = struct.unpack("B", f.read(1))[0]
    if nlen > sz:
        raise Exception("名称长度非法")
    npos = sz - len(MAGIC) - 5 - nlen
    if npos < 0:
        raise Exception("name_pos 非法")
    hpos = npos - hlen
    if hpos < 0:
        raise Exception("head_pos 非法")
    f.seek(npos)
    raw_name = f.read(nlen)
    if len(raw_name) != nlen:
        raise Exception("名称长度不足")
    # 一次性读取完毕，后续不再 seek/read，避免文件指针问题
    name = _try_parse_name(raw_name, MAGIC)
    if not name:
        # 回退：当作后缀拼接
        try:
            suffix = raw_name.decode("utf-8")
        except Exception as e:
            raise Exception(f"无法解析后缀: {e}")
        name = Path(fp_name).stem + suffix
    return {"hlen": hlen, "hpos": hpos, "name": name, "osize": hpos}


def reveal_file(fp: Path, reserved):
    global fp_name
    fp_name = fp.name
    with open(fp, "r+b") as f:
        meta = parse_metadata(f, fp.stat().st_size)
        bytes_left, read_offset = meta["hlen"], meta["hpos"]
        while bytes_left > 0:
            read_size = min(CHUNK_SIZE, bytes_left)
            f.seek(read_offset)
            chunk = f.read(read_size)
            write_offset = bytes_left - read_size
            f.seek(write_offset)
            f.write(chunk[::-1])
            read_offset += read_size
            bytes_left -= read_size
        f.truncate(meta["osize"])

    dp = fp.parent / meta["name"]
    rest = dp
    if str(dp.resolve()) in reserved:
        idx = 1
        while True:
            c = dp.with_name(f"{dp.stem}_restored_{idx}{dp.suffix}")
            if str(c.resolve()) not in reserved and not c.exists():
                rest = c
                break
            idx += 1
    fp.replace(rest)
    return rest


fp_name = ""


def main():
    global fp_name
    bd = get_base_dir()
    print(f"扫描: {bd}\\n魔术字: {MAGIC.hex()}\\n" + "-" * 40)
    res, fail = 0, 0
    reserved = {str(p.resolve()) for p in bd.rglob("*") if p.is_file()}
    for p in bd.rglob("*"):
        if p.is_file() and p.name.lower() not in SELF_NAMES:
            try:
                reserved.discard(str(p.resolve()))
                if is_disguised_file(p):
                    fp_name = p.name
                    np = reveal_file(p, reserved)
                    reserved.add(str(np.resolve()))
                    res += 1
                    print(f"[恢复] {p.name} -> {np.name}")
            except Exception as e:
                fail += 1
                print(f"[失败] {p.name} -> {e}")
    print(f"\\n完成: 成功 {res}, 失败 {fail}")
    input("按回车退出...")


if __name__ == "__main__":
    main()
'''
