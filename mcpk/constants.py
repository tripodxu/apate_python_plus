"""MCPK 格式常量和枚举定义。"""

import struct
from enum import IntEnum

# ── 魔数和版本 ──────────────────────────────────────────────
MAGIC = b"MCPK"
VERSION = 2  # v2: Magic Index + Group + VIDEO + 时间戳 + 可选加密

# ── v2 子段魔数 ────────────────────────────────────────────
MAGIC_INDEX_MAGIC       = b"MGIX"
GROUP_INDEX_MAGIC       = b"GRPX"
ENCRYPTION_PARAMS_MAGIC = b"ENC0"

# ── 固定大小 ────────────────────────────────────────────────
HEADER_SIZE        = 64
FOOTER_SIZE        = 16
MAGIC_ENTRY_SIZE   = 48   # Magic Index 中每条目固定 48 字节
ENCRYPTION_PARAMS_SIZE = 56  # Encryption Params 区固定 56 字节

# ── struct 格式 ─────────────────────────────────────────────
# v2 Header (64 字节):
#   magic(4s) + version(H) + flags(H) + packed_at(Q)
#   + ep_offset(Q) + ep_size(Q)
#   + entry_count(I) + group_count(I)
#   + group_index_offset(Q) + group_index_size(Q)
#   + toc_offset(Q)
# 注意: Magic Index 紧接 Header(或 ep) 之后，偏移 = HEADER_SIZE + ep_size
HEADER_FMT = "<4sHH Q Q Q I I Q Q Q"
HEADER_SIZE_CALC = struct.calcsize(HEADER_FMT)  # 64

# Footer: magic(4s) + toc_offset(Q) + footer_crc(I)
FOOTER_FMT = "<4sQI"
FOOTER_SIZE_CALC = struct.calcsize(FOOTER_FMT)  # 16

# TOC Entry 固定部分 (50 字节):
#   type(B) + compression(B) + reserved(2s) + crc32(I)
#   + created_at(Q) + modified_at(Q)
#   + original_size(Q) + stored_size(Q) + blob_offset(Q) + name_len(H)
TOC_ENTRY_FIXED_FMT = "<BB2sI Q Q Q Q Q H"
TOC_ENTRY_FIXED_SIZE = struct.calcsize(TOC_ENTRY_FIXED_FMT)  # 50

# Encryption Params 区 (56 字节):
#   params_magic(4s) + kdf_type(B) + encrypt_mode(B) + reserved(2s)
#   + salt(16s) + control_key_hash(32s)
ENCRYPTION_PARAMS_FMT = "<4sBB 2s 16s 32s"
ENCRYPTION_PARAMS_SIZE_CALC = struct.calcsize(ENCRYPTION_PARAMS_FMT)  # 56

# Magic Index 头部: magic(4s) + entry_count(I) + index_size(I)
MAGIC_INDEX_HEADER_FMT = "<4sII"
MAGIC_INDEX_HEADER_SIZE = struct.calcsize(MAGIC_INDEX_HEADER_FMT)  # 12

# Magic Entry 固定部分 (48 字节):
#   entry_id(I) + entry_type(B) + group_id(B) + magic_len(H)
#   + magic_bytes(32s) + name_len(H) + reserved(6s)
MAGIC_ENTRY_FMT = "<IBB H 32s H 6s"
MAGIC_ENTRY_SIZE = struct.calcsize(MAGIC_ENTRY_FMT)  # 48

# Group Index 头部: magic(4s) + group_count(I) + relation_count(I) + index_size(I)
GROUP_INDEX_HEADER_FMT = "<4sIII"
GROUP_INDEX_HEADER_SIZE = struct.calcsize(GROUP_INDEX_HEADER_FMT)  # 16


# ── 枚举 ───────────────────────────────────────────────────

class EntryType(IntEnum):
    """条目类型枚举。"""
    DOCUMENT = 0x01
    IMAGE    = 0x02
    AUDIO    = 0x03
    VIDEO    = 0x04


class Compression(IntEnum):
    """压缩算法枚举。"""
    NONE = 0x00
    ZLIB = 0x01
    ZSTD = 0x02
    LZ4  = 0x03


class GroupType(IntEnum):
    """分组类型枚举。"""
    GENERIC        = 0x00
    VIDEO_SUBTITLE = 0x01
    DOCUMENT_SET   = 0x02
    MEDIA_ALBUM    = 0x03
    COURSE         = 0x04
    MEETING        = 0x05


class RelationType(IntEnum):
    """组间关系类型枚举。"""
    SEQUEL      = 0x00
    RELATED     = 0x01
    DEPENDS_ON  = 0x02
    VARIANT     = 0x03
    REFERENCES  = 0x04


class EncryptionMode(IntEnum):
    """加密模式枚举。"""
    NONE           = 0x00  # 不加密
    FULL           = 0x01  # 控制区 + 数据区全部加密
    METADATA_ONLY  = 0x02  # 仅加密控制区
    DATA_ONLY      = 0x03  # 仅加密数据区


class KdfType(IntEnum):
    """密钥派生函数类型。"""
    SHA256_XOR = 0x01  # SHA-256 + XOR 流加密


# ── 无分组标记 ──────────────────────────────────────────────
NO_GROUP = 0xFF


