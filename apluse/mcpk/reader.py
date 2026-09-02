"""MCPK v1/v2 文件读取工具。

支持：
- 自动检测 v1/v2 版本
- Magic Index / Group Index 解析（v2）
- VIDEO 条目类型
- 完整时间戳（created_at / modified_at）
- XOR 流解密（v2.1 兼容）
- AES-256-GCM 认证解密（v2.2）
- 分组标签 + 组内关系解析
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
    NO_GROUP, ENCRYPTION_PARAMS_SIZE_LEGACY, ENCRYPTION_PARAMS_SIZE_V2,
    AES_GCM_NONCE_SIZE, AES_GCM_TAG_SIZE, FLAG_ENCRYPTED,
    HEADER_FMT, FOOTER_FMT, TOC_ENTRY_FIXED_FMT, TOC_ENTRY_FIXED_SIZE,
    MAGIC_INDEX_HEADER_FMT, MAGIC_INDEX_HEADER_SIZE,
    MAGIC_ENTRY_FMT, MAGIC_ENTRY_SIZE,
    GROUP_INDEX_HEADER_FMT, GROUP_INDEX_HEADER_SIZE,
    ENCRYPTION_PARAMS_FMT_LEGACY, ENCRYPTION_PARAMS_FMT_V2,
    EntryType, Compression, GroupType, RelationType, IntraRelationType,
    EncryptionMode, KdfType,
)
from .types import (
    FileHeader, TocEntry, MagicEntry, GroupEntry, GroupRelation,
    IntraRelation, EncryptionParams,
)
from .writer import (
    xor_bytes, _derive_key, _derive_control_key, _derive_blob_key,
    _derive_key_pbkdf2, _derive_subkeys_aes, _derive_blob_key_aes,
    aes_gcm_decrypt, HAS_CRYPTO, _get_zstd, _get_lz4,
)


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

        # 加密文件（自动检测 XOR / AES-GCM）
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
        self._group_by_name: dict[str, GroupEntry] = {}
        self._relations: list[GroupRelation] = []
        self._loaded = False
        self._version: int = 1
        self._control_key: Optional[bytes] = None
        self._master_key: Optional[bytes] = None
        self._data_key_base: Optional[bytes] = None  # AES 模式专用
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

    # ── 属性 ──────────────────────────────────────────────

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

    # ── 公开 API ──────────────────────────────────────────

    def list_entries(self, entry_type: Optional[int] = None) -> list[TocEntry]:
        if entry_type is None:
            return self.entries
        return [e for e in self._entries if e.entry_type == entry_type]

    def find(self, name: str, *, group: Optional[Union[str, int]] = None,
             index: int = 0) -> Optional[TocEntry]:
        """按文件名查找条目。

        Args:
            name: 文件名
            group: 分组名或 group_id，区分不同组的同名文件
            index: 同组同名文件的索引（0=第一个，1=第二个，以此类推）

        Returns:
            匹配的 TocEntry，不存在返回 None
        """
        matches = self.find_all(name, group=group)
        if index < len(matches):
            return matches[index]
        return None

    def find_all(self, name: str, *, group: Optional[Union[str, int]] = None) -> list[TocEntry]:
        """返回所有同名条目。可按分组过滤。"""
        gid = None
        if group is not None:
            if isinstance(group, int):
                gid = group
            else:
                g = self.find_group(group)
                if g is None:
                    return []
                gid = g.group_id
        if gid is not None:
            return [e for e in self._entries if e.name == name and e.group_id == gid]
        return [e for e in self._entries if e.name == name]

    def find_group(self, name: str) -> Optional[GroupEntry]:
        return self._group_by_name.get(name)

    def list_group_entries(self, group_name: str) -> list[TocEntry]:
        group = self.find_group(group_name)
        if group is None:
            raise KeyError(f"分组不存在: {group_name}")
        return [self._entries[eid] for eid in group.entry_ids if eid < len(self._entries)]

    def extract(self, name: str, *, group: Optional[Union[str, int]] = None,
                index: int = 0) -> bytes:
        """提取文件内容。

        Args:
            name: 文件名
            group: 分组名或 group_id，区分不同组的同名文件
            index: 同组同名文件的索引（0=第一个）
        """
        entry = self.find(name, group=group, index=index)
        if entry is None:
            hint = ""
            if group is not None:
                hint += f", 分组: {group}"
            if index > 0:
                hint += f", 索引: {index}"
            # 提示有多少同名文件
            all_matches = self.find_all(name)
            if all_matches:
                raise KeyError(f"文件不存在: {name}{hint}（共找到 {len(all_matches)} 个同名条目）")
            raise KeyError(f"文件不存在: {name}")
        return self.extract_entry(entry)

    def extract_entry(self, entry: TocEntry) -> bytes:
        self._file.seek(entry.blob_offset)

        if self._is_encrypted and self._enc_params.encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.DATA_ONLY
        ):
            entry_id = self._entries.index(entry)
            entry_salt = self._file.read(16)

            if self._enc_params.is_aes:
                # AES-GCM: nonce(12) + ciphertext + tag(16)
                encrypted_data = self._file.read(entry.stored_size - 16)
                blob_key = _derive_blob_key_aes(
                    self._data_key_base, entry_id, entry_salt
                )
                try:
                    stored_data = aes_gcm_decrypt(
                        blob_key, encrypted_data, aad=struct.pack("<I", entry_id)
                    )
                except Exception:
                    raise MCPKError(
                        f"数据已损坏: {entry.name}（AES-GCM 认证失败）"
                    )
            else:
                # XOR: encrypted bytes
                encrypted_data = self._file.read(entry.stored_size - 16)
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
                   preserve_structure: bool = True,
                   group: Optional[Union[str, int]] = None,
                   index: int = 0) -> Path:
        data = self.extract(name, group=group, index=index)
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

    def get_metadata(self, name: str, *, group: Optional[Union[str, int]] = None,
                     index: int = 0) -> dict:
        entry = self.find(name, group=group, index=index)
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
                    mi_data = self._decrypt_control(mi_data)
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
            result["kdf_type"] = KdfType(self._enc_params.kdf_type).name
            if self._enc_params.kdf_iterations > 0:
                result["kdf_iterations"] = self._enc_params.kdf_iterations

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
                    "tags": g.tags,
                    "intra_relations": [
                        {
                            "source": ir.source_entry, "target": ir.target_entry,
                            "type": IntraRelationType(ir.relation_type).name
                                if ir.relation_type in IntraRelationType._value2member_map_
                                else f"0x{ir.relation_type:02x}",
                            "description": ir.description,
                        }
                        for ir in g.intra_relations
                    ],
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

    # ── 解密内部方法 ──────────────────────────────────────

    def _decrypt_control(self, data: bytes) -> bytes:
        """解密控制区数据。"""
        if self._enc_params.is_aes:
            try:
                return aes_gcm_decrypt(self._control_key, data, aad=b"mcpk-ctrl")
            except Exception:
                raise MCPKError("数据已损坏或密码错误（AES-GCM 认证失败）")
        else:
            return xor_bytes(data, self._control_key)

    # ── 内部方法 ──────────────────────────────────────────

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
        # 构建快速查找索引
        self._group_by_name = {g.name: g for g in self._groups}
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
         group_index_offset, mi_encrypted_size,
         toc_offset) = struct.unpack(HEADER_FMT, header_data)

        # mi_encrypted_size 是 writer 写入 header 的 MI 在磁盘上的精确大小
        magic_index_offset = HEADER_SIZE + ep_size
        file_size = self.file_path.stat().st_size

        self._is_encrypted = bool(flags & FLAG_ENCRYPTED)

        # ── 加密处理 ──
        if self._is_encrypted:
            if ep_offset == 0:
                raise MCPKError("文件标记为加密但缺少 Encryption Params")
            self._file.seek(ep_offset)

            # 先读取 kdf_type 来判断格式
            ep_header = self._file.read(8)
            kdf_type = ep_header[4]

            self._file.seek(ep_offset)
            if kdf_type == KdfType.PBKDF2_AES:
                ep_data = self._file.read(ENCRYPTION_PARAMS_SIZE_V2)
                if len(ep_data) < ENCRYPTION_PARAMS_SIZE_V2:
                    raise MCPKError("Encryption Params 数据不完整")
                self._enc_params = self._parse_encryption_params_v2(ep_data)
            else:
                ep_data = self._file.read(ENCRYPTION_PARAMS_SIZE_LEGACY)
                if len(ep_data) < ENCRYPTION_PARAMS_SIZE_LEGACY:
                    raise MCPKError("Encryption Params 数据不完整")
                self._enc_params = self._parse_encryption_params_legacy(ep_data)

            if self._password is None:
                raise MCPKError("此文件已加密，请提供密码（password 参数）")

            # 派生密钥并验证
            if self._enc_params.is_aes:
                if not HAS_CRYPTO:
                    raise MCPKError(
                        "此文件使用 AES-256-GCM 加密，请安装 cryptography: "
                        "pip install cryptography"
                    )
                self._master_key = _derive_key_pbkdf2(
                    self._password, self._enc_params.salt,
                    self._enc_params.kdf_iterations,
                )
                self._control_key, self._data_key_base = _derive_subkeys_aes(
                    self._master_key
                )
                computed_verify = hashlib.sha256(
                    self._master_key + b"verify"
                ).digest()
                if computed_verify != self._enc_params.control_key_hash:
                    raise MCPKError("密码错误或文件已损坏")
            else:
                self._master_key = _derive_key(self._password, self._enc_params.salt)
                self._control_key = _derive_control_key(self._master_key)
                computed_hash = hashlib.sha256(self._control_key).digest()
                if computed_hash != self._enc_params.control_key_hash:
                    raise MCPKError("密码错误或文件已损坏")

        # GI 大小通过偏移计算：gi_encrypted_size = toc_offset - gi_offset
        gi_encrypted_size = toc_offset - group_index_offset if toc_offset > group_index_offset else 0

        self._header = FileHeader(
            magic=magic, version=version, flags=flags,
            packed_at=packed_at,
            magic_index_offset=magic_index_offset,
            magic_index_size=mi_encrypted_size,
            entry_count=entry_count, group_count=group_count,
            group_index_offset=group_index_offset,
            group_index_size=gi_encrypted_size,
            ep_offset=ep_offset, ep_size=ep_size,
            toc_offset=toc_offset,
        )

        # ── 读取 Magic Index ──
        if mi_encrypted_size > 0:
            self._file.seek(magic_index_offset)
            mi_data = self._file.read(mi_encrypted_size)
            if self._is_encrypted and self._enc_params.encrypt_mode in (
                EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
            ):
                mi_data = self._decrypt_control(mi_data)
            self._magic_entries = self._parse_magic_index(mi_data)

        # ── 读取 Group Index ──
        if gi_encrypted_size > 0:
            self._file.seek(group_index_offset)
            gi_data = self._file.read(gi_encrypted_size)
            if self._is_encrypted and self._enc_params.encrypt_mode in (
                EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
            ):
                gi_data = self._decrypt_control(gi_data)
            self._groups, self._relations = self._parse_group_index(gi_data)

        # ── 读取 TOC ──
        footer_offset = self.file_path.stat().st_size - FOOTER_SIZE
        toc_size = footer_offset - toc_offset
        self._file.seek(toc_offset)
        toc_data = self._file.read(toc_size)
        if self._is_encrypted and self._enc_params.encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            toc_data = self._decrypt_control(toc_data)
        self._entries = self._parse_toc(toc_data, entry_count, version=2)

    def _parse_encryption_params_legacy(self, data: bytes) -> EncryptionParams:
        """解析旧版 56 字节 Encryption Params (kdf_type=0x01)。"""
        (params_magic, kdf_type, encrypt_mode,
         _reserved, salt, control_key_hash) = struct.unpack_from(
            ENCRYPTION_PARAMS_FMT_LEGACY, data, 0
        )
        if params_magic != ENCRYPTION_PARAMS_MAGIC:
            raise MCPKError(f"Encryption Params magic 不匹配: {params_magic!r}")
        return EncryptionParams(
            kdf_type=kdf_type, encrypt_mode=encrypt_mode,
            salt=salt, control_key_hash=control_key_hash,
            kdf_iterations=0,
        )

    def _parse_encryption_params_v2(self, data: bytes) -> EncryptionParams:
        """解析新版 76 字节 Encryption Params (kdf_type=0x02)。"""
        (params_magic, kdf_type, encrypt_mode,
         _reserved, kdf_iterations, salt, key_verify) = struct.unpack_from(
            ENCRYPTION_PARAMS_FMT_V2, data, 0
        )
        if params_magic != ENCRYPTION_PARAMS_MAGIC:
            raise MCPKError(f"Encryption Params magic 不匹配: {params_magic!r}")
        return EncryptionParams(
            kdf_type=kdf_type, encrypt_mode=encrypt_mode,
            salt=salt, control_key_hash=key_verify,
            kdf_iterations=kdf_iterations,
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

            # 解析 tags (v2.2 新增)
            tags = []
            tag_count = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            for _ in range(tag_count):
                tag_len = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                tag = data[offset:offset + tag_len].decode("utf-8")
                offset += tag_len
                tags.append(tag)

            # 解析 entry_ids
            eid_count = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            entry_ids = []
            for _ in range(eid_count):
                entry_ids.append(struct.unpack_from("<I", data, offset)[0])
                offset += 4

            # 解析 intra_relations (v2.2 新增)
            intra_rels = []
            ir_count = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            for _ in range(ir_count):
                src_eid, tgt_eid, ir_type, ir_dlen = struct.unpack_from(
                    "<II H H", data, offset
                )
                offset += 12
                ir_desc = ""
                if ir_dlen > 0:
                    ir_desc = data[offset:offset + ir_dlen].decode("utf-8")
                    offset += ir_dlen
                intra_rels.append(IntraRelation(
                    source_entry=src_eid, target_entry=tgt_eid,
                    relation_type=ir_type, description=ir_desc,
                ))

            groups.append(GroupEntry(
                group_id=group_id, entry_ids=entry_ids,
                group_type=group_type, name=name, metadata=metadata,
                tags=tags, intra_relations=intra_rels,
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
            m = _get_zstd()
            if m is not None:
                return m.decompress(data)
            raise MCPKError("数据使用 zstd 压缩，请安装 zstd: pip install zstd")
        elif compression == Compression.LZ4:
            m = _get_lz4()
            if m is not None:
                return m.decompress(data)
            raise MCPKError("数据使用 lz4 压缩，请安装 lz4: pip install lz4")
        else:
            raise MCPKError(f"未知压缩算法: {compression}")
