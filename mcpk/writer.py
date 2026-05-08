"""MCPK v2 文件写入工具。

支持：
- Magic Index Table（文件签名聚合）
- 分组存储（相关文件物理相邻）
- Group Index（分组元数据 + 组间关系）
- VIDEO 条目类型
- 完整时间戳（created_at / modified_at / packed_at）
- 可选 XOR 流加密（密码派生密钥，与 1apluse 加密体系一致）
"""

from __future__ import annotations

import binascii
import hashlib
import json
import os
import struct
import time
import zlib
from pathlib import Path
from typing import Optional, Union

from .constants import (
    MAGIC, VERSION, HEADER_SIZE, FOOTER_SIZE, MAGIC_ENTRY_SIZE,
    MAGIC_INDEX_MAGIC, GROUP_INDEX_MAGIC, ENCRYPTION_PARAMS_MAGIC,
    NO_GROUP, ENCRYPTION_PARAMS_SIZE,
    HEADER_FMT, FOOTER_FMT, TOC_ENTRY_FIXED_FMT,
    MAGIC_INDEX_HEADER_FMT, MAGIC_INDEX_HEADER_SIZE,
    MAGIC_ENTRY_FMT, GROUP_INDEX_HEADER_FMT, GROUP_INDEX_HEADER_SIZE,
    ENCRYPTION_PARAMS_FMT,
    EntryType, Compression, GroupType, RelationType,
    EncryptionMode, KdfType, FLAG_ENCRYPTED,
    EXTENSION_MAP, FILE_MAGICS,
)
from .types import FileHeader, TocEntry, MagicEntry, GroupEntry, GroupRelation, EncryptionParams


# ── 加密工具函数 ────────────────────────────────────────────

def xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR 流加密/解密（与 1apluse xor_bytes 一致）。"""
    if not key:
        return data
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def _derive_key(password: str, salt: bytes) -> bytes:
    """从密码 + salt 派生 32 字节主密钥。"""
    pwd_bytes = password.encode("utf-8")
    seed = bytes(
        pwd_bytes[i % len(pwd_bytes)] ^ salt[i % len(salt)]
        for i in range(32)
    )
    return hashlib.sha256(seed + salt).digest()


def _derive_control_key(master_key: bytes) -> bytes:
    """派生控制区加密密钥。"""
    return hashlib.sha256(master_key + b"ctrl").digest()


def _derive_blob_key(master_key: bytes, entry_id: int, entry_salt: bytes) -> bytes:
    """派生单条目 blob 加密密钥。"""
    id_bytes = struct.pack("<I", entry_id)
    return hashlib.sha256(master_key + id_bytes + entry_salt).digest()


# ── Writer ──────────────────────────────────────────────────

class MCPKWriter:
    """
    MCPK v2 文件写入器。

    用法:
        # 不加密（默认）
        with MCPKWriter("output.mcpk") as writer:
            writer.add_file("report.pdf")

        # 加密（全量）
        with MCPKWriter("secret.mcpk", password="mypass") as writer:
            writer.add_file("private.md")

        # 加密（仅元数据）
        with MCPKWriter("obscured.mcpk", password="mypass",
                        encrypt_mode="metadata_only") as writer:
            writer.add_file("video.mp4")
    """

    def __init__(
        self,
        output_path: Union[str, Path],
        *,
        password: Optional[str] = None,
        encrypt_mode: Union[str, int] = EncryptionMode.FULL,
    ):
        self.output_path = Path(output_path)
        self._file = None
        self._closed = False

        # 条目和 blob 缓存
        self._entries: list[TocEntry] = []
        self._blobs: list[bytes] = []

        # 分组管理
        self._groups: dict[str, GroupEntry] = {}
        self._group_id_counter: int = 0
        self._relations: list[GroupRelation] = []

        # 加密状态
        self._password = password
        self._encrypted = password is not None
        self._master_key: Optional[bytes] = None
        self._control_key: Optional[bytes] = None
        self._salt: bytes = b""
        self._encrypt_mode = EncryptionMode.NONE

        if self._encrypted:
            if isinstance(encrypt_mode, str):
                mode_map = {
                    "full": EncryptionMode.FULL,
                    "metadata_only": EncryptionMode.METADATA_ONLY,
                    "data_only": EncryptionMode.DATA_ONLY,
                    "none": EncryptionMode.NONE,
                }
                self._encrypt_mode = mode_map.get(encrypt_mode.lower(), EncryptionMode.FULL)
            else:
                self._encrypt_mode = EncryptionMode(encrypt_mode)

            if self._encrypt_mode == EncryptionMode.NONE:
                self._encrypted = False
                self._password = None
            else:
                self._salt = os.urandom(16)
                self._master_key = _derive_key(password, self._salt)
                self._control_key = _derive_control_key(self._master_key)

    def __enter__(self):
        self._file = open(self.output_path, "wb")
        self._file.write(b"\x00" * HEADER_SIZE)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._closed:
            self.finalize()

    # ── 分组 API ────────────────────────────────────────────

    def create_group(
        self, name: str, group_type: int = GroupType.GENERIC,
        *, metadata: Optional[dict] = None,
    ) -> GroupEntry:
        if name in self._groups:
            raise ValueError(f"分组已存在: {name}")
        group_id = self._group_id_counter
        self._group_id_counter += 1
        meta_json = None
        if metadata:
            meta_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        group = GroupEntry(
            group_id=group_id, group_type=group_type,
            name=name, metadata=meta_json,
        )
        self._groups[name] = group
        return group

    def add_relation(
        self, source_group: str, target_group: str,
        relation_type: int = RelationType.RELATED, *, description: str = "",
    ) -> GroupRelation:
        if source_group not in self._groups:
            raise ValueError(f"源分组不存在: {source_group}")
        if target_group not in self._groups:
            raise ValueError(f"目标分组不存在: {target_group}")
        relation = GroupRelation(
            source_group=self._groups[source_group].group_id,
            target_group=self._groups[target_group].group_id,
            relation_type=relation_type, description=description,
        )
        self._relations.append(relation)
        return relation

    # ── 文件添加 API ────────────────────────────────────────

    def add_file(
        self, file_path: Union[str, Path], *,
        arcname: Optional[str] = None, entry_type: Optional[int] = None,
        mime_type: Optional[str] = None, compression: Optional[int] = None,
        metadata: Optional[dict] = None, created_at: Optional[int] = None,
        modified_at: Optional[int] = None,
        group: Optional[Union[GroupEntry, str]] = None,
        group_name: Optional[str] = None,
    ) -> TocEntry:
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = file_path.suffix.lower()
        inferred = EXTENSION_MAP.get(ext)
        if entry_type is None:
            entry_type = inferred[0] if inferred else EntryType.DOCUMENT
        if mime_type is None:
            mime_type = inferred[1] if inferred else "application/octet-stream"
        if compression is None:
            compression = inferred[2] if inferred else Compression.ZLIB

        name = arcname or file_path.name
        if ".." in name or name.startswith("/") or name.startswith("\\"):
            raise ValueError(f"不安全的文件名: {name}")

        # 读取源文件时间戳
        stat = file_path.stat()
        if created_at is None:
            ct = stat.st_ctime
            created_at = int(ct * 1000)
        if modified_at is None:
            mt = stat.st_mtime
            modified_at = int(mt * 1000)

        original_data = file_path.read_bytes()
        return self._add_entry(
            original_data, name, entry_type, mime_type, compression,
            metadata=metadata, created_at=created_at, modified_at=modified_at,
            group=group, group_name=group_name,
        )

    def add_data(
        self, data: bytes, name: str, *,
        entry_type: int = EntryType.DOCUMENT,
        mime_type: str = "application/octet-stream",
        compression: int = Compression.ZLIB,
        metadata: Optional[dict] = None,
        created_at: Optional[int] = None, modified_at: Optional[int] = None,
        group: Optional[Union[GroupEntry, str]] = None,
        group_name: Optional[str] = None,
    ) -> TocEntry:
        if ".." in name or name.startswith("/") or name.startswith("\\"):
            raise ValueError(f"不安全的文件名: {name}")
        return self._add_entry(
            data, name, entry_type, mime_type, compression,
            metadata=metadata, created_at=created_at, modified_at=modified_at,
            group=group, group_name=group_name,
        )

    def add_directory(
        self, dir_path: Union[str, Path], *,
        recursive: bool = True, prefix: str = "",
        metadata_fn=None, group_name: Optional[str] = None,
    ) -> list[TocEntry]:
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"不是目录: {dir_path}")
        group = None
        if group_name:
            if group_name not in self._groups:
                group = self.create_group(group_name)
            else:
                group = self._groups[group_name]
        entries = []
        pattern = "**/*" if recursive else "*"
        for f in sorted(dir_path.glob(pattern)):
            if not f.is_file():
                continue
            relative = f.relative_to(dir_path)
            arcname = f"{prefix}{relative}" if prefix else str(relative)
            arcname = arcname.replace("\\", "/")
            meta = metadata_fn(f) if metadata_fn else None
            entry = self.add_file(f, arcname=arcname, metadata=meta, group=group)
            entries.append(entry)
        return entries

    # ── 完成写入 ────────────────────────────────────────────

    def finalize(self):
        if self._closed:
            return
        self._closed = True

        if not self._entries:
            self._write_empty_file()
            return

        packed_at = int(time.time() * 1000)
        cursor = HEADER_SIZE

        # ── Step 0: 写入 Encryption Params (如果加密) ──
        ep_offset = 0
        ep_size = 0
        if self._encrypted:
            ep_offset = cursor
            ep_size = ENCRYPTION_PARAMS_SIZE
            ep_bytes = self._build_encryption_params()
            self._file.write(ep_bytes)
            cursor += ep_size

        # ── Step 1: 写入 Magic Index ──
        magic_index_offset = cursor
        mi_bytes = self._build_magic_index()
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            mi_bytes = xor_bytes(mi_bytes, self._control_key)
        self._file.write(mi_bytes)
        cursor += len(mi_bytes)

        # ── Step 2: 按分组顺序写入 Blob ──
        indexed = list(enumerate(self._entries))
        def sort_key(item):
            idx, e = item
            return (0 if e.group_id != NO_GROUP else 1, e.group_id, idx)
        sorted_entries = sorted(indexed, key=sort_key)

        encrypt_blobs = self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.DATA_ONLY
        )
        for original_idx, entry in sorted_entries:
            entry.blob_offset = cursor
            blob = self._blobs[original_idx]
            if encrypt_blobs:
                entry_salt = os.urandom(16)
                blob_key = _derive_blob_key(self._master_key, original_idx, entry_salt)
                blob = entry_salt + xor_bytes(blob, blob_key)
                entry.stored_size = len(blob)
            self._file.write(blob)
            cursor += len(blob)

        # ── Step 3: 写入 Group Index ──
        group_index_offset = cursor
        gi_bytes = self._build_group_index()
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            gi_bytes = xor_bytes(gi_bytes, self._control_key)
        self._file.write(gi_bytes)
        cursor += len(gi_bytes)

        # ── Step 4: 写入 TOC ──
        toc_offset = cursor
        toc_bytes = self._build_toc()
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            toc_bytes = xor_bytes(toc_bytes, self._control_key)
        self._file.write(toc_bytes)
        cursor += len(toc_bytes)

        # ── Step 5: 写入 Footer ──
        footer_raw = struct.pack(FOOTER_FMT, MAGIC, toc_offset, 0)
        footer_crc = binascii.crc32(footer_raw[:12]) & 0xFFFFFFFF
        self._file.write(struct.pack(FOOTER_FMT, MAGIC, toc_offset, footer_crc))

        # ── Step 6: 回写 Header ──
        flags = FLAG_ENCRYPTED if self._encrypted else 0
        header = struct.pack(
            HEADER_FMT,
            MAGIC, VERSION, flags, packed_at,
            ep_offset, ep_size,
            len(self._entries), len(self._groups),
            group_index_offset, len(gi_bytes),
            toc_offset,
        )
        self._file.seek(0)
        self._file.write(header)
        self._file.close()

    # ── 内部方法 ────────────────────────────────────────────

    def _add_entry(
        self, original_data: bytes, name: str,
        entry_type: int, mime_type: str, compression: int, *,
        metadata: Optional[dict] = None,
        created_at: Optional[int] = None, modified_at: Optional[int] = None,
        group: Optional[Union[GroupEntry, str]] = None,
        group_name: Optional[str] = None,
    ) -> TocEntry:
        stored_data = self._compress(original_data, compression)
        original_size = len(original_data)
        stored_size = len(stored_data)
        crc32_val = binascii.crc32(original_data) & 0xFFFFFFFF
        now_ms = int(time.time() * 1000)
        ts_created = created_at if created_at is not None else now_ms
        ts_modified = modified_at if modified_at is not None else now_ms

        gid = NO_GROUP
        if group is not None:
            if isinstance(group, GroupEntry):
                gid = group.group_id
            elif isinstance(group, str):
                if group in self._groups:
                    gid = self._groups[group].group_id
                else:
                    gid = self.create_group(group).group_id
        elif group_name is not None:
            if group_name in self._groups:
                gid = self._groups[group_name].group_id
            else:
                gid = self.create_group(group_name).group_id

        if gid != NO_GROUP:
            for g in self._groups.values():
                if g.group_id == gid:
                    g.entry_ids.append(len(self._entries))
                    break

        meta_json = None
        if metadata:
            if "title" not in metadata:
                metadata["title"] = Path(name).stem
            meta_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))

        entry = TocEntry(
            entry_type=entry_type, compression=compression,
            crc32=crc32_val, created_at=ts_created, modified_at=ts_modified,
            original_size=original_size, stored_size=stored_size,
            blob_offset=0, name=name, mime_type=mime_type,
            metadata=meta_json, group_id=gid,
        )
        self._entries.append(entry)
        self._blobs.append(stored_data)
        return entry

    def _compress(self, data: bytes, compression: int) -> bytes:
        if compression == Compression.NONE:
            return data
        elif compression == Compression.ZLIB:
            return zlib.compress(data, level=6)
        elif compression == Compression.ZSTD:
            try:
                import zstd
                return zstd.compress(data, 3)
            except ImportError:
                return zlib.compress(data, level=6)
        elif compression == Compression.LZ4:
            try:
                import lz4.frame
                return lz4.frame.compress(data)
            except ImportError:
                return zlib.compress(data, level=6)
        else:
            raise ValueError(f"未知压缩算法: {compression}")

    def _build_encryption_params(self) -> bytes:
        key_hash = hashlib.sha256(self._control_key).digest()
        return struct.pack(
            ENCRYPTION_PARAMS_FMT,
            ENCRYPTION_PARAMS_MAGIC,
            KdfType.SHA256_XOR,
            self._encrypt_mode,
            b"\x00" * 2,
            self._salt,
            key_hash,
        )

    def _build_magic_index(self) -> bytes:
        parts = []
        header = struct.pack(
            MAGIC_INDEX_HEADER_FMT,
            MAGIC_INDEX_MAGIC, len(self._entries), 0,
        )
        parts.append(header)
        for i, entry in enumerate(self._entries):
            ext = Path(entry.name).suffix.lower()
            magic_bytes = FILE_MAGICS.get(ext, b"")
            if len(magic_bytes) > 32:
                magic_bytes = magic_bytes[:32]
            else:
                magic_bytes = magic_bytes.ljust(32, b"\x00")
            name_bytes = entry.name.encode("utf-8")
            me = struct.pack(
                MAGIC_ENTRY_FMT,
                i, entry.entry_type, entry.group_id,
                len(magic_bytes), magic_bytes,
                len(name_bytes), b"\x00" * 6,
            )
            parts.append(me)
        result = b"".join(parts)
        index_size = len(result)
        result = result[:8] + struct.pack("<I", index_size) + result[12:]
        return result

    def _build_group_index(self) -> bytes:
        parts = []
        header = struct.pack(
            GROUP_INDEX_HEADER_FMT,
            GROUP_INDEX_MAGIC, len(self._groups), len(self._relations), 0,
        )
        parts.append(header)
        for group in self._groups.values():
            name_bytes = group.name.encode("utf-8")
            meta_bytes = group.metadata.encode("utf-8") if group.metadata else b""
            parts.append(struct.pack(
                "<BBH H", group.group_id, len(group.entry_ids),
                group.group_type, len(name_bytes),
            ))
            parts.append(name_bytes)
            parts.append(struct.pack("<H", len(meta_bytes)))
            if meta_bytes:
                parts.append(meta_bytes)
            parts.append(struct.pack("<H", len(group.entry_ids)))
            for eid in group.entry_ids:
                parts.append(struct.pack("<I", eid))
        for rel in self._relations:
            desc_bytes = rel.description.encode("utf-8") if rel.description else b""
            parts.append(struct.pack(
                "<BBH H", rel.source_group, rel.target_group,
                rel.relation_type, len(desc_bytes),
            ))
            if desc_bytes:
                parts.append(desc_bytes)
        result = b"".join(parts)
        index_size = len(result)
        result = result[:12] + struct.pack("<I", index_size) + result[16:]
        return result

    def _build_toc(self) -> bytes:
        parts = []
        for entry in self._entries:
            name_bytes = entry.name.encode("utf-8")
            mime_bytes = entry.mime_type.encode("utf-8")
            meta_bytes = entry.metadata.encode("utf-8") if entry.metadata else b""
            reserved = bytes([entry.group_id, 0x00])
            fixed = struct.pack(
                TOC_ENTRY_FIXED_FMT,
                entry.entry_type, entry.compression, reserved,
                entry.crc32, entry.created_at, entry.modified_at,
                entry.original_size, entry.stored_size, entry.blob_offset,
                len(name_bytes),
            )
            parts.append(fixed)
            parts.append(name_bytes)
            parts.append(struct.pack("<H", len(mime_bytes)))
            parts.append(mime_bytes)
            parts.append(struct.pack("<H", len(meta_bytes)))
            if meta_bytes:
                parts.append(meta_bytes)
        return b"".join(parts)

    def _write_empty_file(self):
        packed_at = int(time.time() * 1000)
        ep_offset = 0
        ep_size = 0
        if self._encrypted:
            ep_offset = HEADER_SIZE
            ep_size = ENCRYPTION_PARAMS_SIZE
            self._file.write(self._build_encryption_params())

        magic_index_offset = HEADER_SIZE + ep_size
        mi_bytes = struct.pack(
            MAGIC_INDEX_HEADER_FMT,
            MAGIC_INDEX_MAGIC, 0, MAGIC_INDEX_HEADER_SIZE,
        )
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            mi_bytes = xor_bytes(mi_bytes, self._control_key)
        self._file.write(mi_bytes)

        group_index_offset = self._file.tell()
        gi_bytes = struct.pack(
            GROUP_INDEX_HEADER_FMT,
            GROUP_INDEX_MAGIC, 0, 0, GROUP_INDEX_HEADER_SIZE,
        )
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            gi_bytes = xor_bytes(gi_bytes, self._control_key)
        self._file.write(gi_bytes)

        toc_offset = self._file.tell()
        footer_raw = struct.pack(FOOTER_FMT, MAGIC, toc_offset, 0)
        footer_crc = binascii.crc32(footer_raw[:12]) & 0xFFFFFFFF
        self._file.write(struct.pack(FOOTER_FMT, MAGIC, toc_offset, footer_crc))

        flags = FLAG_ENCRYPTED if self._encrypted else 0
        header = struct.pack(
            HEADER_FMT,
            MAGIC, VERSION, flags, packed_at,
            ep_offset, ep_size,
            0, 0,
            group_index_offset, GROUP_INDEX_HEADER_SIZE,
            toc_offset,
        )
        self._file.seek(0)
        self._file.write(header)
        self._file.close()

    @property
    def entries(self) -> list[TocEntry]:
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def groups(self) -> list[GroupEntry]:
        return list(self._groups.values())

    @property
    def is_encrypted(self) -> bool:
        return self._encrypted