# ── 扩展名 → (EntryType, MIME, Compression) 映射 ─────────
EXTENSION_MAP = {
    # 文档
    ".md":   (EntryType.DOCUMENT, "text/markdown",      Compression.ZLIB),
    ".txt":  (EntryType.DOCUMENT, "text/plain",          Compression.ZLIB),
    ".json": (EntryType.DOCUMENT, "application/json",    Compression.ZLIB),
    ".csv":  (EntryType.DOCUMENT, "text/csv",            Compression.ZLIB),
    ".html": (EntryType.DOCUMENT, "text/html",           Compression.ZLIB),
    ".htm":  (EntryType.DOCUMENT, "text/html",           Compression.ZLIB),
    ".pdf":  (EntryType.DOCUMENT, "application/pdf",     Compression.NONE),
    ".docx": (EntryType.DOCUMENT, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", Compression.NONE),
    ".doc":  (EntryType.DOCUMENT, "application/msword",  Compression.NONE),
    ".xlsx": (EntryType.DOCUMENT, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", Compression.NONE),
    ".pptx": (EntryType.DOCUMENT, "application/vnd.openxmlformats-officedocument.presentationml.presentation", Compression.NONE),
    ".xml":  (EntryType.DOCUMENT, "application/xml",     Compression.ZLIB),
    ".yaml": (EntryType.DOCUMENT, "application/x-yaml",  Compression.ZLIB),
    ".yml":  (EntryType.DOCUMENT, "application/x-yaml",  Compression.ZLIB),
    ".srt":  (EntryType.DOCUMENT, "application/x-subrip", Compression.ZLIB),
    ".vtt":  (EntryType.DOCUMENT, "text/vtt",            Compression.ZLIB),
    ".ass":  (EntryType.DOCUMENT, "text/x-ssa",          Compression.ZLIB),

    # 图片
    ".jpg":  (EntryType.IMAGE, "image/jpeg",    Compression.NONE),
    ".jpeg": (EntryType.IMAGE, "image/jpeg",    Compression.NONE),
    ".png":  (EntryType.IMAGE, "image/png",     Compression.NONE),
    ".gif":  (EntryType.IMAGE, "image/gif",     Compression.NONE),
    ".webp": (EntryType.IMAGE, "image/webp",    Compression.NONE),
    ".bmp":  (EntryType.IMAGE, "image/bmp",     Compression.ZLIB),
    ".tiff": (EntryType.IMAGE, "image/tiff",    Compression.ZLIB),
    ".tif":  (EntryType.IMAGE, "image/tiff",    Compression.ZLIB),
    ".svg":  (EntryType.IMAGE, "image/svg+xml", Compression.ZLIB),
    ".ico":  (EntryType.IMAGE, "image/x-icon",  Compression.NONE),

    # 音频
    ".mp3":  (EntryType.AUDIO, "audio/mpeg",  Compression.NONE),
    ".wav":  (EntryType.AUDIO, "audio/wav",   Compression.ZSTD),
    ".ogg":  (EntryType.AUDIO, "audio/ogg",   Compression.NONE),
    ".flac": (EntryType.AUDIO, "audio/flac",  Compression.NONE),
    ".aac":  (EntryType.AUDIO, "audio/aac",   Compression.NONE),
    ".m4a":  (EntryType.AUDIO, "audio/mp4",   Compression.NONE),
    ".wma":  (EntryType.AUDIO, "audio/x-ms-wma", Compression.NONE),

    # 视频
    ".mp4":  (EntryType.VIDEO, "video/mp4",         Compression.NONE),
    ".mkv":  (EntryType.VIDEO, "video/x-matroska",  Compression.NONE),
    ".avi":  (EntryType.VIDEO, "video/x-msvideo",   Compression.NONE),
    ".mov":  (EntryType.VIDEO, "video/quicktime",   Compression.NONE),
    ".webm": (EntryType.VIDEO, "video/webm",        Compression.NONE),
    ".flv":  (EntryType.VIDEO, "video/x-flv",       Compression.NONE),
    ".wmv":  (EntryType.VIDEO, "video/x-ms-wmv",    Compression.NONE),
    ".ts":   (EntryType.VIDEO, "video/mp2t",         Compression.NONE),
    ".m4v":  (EntryType.VIDEO, "video/mp4",          Compression.NONE),
}


# ── 常见文件 magic 码映射 ──────────────────────────────────
FILE_MAGICS = {
    ".mp4":  b"\x00\x00\x00\x00\x66\x74\x79\x70",
    ".mkv":  b"\x1a\x45\xdf\xa3",
    ".avi":  b"\x52\x49\x46\x46",
    ".mov":  b"\x00\x00\x00\x00\x66\x74\x79\x70",
    ".webm": b"\x1a\x45\xdf\xa3",
    ".mp3":  b"\x49\x44\x33",
    ".wav":  b"\x52\x49\x46\x46",
    ".flac": b"\x66\x4c\x61\x43",
    ".ogg":  b"\x4f\x67\x67\x53",
    ".jpg":  b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png":  b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a",
    ".gif":  b"\x47\x49\x46\x38",
    ".bmp":  b"\x42\x4d",
    ".pdf":  b"\x25\x50\x44\x46",
    ".zip":  b"\x50\x4b\x03\x04",
    ".docx": b"\x50\x4b\x03\x04",
    ".xlsx": b"\x50\x4b\x03\x04",
    ".pptx": b"\x50\x4b\x03\x04",
}


# ── 全局标志位 ──────────────────────────────────────────────
FLAG_ENCRYPTED = 0x01
FLAG_SIGNED    = 0x02
