"""MCPK v1/v2 文件读取工具。

支持：
- 自动检测 v1/v2 版本
- Magic Index / Group Index 解析（v2）
- VIDEO 条目类型
- 完整时间戳（created_at / modified_at）
- 可选 XOR 流解密
"""

from __future__ import annotations

import binascii
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Optional, Union

from .constants import (
    MAGIC, VERSION, HEADER_SIZE, FOOTER_SIZE,
    MAGIC_INDEX_MAGIC, GROUP_INDEX_MAGIC, ENCRYPTION_PARAMS_MAGIC,
    NO_GROUP, ENCRYPTION_PARAMS_SIZE, FLAG_ENCRYPTED,
    HEADER_FMT, FOOTER_FMT, TOC_ENTRY_FIXED_FMT, TOC_ENTRY_FIXED_SIZE,
    MAGIC_INDEX_HEADER_FMT, MAGIC_INDEX_HEADER_SIZE,
    MAGIC_ENTRY_FMT, MAGIC_ENTRY_SIZE,
    GROUP_INDEX_HEADER_FMT, GROUP_INDEX_HEADER_SIZE,
    ENCRYPTION_PARAMS_FMT,
    EntryType, Compression, GroupType, RelationType,
    EncryptionMode, KdfType,
)
from .types import (
    FileHeader, TocEntry, MagicEntry, GroupEntry, GroupRelation, EncryptionParams,
)
from .writer import xor_bytes, _derive_key, _derive_control_key, _derive_blob_key


class MCPKError(Exception):
    pass


