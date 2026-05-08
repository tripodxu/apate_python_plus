"""
MCPK - MeCapsule Package v2
自定义二进制容器格式，用于个人知识管理。

v2 特性：
- Magic Index Table（文件签名聚合索引）
- 分组存储（相关文件物理相邻）
- Group Index（分组元数据 + 组间关系）
- VIDEO 条目类型
- 完整时间戳（created_at / modified_at / packed_at）
- 可选 XOR 流加密（密码派生密钥）
"""

from .constants import (
    MAGIC, VERSION,
    EntryType, Compression, GroupType, RelationType,
    EncryptionMode, KdfType,
    NO_GROUP, FLAG_ENCRYPTED,
)
from .types import (
    TocEntry, FileHeader, MagicEntry, GroupEntry, GroupRelation, EncryptionParams,
)
from .writer import MCPKWriter, xor_bytes
from .reader import MCPKReader, MCPKError

__version__ = "2.0.0"
__all__ = [
    "MAGIC", "VERSION",
    "EntryType", "Compression", "GroupType", "RelationType",
    "EncryptionMode", "KdfType", "NO_GROUP", "FLAG_ENCRYPTED",
    "TocEntry", "FileHeader", "MagicEntry", "GroupEntry", "GroupRelation",
    "EncryptionParams",
    "MCPKWriter", "MCPKReader", "MCPKError", "xor_bytes",
]
