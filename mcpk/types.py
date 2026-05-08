"""MCPK 数据类型定义。"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


def _ms_to_iso(ts_ms: int) -> str:
    """将 Unix 毫秒时间戳转为 ISO 8601 字符串 (本地时区)。"""
    if ts_ms <= 0:
        return ""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.astimezone().isoformat()


@dataclass
class FileHeader:
    """MCPK v2 文件头 (64 字节)。"""
    magic: bytes = b"MCPK"
    version: int = 2
    flags: int = 0
    packed_at: int = 0               # 容器打包时间 (Unix ms)

    # Magic Index 位置
    magic_index_offset: int = 0
    magic_index_size: int = 0

    # 条目和分组计数
    entry_count: int = 0
    group_count: int = 0

    # Group Index 位置
    group_index_offset: int = 0
    group_index_size: int = 0

    # Encryption Params 位置 (0 = 无加密)
    ep_offset: int = 0
    ep_size: int = 0

    # TOC 位置
    toc_offset: int = 0

    @property
    def is_encrypted(self) -> bool:
        return bool(self.flags & 0x01)

    def packed_at_iso(self) -> str:
        return _ms_to_iso(self.packed_at)


@dataclass
class EncryptionParams:
    """加密参数区 (56 字节)。"""
    kdf_type: int = 0x01           # KdfType.SHA256_XOR
    encrypt_mode: int = 0x00       # EncryptionMode
    salt: bytes = b"\x00" * 16     # 128-bit 随机盐
    control_key_hash: bytes = b"\x00" * 32  # SHA-256(control_key)


@dataclass
class TocEntry:
    """TOC 条目（单个文件的索引+元数据）。"""
    entry_type: int = 0x01
    compression: int = 0x00
    crc32: int = 0
    created_at: int = 0            # 源文件创建时间 (Unix ms)
    modified_at: int = 0           # 源文件修改时间 (Unix ms)
    original_size: int = 0
    stored_size: int = 0
    blob_offset: int = 0
    name: str = ""
    mime_type: str = ""
    metadata: Optional[str] = None
    group_id: int = 0xFF           # 所属分组 ID (0xFF=无分组)

    def metadata_dict(self) -> dict:
        if not self.metadata:
            return {}
        import json
        return json.loads(self.metadata)

    @property
    def compression_ratio(self) -> float:
        if self.stored_size == 0:
            return 0.0
        return self.original_size / self.stored_size

    @property
    def is_compressed(self) -> bool:
        return self.compression != 0x00

    def time_info(self) -> dict:
        """返回格式化的时间信息。"""
        return {
            "created": _ms_to_iso(self.created_at),
            "modified": _ms_to_iso(self.modified_at),
        }

    def __repr__(self) -> str:
        from .constants import EntryType, Compression
        try:
            type_name = EntryType(self.entry_type).name
        except ValueError:
            type_name = f"0x{self.entry_type:02x}"
        try:
            comp_name = Compression(self.compression).name
        except ValueError:
            comp_name = f"0x{self.compression:02x}"
        return (
            f"TocEntry({type_name}, name={self.name!r}, "
            f"mime={self.mime_type!r}, "
            f"original={self.original_size}, stored={self.stored_size}, "
            f"comp={comp_name}, crc32=0x{self.crc32:08x}, "
            f"group={self.group_id})"
        )


@dataclass
class MagicEntry:
    """Magic Index 中的单个条目（固定 48 字节）。"""
    entry_id: int = 0
    entry_type: int = 0x01
    group_id: int = 0xFF
    magic_bytes: bytes = b""
    name: str = ""

    def __repr__(self) -> str:
        from .constants import EntryType
        try:
            type_name = EntryType(self.entry_type).name
        except ValueError:
            type_name = f"0x{self.entry_type:02x}"
        magic_hex = self.magic_bytes[:8].hex() if self.magic_bytes else "N/A"
        return (
            f"MagicEntry(id={self.entry_id}, type={type_name}, "
            f"group={self.group_id}, magic={magic_hex}..., "
            f"name={self.name!r})"
        )


@dataclass
class GroupEntry:
    """Group Index 中的分组条目（变长）。"""
    group_id: int = 0
    entry_ids: list[int] = field(default_factory=list)
    group_type: int = 0x00
    name: str = ""
    metadata: Optional[str] = None

    def metadata_dict(self) -> dict:
        if not self.metadata:
            return {}
        import json
        return json.loads(self.metadata)

    def __repr__(self) -> str:
        from .constants import GroupType
        try:
            type_name = GroupType(self.group_type).name
        except ValueError:
            type_name = f"0x{self.group_type:02x}"
        return (
            f"GroupEntry(id={self.group_id}, type={type_name}, "
            f"name={self.name!r}, entries={self.entry_ids})"
        )


@dataclass
class GroupRelation:
    """组间关系（变长）。"""
    source_group: int = 0
    target_group: int = 0
    relation_type: int = 0x00
    description: str = ""

    def __repr__(self) -> str:
        from .constants import RelationType
        try:
            type_name = RelationType(self.relation_type).name
        except ValueError:
            type_name = f"0x{self.relation_type:02x}"
        return (
            f"GroupRelation({self.source_group} -> {self.target_group}, "
            f"type={type_name}, desc={self.description!r})"
        )