class MCPKReader:
    """
    MCPK v1/v2 文件读取器。

    用法:
        # 不加密文件
        with MCPKReader("archive.mcpk") as r:
            for entry in r.entries:
                print(entry.name, entry.modified_at)
            data = r.extract("report.pdf")

        # 加密文件
        with MCPKReader("secret.mcpk", password="mypass") as r:
            data = r.extract("private.md")
    """

    def __init__(self, file_path: Union[str, Path], *, password: Optional[str] = None):
        self.file_path = Path(file_path)
        self._file = None
        self._password = password
        self._header: Optional[FileHeader] = None
        self._enc_params: Optional[EncryptionParams] = None
        self._entries: list[TocEntry] = []
        self._magic_entries: list[MagicEntry] = []
        self._groups: list[GroupEntry] = []
        self._relations: list[GroupRelation] = []
        self._loaded = False
        self._version: int = 1
        self._control_key: Optional[bytes] = None
        self._master_key: Optional[bytes] = None
        self._is_encrypted: bool = False

    def __enter__(self):
        self._file = open(self.file_path, "rb")
        try:
            self._load()
        except Exception:
            self._file.close()
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self._file.close()

    @property
    def version(self) -> int:
        self._ensure_loaded()
        return self._version

    @property
    def header(self) -> FileHeader:
        self._ensure_loaded()
        return self._header

    @property
    def is_encrypted(self) -> bool:
        self._ensure_loaded()
        return self._is_encrypted

    @property
    def encryption_params(self) -> Optional[EncryptionParams]:
        self._ensure_loaded()
        return self._enc_params

    @property
    def entries(self) -> list[TocEntry]:
        self._ensure_loaded()
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def magic_entries(self) -> list[MagicEntry]:
        self._ensure_loaded()
        return list(self._magic_entries)

    @property
    def groups(self) -> list[GroupEntry]:
        self._ensure_loaded()
        return list(self._groups)

    @property
    def relations(self) -> list[GroupRelation]:
        self._ensure_loaded()
        return list(self._relations)

    def list_entries(self, entry_type: Optional[int] = None) -> list[TocEntry]:
        if entry_type is None:
            return self.entries
        return [e for e in self._entries if e.entry_type == entry_type]

    def find(self, name: str) -> Optional[TocEntry]:
        for entry in self._entries:
            if entry.name == name:
                return entry
        return None

    def find_group(self, name: str) -> Optional[GroupEntry]:
        for group in self._groups:
            if group.name == name:
                return group
        return None

    def list_group_entries(self, group_name: str) -> list[TocEntry]:
        group = self.find_group(group_name)
        if group is None:
            raise KeyError(f"分组不存在: {group_name}")
        return [self._entries[eid] for eid in group.entry_ids if eid < len(self._entries)]

    def extract(self, name: str) -> bytes:
        entry = self.find(name)
        if entry is None:
            raise KeyError(f"文件不存在: {name}")
        return self.extract_entry(entry)

    def extract_entry(self, entry: TocEntry) -> bytes:
        self._file.seek(entry.blob_offset)

        if self._is_encrypted and self._enc_params.encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.DATA_ONLY
        ):
            entry_salt = self._file.read(16)
            encrypted_data = self._file.read(entry.stored_size - 16)
            entry_id = self._entries.index(entry)
            blob_key = _derive_blob_key(self._master_key, entry_id, entry_salt)
            stored_data = xor_bytes(encrypted_data, blob_key)
        else:
            stored_data = self._file.read(entry.stored_size)

        original_data = self._decompress(stored_data, entry.compression)

        if len(original_data) != entry.original_size:
            raise MCPKError(
                f"数据大小不匹配: {entry.name} "
                f"(期望 {entry.original_size}, 实际 {len(original_data)})"
            )

        crc32_val = binascii.crc32(original_data) & 0xFFFFFFFF
        if crc32_val != entry.crc32:
            raise MCPKError(
                f"CRC32 校验失败: {entry.name} "
                f"(期望 0x{entry.crc32:08x}, 实际 0x{crc32_val:08x})"
            )
        return original_data

    def extract_to(self, name: str, output_dir: Union[str, Path], *,
                   preserve_structure: bool = True) -> Path:
        data = self.extract(name)
        output_dir = Path(output_dir)
        out_path = output_dir / name if preserve_structure else output_dir / Path(name).name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path

    def extract_all(self, output_dir: Union[str, Path], *,
                    preserve_structure: bool = True) -> list[Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return [
            self.extract_to(e.name, output_dir, preserve_structure=preserve_structure)
            for e in self._entries
        ]

    def extract_group(self, group_name: str, output_dir: Union[str, Path], *,
                      preserve_structure: bool = True) -> list[Path]:
        entries = self.list_group_entries(group_name)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return [
            self.extract_to(e.name, output_dir, preserve_structure=preserve_structure)
            for e in entries
        ]

    def get_metadata(self, name: str) -> dict:
        entry = self.find(name)
        if entry is None:
            raise KeyError(f"文件不存在: {name}")
        return entry.metadata_dict()

    def verify(self) -> list[str]:
        errors = []
        if self._header.magic != MAGIC:
            errors.append(f"Header magic 不匹配: {self._header.magic!r}")
        if self._header.version > VERSION:
            errors.append(f"版本过高: {self._header.version} (当前工具支持 {VERSION})")

        try:
            self._file.seek(-FOOTER_SIZE, 2)
            footer_data = self._file.read(FOOTER_SIZE)
            footer_magic, footer_toc_offset, footer_crc = struct.unpack(FOOTER_FMT, footer_data)
            if footer_magic != MAGIC:
                errors.append(f"Footer magic 不匹配: {footer_magic!r}")
            computed_crc = binascii.crc32(footer_data[:12]) & 0xFFFFFFFF
            if computed_crc != footer_crc:
                errors.append(f"Footer CRC 不匹配")
        except Exception as e:
            errors.append(f"Footer 读取失败: {e}")

        if self._version >= 2 and self._header.magic_index_size > 0:
            try:
                self._file.seek(self._header.magic_index_offset)
                mi_data = self._file.read(self._header.magic_index_size)
                if self._is_encrypted and self._enc_params.encrypt_mode in (
                    EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
                ):
                    mi_data = xor_bytes(mi_data, self._control_key)
                if mi_data[:4] != MAGIC_INDEX_MAGIC:
                    errors.append("Magic Index magic 不匹配")
            except Exception as e:
                errors.append(f"Magic Index 读取失败: {e}")

        for i, entry in enumerate(self._entries):
            try:
                self.extract_entry(entry)
            except MCPKError as e:
                errors.append(f"条目 [{i}] {entry.name}: {e}")
        return errors

    def inspect(self) -> dict:
        h = self._header
        entries_info = []
        total_original = 0
        total_stored = 0
        for e in self._entries:
            total_original += e.original_size
            total_stored += e.stored_size
            entries_info.append({
                "name": e.name,
                "type": EntryType(e.entry_type).name if e.entry_type in EntryType._value2member_map_ else f"0x{e.entry_type:02x}",
                "mime": e.mime_type,
                "compression": Compression(e.compression).name if e.compression in Compression._value2member_map_ else f"0x{e.compression:02x}",
                "original_size": e.original_size,
                "stored_size": e.stored_size,
                "ratio": f"{e.compression_ratio:.2f}x" if e.stored_size > 0 else "N/A",
                "crc32": f"0x{e.crc32:08x}",
                "group_id": e.group_id,
                "created_at": e.created_at,
                "modified_at": e.modified_at,
                "created_iso": e.time_info()["created"],
                "modified_iso": e.time_info()["modified"],
                "metadata": e.metadata_dict(),
            })

        result = {
            "file": str(self.file_path),
            "file_size": self.file_path.stat().st_size,
            "version": h.version,
            "flags": h.flags,
            "encrypted": self._is_encrypted,
            "packed_at": h.packed_at,
            "packed_at_iso": h.packed_at_iso(),
            "entry_count": h.entry_count,
            "toc_offset": h.toc_offset,
            "total_original_size": total_original,
            "total_stored_size": total_stored,
            "overall_ratio": f"{total_original / total_stored:.2f}x" if total_stored > 0 else "N/A",
            "entries": entries_info,
        }

        if self._is_encrypted and self._enc_params:
            result["encrypt_mode"] = EncryptionMode(self._enc_params.encrypt_mode).name

        if self._version >= 2:
            result["magic_index_offset"] = h.magic_index_offset
            result["magic_index_size"] = h.magic_index_size
            result["group_count"] = h.group_count
            result["group_index_offset"] = h.group_index_offset
            result["group_index_size"] = h.group_index_size
            result["groups"] = [
                {
                    "group_id": g.group_id, "name": g.name,
                    "type": GroupType(g.group_type).name if g.group_type in GroupType._value2member_map_ else f"0x{g.group_type:02x}",
                    "entry_count": len(g.entry_ids), "entry_ids": g.entry_ids,
                    "metadata": g.metadata_dict(),
                }
                for g in self._groups
            ]
            result["relations"] = [
                {
                    "source": r.source_group, "target": r.target_group,
                    "type": RelationType(r.relation_type).name if r.relation_type in RelationType._value2member_map_ else f"0x{r.relation_type:02x}",
                    "description": r.description,
                }
                for r in self._relations
            ]
        return result

    def _ensure_loaded(self):
        if not self._loaded:
            raise MCPKError("文件未打开，请使用 with 语句")

    def _load(self):
        file_size = self.file_path.stat().st_size
        if file_size < HEADER_SIZE + FOOTER_SIZE:
            raise MCPKError("文件太小，不是有效的 MCPK 文件")

        self._file.seek(0)
        header_data = self._file.read(HEADER_SIZE)
        if header_data[:4] != MAGIC:
            raise MCPKError(f"不是有效的 MCPK 文件 (magic: {header_data[:4]!r})")

        version = struct.unpack_from("<H", header_data, 4)[0]
        self._version = version

        if version == 1:
            self._load_v1(header_data)
        elif version == 2:
            self._load_v2(header_data)
        else:
            raise MCPKError(f"不支持的版本 {version}")
        self._loaded = True

    def _load_v1(self, header_data: bytes):
        v1_fmt = "<4sHH Q Q Q I I 24s"
        (magic, version, flags, created_at,
         toc_offset, toc_size, entry_count,
         data_section_size, _reserved) = struct.unpack(v1_fmt, header_data)

        self._header = FileHeader(
            magic=magic, version=version, flags=flags,
            packed_at=created_at,
            magic_index_offset=0, magic_index_size=0,
            entry_count=entry_count, group_count=0,
            group_index_offset=0, group_index_size=0,
            ep_offset=0, toc_offset=toc_offset,
        )
        self._file.seek(toc_offset)
        toc_data = self._file.read(toc_size)
        self._entries = self._parse_toc(toc_data, entry_count, version=1)

    def _load_v2(self, header_data: bytes):
        (magic, version, flags, packed_at,
         ep_offset, ep_size,
         entry_count, group_count,
         group_index_offset, group_index_size,
         toc_offset) = struct.unpack(HEADER_FMT, header_data)

        magic_index_offset = HEADER_SIZE + ep_size
        magic_index_size = group_index_offset - magic_index_offset if group_index_offset > magic_index_offset else 0

        self._header = FileHeader(
            magic=magic, version=version, flags=flags,
            packed_at=packed_at,
            magic_index_offset=magic_index_offset,
            magic_index_size=magic_index_size,
            entry_count=entry_count, group_count=group_count,
            group_index_offset=group_index_offset,
            group_index_size=group_index_size,
            ep_offset=ep_offset, ep_size=ep_size,
            toc_offset=toc_offset,
        )
        self._is_encrypted = bool(flags & FLAG_ENCRYPTED)

        if self._is_encrypted:
            if ep_offset == 0:
                raise MCPKError("文件标记为加密但缺少 Encryption Params")
            self._file.seek(ep_offset)
            ep_data = self._file.read(ENCRYPTION_PARAMS_SIZE)
            if len(ep_data) < ENCRYPTION_PARAMS_SIZE:
                raise MCPKError("Encryption Params 数据不完整")
            self._enc_params = self._parse_encryption_params(ep_data)

            if self._password is None:
                raise MCPKError("此文件已加密，请提供密码（password 参数）")

            self._master_key = _derive_key(self._password, self._enc_params.salt)
            self._control_key = _derive_control_key(self._master_key)
            computed_hash = hashlib.sha256(self._control_key).digest()
            if computed_hash != self._enc_params.control_key_hash:
                raise MCPKError("密码错误或文件已损坏")

        if magic_index_size > 0:
            self._file.seek(magic_index_offset)
            mi_data = self._file.read(magic_index_size)
            if self._is_encrypted and self._enc_params.encrypt_mode in (
                EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
            ):
                mi_data = xor_bytes(mi_data, self._control_key)
            self._magic_entries = self._parse_magic_index(mi_data)

        if group_index_size > 0:
            self._file.seek(group_index_offset)
            gi_data = self._file.read(group_index_size)
            if self._is_encrypted and self._enc_params.encrypt_mode in (
                EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
            ):
                gi_data = xor_bytes(gi_data, self._control_key)
            self._groups, self._relations = self._parse_group_index(gi_data)

        footer_offset = self.file_path.stat().st_size - FOOTER_SIZE
        toc_size = footer_offset - toc_offset
        self._file.seek(toc_offset)
        toc_data = self._file.read(toc_size)
        if self._is_encrypted and self._enc_params.encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            toc_data = xor_bytes(toc_data, self._control_key)
        self._entries = self._parse_toc(toc_data, entry_count, version=2)

    def _parse_encryption_params(self, data: bytes) -> EncryptionParams:
        (params_magic, kdf_type, encrypt_mode,
         _reserved, salt, control_key_hash) = struct.unpack_from(
            ENCRYPTION_PARAMS_FMT, data, 0
        )
        if params_magic != ENCRYPTION_PARAMS_MAGIC:
            raise MCPKError(f"Encryption Params magic 不匹配: {params_magic!r}")
        return EncryptionParams(
            kdf_type=kdf_type, encrypt_mode=encrypt_mode,
            salt=salt, control_key_hash=control_key_hash,
        )

    def _parse_magic_index(self, data: bytes) -> list[MagicEntry]:
        entries = []
        if len(data) < MAGIC_INDEX_HEADER_SIZE:
            raise MCPKError("Magic Index 数据不完整")
        mi_magic, entry_count, index_size = struct.unpack_from(
            MAGIC_INDEX_HEADER_FMT, data, 0
        )
        if mi_magic != MAGIC_INDEX_MAGIC:
            raise MCPKError(f"Magic Index magic 不匹配: {mi_magic!r}")
        offset = MAGIC_INDEX_HEADER_SIZE
        for i in range(entry_count):
            if offset + MAGIC_ENTRY_SIZE > len(data):
                raise MCPKError(f"Magic Entry 数据越界 (条目 {i})")
            (entry_id, entry_type, group_id, magic_len,
             magic_bytes, name_len, _reserved) = struct.unpack_from(
                MAGIC_ENTRY_FMT, data, offset
            )
            offset += MAGIC_ENTRY_SIZE
            entries.append(MagicEntry(
                entry_id=entry_id, entry_type=entry_type,
                group_id=group_id, magic_bytes=magic_bytes[:magic_len] if magic_len > 0 else b"",
            ))
        return entries

    def _parse_group_index(self, data: bytes) -> tuple[list[GroupEntry], list[GroupRelation]]:
        groups, relations = [], []
        if len(data) < GROUP_INDEX_HEADER_SIZE:
            raise MCPKError("Group Index 数据不完整")
        gi_magic, group_count, relation_count, index_size = struct.unpack_from(
            GROUP_INDEX_HEADER_FMT, data, 0
        )
        if gi_magic != GROUP_INDEX_MAGIC:
            raise MCPKError(f"Group Index magic 不匹配: {gi_magic!r}")
        offset = GROUP_INDEX_HEADER_SIZE
        for i in range(group_count):
            if offset + 6 > len(data):
                raise MCPKError(f"Group Entry 数据越界 (分组 {i})")
            group_id, entry_count, group_type, name_len = struct.unpack_from(
                "<BBH H", data, offset
            )
            offset += 6
            name = data[offset:offset + name_len].decode("utf-8")
            offset += name_len
            meta_len = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            metadata = None
            if meta_len > 0:
                metadata = data[offset:offset + meta_len].decode("utf-8")
                offset += meta_len
            eid_count = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            entry_ids = []
            for _ in range(eid_count):
                entry_ids.append(struct.unpack_from("<I", data, offset)[0])
                offset += 4
            groups.append(GroupEntry(
                group_id=group_id, entry_ids=entry_ids,
                group_type=group_type, name=name, metadata=metadata,
            ))
        for i in range(relation_count):
            if offset + 6 > len(data):
                raise MCPKError(f"Relation 数据越界 (关系 {i})")
            src, tgt, rtype, dlen = struct.unpack_from("<BBH H", data, offset)
            offset += 6
            desc = ""
            if dlen > 0:
                desc = data[offset:offset + dlen].decode("utf-8")
                offset += dlen
            relations.append(GroupRelation(
                source_group=src, target_group=tgt,
                relation_type=rtype, description=desc,
            ))
        return groups, relations

    def _parse_toc(self, toc_data: bytes, expected_count: int, version: int = 2) -> list[TocEntry]:
        entries = []
        offset = 0
        fixed_size = TOC_ENTRY_FIXED_SIZE if version >= 2 else 42

        for i in range(expected_count):
            if offset + fixed_size > len(toc_data):
                raise MCPKError(f"TOC 数据不完整 (条目 {i}/{expected_count})")

            if version >= 2:
                (entry_type, compression, reserved, crc32,
                 created_at, modified_at,
                 original_size, stored_size,
                 blob_offset, name_len) = struct.unpack_from(
                    TOC_ENTRY_FIXED_FMT, toc_data, offset
                )
            else:
                (entry_type, compression, reserved, crc32,
                 created_at, original_size, stored_size,
                 blob_offset, name_len) = struct.unpack_from(
                    "<BB2sI Q Q Q Q H", toc_data, offset
                )
                modified_at = 0

            offset += fixed_size
            group_id = reserved[0] if (version >= 2 and len(reserved) >= 1) else NO_GROUP

            name = toc_data[offset:offset + name_len].decode("utf-8")
            offset += name_len

            mime_len = struct.unpack_from("<H", toc_data, offset)[0]
            offset += 2
            mime_type = toc_data[offset:offset + mime_len].decode("utf-8")
            offset += mime_len

            meta_len = struct.unpack_from("<H", toc_data, offset)[0]
            offset += 2
            metadata = None
            if meta_len > 0:
                metadata = toc_data[offset:offset + meta_len].decode("utf-8")
                offset += meta_len

            entries.append(TocEntry(
                entry_type=entry_type, compression=compression,
                crc32=crc32, created_at=created_at, modified_at=modified_at,
                original_size=original_size, stored_size=stored_size,
                blob_offset=blob_offset, name=name, mime_type=mime_type,
                metadata=metadata, group_id=group_id,
            ))
        return entries

    def _decompress(self, data: bytes, compression: int) -> bytes:
        if compression == Compression.NONE:
            return data
        elif compression == Compression.ZLIB:
            return zlib.decompress(data)
        elif compression == Compression.ZSTD:
            try:
                import zstd
                return zstd.decompress(data)
            except ImportError:
                raise MCPKError("数据使用 zstd 压缩，请安装 zstd: pip install zstd")
        elif compression == Compression.LZ4:
            try:
                import lz4.frame
                return lz4.frame.decompress(data)
            except ImportError:
                raise MCPKError("数据使用 lz4 压缩，请安装 lz4: pip install lz4")
        else:
            raise MCPKError(f"未知压缩算法: {compression}")
