"""MCPK v2 文件写入工具。

支持：
- Magic Index Table（文件签名聚合）
- 分组存储（相关文件物理相邻）
- Group Index（分组元数据 + 组间关系 + 组内关系 + 标签）
- VIDEO 条目类型
- 完整时间戳（created_at / modified_at / packed_at）
- 可选 XOR 流加密（v2.1 兼容）
- 可选 AES-256-GCM 认证加密（v2.2 高强度）
- 按文件夹打包（import_folder）
- JSON 索引打包（load_index）
"""

from __future__ import annotations

import binascii
import hashlib
import json
import os
import struct
import time
import warnings
import zlib
from pathlib import Path
from typing import Optional, Union

from .constants import (
    MAGIC, VERSION, HEADER_SIZE, FOOTER_SIZE, MAGIC_ENTRY_SIZE,
    MAGIC_INDEX_MAGIC, GROUP_INDEX_MAGIC, ENCRYPTION_PARAMS_MAGIC,
    NO_GROUP, ENCRYPTION_PARAMS_SIZE_LEGACY, ENCRYPTION_PARAMS_SIZE_V2,
    ENCRYPTION_PARAMS_SIZE, AES_GCM_NONCE_SIZE, AES_GCM_TAG_SIZE,
    PBKDF2_DEFAULT_ITERATIONS,
    HEADER_FMT, FOOTER_FMT, TOC_ENTRY_FIXED_FMT,
    MAGIC_INDEX_HEADER_FMT, MAGIC_INDEX_HEADER_SIZE,
    MAGIC_ENTRY_FMT, GROUP_INDEX_HEADER_FMT, GROUP_INDEX_HEADER_SIZE,
    ENCRYPTION_PARAMS_FMT_LEGACY, ENCRYPTION_PARAMS_FMT_V2,
    EntryType, Compression, GroupType, RelationType, IntraRelationType,
    EncryptionMode, KdfType, FLAG_ENCRYPTED,
    EXTENSION_MAP, FILE_MAGICS,
)
from .types import (
    FileHeader, TocEntry, MagicEntry, GroupEntry, GroupRelation,
    IntraRelation, EncryptionParams,
)

# ── 可选依赖：cryptography（AES-GCM）──────────────────────
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ── 加密工具函数 ────────────────────────────────────────────

def xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR 流加密/解密（与 1apluse xor_bytes 一致）。"""
    if not key:
        return data
    key_len = len(key)
    if key_len == 1:
        return bytes(b ^ key[0] for b in data)
    result = bytearray(data)
    # 扩展密钥到与数据等长，一次性 XOR（比逐字节循环快 50-100 倍）
    full_key = (key * (len(result) // key_len + 1))[:len(result)]
    for i in range(len(result)):
        result[i] ^= full_key[i]
    return bytes(result)


# ── 可选压缩模块缓存 ──────────────────────────────────────
_zstd_mod = None
_lz4_mod = None
_zstd_checked = False
_lz4_checked = False

def _get_zstd():
    global _zstd_mod, _zstd_checked
    if not _zstd_checked:
        _zstd_checked = True
        try:
            import zstd as _m
            _zstd_mod = _m
        except ImportError:
            pass
    return _zstd_mod

def _get_lz4():
    global _lz4_mod, _lz4_checked
    if not _lz4_checked:
        _lz4_checked = True
        try:
            import lz4.frame as _m
            _lz4_mod = _m
        except ImportError:
            pass
    return _lz4_mod


# ── XOR 模式密钥派生（v2.1 兼容）────────────────────────

def _derive_key(password: str, salt: bytes) -> bytes:
    """从密码 + salt 派生 32 字节主密钥（XOR 模式）。"""
    pwd_bytes = password.encode("utf-8")
    seed = bytes(
        pwd_bytes[i % len(pwd_bytes)] ^ salt[i % len(salt)]
        for i in range(32)
    )
    return hashlib.sha256(seed + salt).digest()


def _derive_control_key(master_key: bytes) -> bytes:
    """派生控制区加密密钥（XOR 模式）。"""
    return hashlib.sha256(master_key + b"ctrl").digest()


def _derive_blob_key(master_key: bytes, entry_id: int, entry_salt: bytes) -> bytes:
    """派生单条目 blob 加密密钥（XOR 模式）。"""
    id_bytes = struct.pack("<I", entry_id)
    return hashlib.sha256(master_key + id_bytes + entry_salt).digest()


# ── AES-GCM 模式密钥派生（v2.2）──────────────────────────

def _derive_key_pbkdf2(password: str, salt: bytes,
                        iterations: int = PBKDF2_DEFAULT_ITERATIONS) -> bytes:
    """PBKDF2-SHA256 派生 256-bit 主密钥。"""
    if not HAS_CRYPTO:
        raise ImportError("AES-GCM 加密需要 cryptography 库: pip install cryptography")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def _derive_subkeys_aes(master_key: bytes) -> tuple[bytes, bytes]:
    """从主密钥派生控制区密钥和数据区密钥基（HKDF-SHA256）。"""
    control_key = HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=None, info=b"mcpk-ctrl",
    ).derive(master_key)
    data_key_base = HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=None, info=b"mcpk-data",
    ).derive(master_key)
    return control_key, data_key_base


def _derive_blob_key_aes(master_key: bytes, entry_id: int, entry_salt: bytes) -> bytes:
    """派生单条目 blob 加密密钥（AES 模式，HKDF）。"""
    id_bytes = struct.pack("<I", entry_id)
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=entry_salt, info=b"mcpk-blob" + id_bytes,
    ).derive(master_key)


def aes_gcm_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM 加密。返回 nonce(12B) + ciphertext + tag(16B)。"""
    nonce = os.urandom(AES_GCM_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce + ct


def aes_gcm_decrypt(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM 解密。输入 nonce(12B) + ciphertext + tag(16B)。"""
    nonce = data[:AES_GCM_NONCE_SIZE]
    ct = data[AES_GCM_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, aad)


# ── Writer ──────────────────────────────────────────────────

class MCPKWriter:
    """
    MCPK v2 文件写入器。

    用法:
        # 不加密（默认）
        with MCPKWriter("output.mcpk") as writer:
            writer.add_file("report.pdf")

        # AES-256-GCM 加密（需 cryptography）
        with MCPKWriter("secret.mcpk", password="mypass") as writer:
            writer.add_file("private.md")

        # XOR 加密（兼容模式，零依赖）
        with MCPKWriter("compat.mcpk", password="mypass", encryption="xor") as writer:
            writer.add_file("video.mp4")

        # 按文件夹打包
        with MCPKWriter("folders.mcpk") as writer:
            writer.import_folder("path/to/folder_A")
            writer.import_folder("path/to/folder_B", tags=["项目B"])

        # 从 JSON 索引打包
        with MCPKWriter("indexed.mcpk") as writer:
            writer.load_index("index.json", base_dir="./project/")
    """

    def __init__(
        self,
        output_path: Union[str, Path],
        *,
        password: Optional[str] = None,
        encrypt_mode: Union[str, int] = EncryptionMode.FULL,
        encryption: str = "xor",  # "aes" | "xor" (默认 xor，兼容无 cryptography 环境)
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
        self._data_key_base: Optional[bytes] = None  # AES 模式专用
        self._salt: bytes = b""
        self._encrypt_mode = EncryptionMode.NONE
        self._kdf_type = KdfType.SHA256_XOR
        self._kdf_iterations = 0

        if self._encrypted:
            # 解析加密模式
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
                # 解析加密算法
                encryption = encryption.lower().strip()
                if encryption == "aes":
                    if HAS_CRYPTO:
                        self._kdf_type = KdfType.PBKDF2_AES
                        self._kdf_iterations = PBKDF2_DEFAULT_ITERATIONS
                        self._salt = os.urandom(32)
                        self._master_key = _derive_key_pbkdf2(
                            password, self._salt, self._kdf_iterations
                        )
                        self._control_key, self._data_key_base = _derive_subkeys_aes(
                            self._master_key
                        )
                    else:
                        raise ImportError(
                            "AES-256-GCM 加密需要 cryptography 库。"
                            "请安装: pip install cryptography，"
                            "或使用 encryption='xor' 回退到 XOR 模式。"
                        )

                if encryption == "xor":
                    self._kdf_type = KdfType.SHA256_XOR
                    self._kdf_iterations = 0
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
        tags: Optional[list[str]] = None,
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
            tags=list(tags) if tags else [],
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

    def add_tag(self, group: Union[str, GroupEntry], tag: str):
        """为已有分组添加标签。"""
        if isinstance(group, str):
            if group not in self._groups:
                raise ValueError(f"分组不存在: {group}")
            group = self._groups[group]
        if tag not in group.tags:
            group.tags.append(tag)

    def add_intra_relation(
        self, group_name: str, *,
        source: str, target: str,
        relation_type: int = IntraRelationType.CUSTOM,
        description: str = "",
    ) -> IntraRelation:
        """添加组内条目间关系。source/target 为文件名。"""
        if group_name not in self._groups:
            raise ValueError(f"分组不存在: {group_name}")
        group = self._groups[group_name]

        # 查找条目 ID
        src_id = None
        tgt_id = None
        for i, entry in enumerate(self._entries):
            if entry.name == source and entry.group_id == group.group_id:
                src_id = i
            if entry.name == target and entry.group_id == group.group_id:
                tgt_id = i

        if src_id is None:
            raise ValueError(f"组内未找到源文件: {source}")
        if tgt_id is None:
            raise ValueError(f"组内未找到目标文件: {target}")

        rel = IntraRelation(
            source_entry=src_id, target_entry=tgt_id,
            relation_type=relation_type, description=description,
        )
        group.intra_relations.append(rel)
        return rel

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

    def import_folder(
        self, folder_path: Union[str, Path], *,
        group_name: Optional[str] = None,
        recursive: bool = True,
        tags: Optional[list[str]] = None,
        group_type: int = GroupType.GENERIC,
        metadata: Optional[dict] = None,
        metadata_fn=None,
    ) -> GroupEntry:
        """
        导入文件夹，自动创建同名分组。

        Args:
            folder_path: 文件夹路径
            group_name: 分组名（默认=文件夹名）
            recursive: 是否递归子目录
            tags: 分组标签
            group_type: 分组类型
            metadata: 分组元数据
            metadata_fn: 条目级元数据回调

        Returns:
            创建的 GroupEntry
        """
        folder_path = Path(folder_path)
        if not folder_path.is_dir():
            raise NotADirectoryError(f"不是目录: {folder_path}")

        if group_name is None:
            group_name = folder_path.name

        if group_name not in self._groups:
            group = self.create_group(
                group_name, group_type, metadata=metadata, tags=tags,
            )
        else:
            group = self._groups[group_name]
            if tags:
                for t in tags:
                    if t not in group.tags:
                        group.tags.append(t)

        pattern = "**/*" if recursive else "*"
        for f in sorted(folder_path.glob(pattern)):
            if not f.is_file():
                continue
            relative = f.relative_to(folder_path)
            arcname = str(relative).replace("\\", "/")
            meta = metadata_fn(f) if metadata_fn else None
            self.add_file(f, arcname=arcname, metadata=meta, group=group)

        return group

    def load_index(
        self, index_path: Union[str, Path], *,
        base_dir: Union[str, Path] = ".",
    ) -> dict:
        """
        从 JSON 索引文件加载打包配置。

        JSON 格式:
        {
            "name": "包名称",
            "description": "描述",
            "groups": [
                {
                    "name": "组名",
                    "type": "COURSE",
                    "tags": ["tag1"],
                    "metadata": {},
                    "files": [
                        {"path": "relative/path.ext", "title": "显示名"},
                        "another/file.ext"
                    ]
                }
            ],
            "standalone_files": [
                {"path": "file.ext", "tags": ["optional"]},
                "simple_file.txt"
            ],
            "relations": [
                {"source": "组A", "target": "组B", "type": "SEQUEL", "desc": "..."}
            ],
            "intra_relations": [
                {"group": "组名", "source": "a.mp4", "target": "a.srt",
                 "type": "SUBTITLE_OF", "desc": "..."}
            ]
        }

        Returns:
            {"loaded": int, "skipped": list, "groups_created": int, "relations_created": int}
        """
        index_path = Path(index_path)
        base_dir = Path(base_dir)

        if not index_path.is_file():
            raise FileNotFoundError(f"索引文件不存在: {index_path}")

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        result = {
            "loaded": 0,
            "skipped": [],
            "groups_created": 0,
            "relations_created": 0,
        }

        # GroupType 名称映射
        gt_map = {name.lower(): val for name, val in GroupType.__members__.items()}
        # RelationType 名称映射
        rt_map = {name.lower(): val for name, val in RelationType.__members__.items()}
        # IntraRelationType 名称映射
        irt_map = {name.lower(): val for name, val in IntraRelationType.__members__.items()}

        # ── 处理 groups ──
        for gspec in index.get("groups", []):
            gname = gspec["name"]
            gtype_str = gspec.get("type", "GENERIC").upper()
            gtype = gt_map.get(gtype_str.lower(), GroupType.GENERIC)
            gtags = gspec.get("tags", [])
            gmeta = gspec.get("metadata")

            if gname not in self._groups:
                self.create_group(gname, gtype, metadata=gmeta, tags=gtags)
                result["groups_created"] += 1
            else:
                # 已存在则补充 tags
                group = self._groups[gname]
                for t in gtags:
                    if t not in group.tags:
                        group.tags.append(t)

            group = self._groups[gname]
            for filespec in gspec.get("files", []):
                if isinstance(filespec, str):
                    fpath = filespec
                    fmeta = None
                else:
                    fpath = filespec["path"]
                    fmeta = {"title": filespec["title"]} if "title" in filespec else None

                full_path = base_dir / fpath
                if not full_path.is_file():
                    result["skipped"].append((fpath, "文件不存在"))
                    warnings.warn(f"跳过不存在的文件: {fpath}", stacklevel=2)
                    continue

                arcname = Path(fpath).name
                try:
                    self.add_file(full_path, arcname=arcname,
                                  metadata=fmeta, group=group)
                    result["loaded"] += 1
                except Exception as e:
                    result["skipped"].append((fpath, str(e)))
                    warnings.warn(f"跳过文件 {fpath}: {e}", stacklevel=2)

        # ── 处理 standalone_files ──
        for filespec in index.get("standalone_files", []):
            if isinstance(filespec, str):
                fpath = filespec
                ftags = []
                fmeta = None
            else:
                fpath = filespec["path"]
                ftags = filespec.get("tags", [])
                fmeta = {"title": filespec["title"]} if "title" in filespec else None

            full_path = base_dir / fpath
            if not full_path.is_file():
                result["skipped"].append((fpath, "文件不存在"))
                warnings.warn(f"跳过不存在的文件: {fpath}", stacklevel=2)
                continue

            arcname = Path(fpath).name
            try:
                self.add_file(full_path, arcname=arcname, metadata=fmeta)
                result["loaded"] += 1
            except Exception as e:
                result["skipped"].append((fpath, str(e)))
                warnings.warn(f"跳过文件 {fpath}: {e}", stacklevel=2)

        # ── 处理 relations ──
        for rspec in index.get("relations", []):
            src = rspec["source"]
            tgt = rspec["target"]
            rtype_str = rspec.get("type", "RELATED").upper()
            rtype = rt_map.get(rtype_str.lower(), RelationType.RELATED)
            rdesc = rspec.get("desc", "")

            if src in self._groups and tgt in self._groups:
                self.add_relation(src, tgt, rtype, description=rdesc)
                result["relations_created"] += 1
            else:
                missing = []
                if src not in self._groups:
                    missing.append(src)
                if tgt not in self._groups:
                    missing.append(tgt)
                warnings.warn(
                    f"跳过关系 (分组不存在: {', '.join(missing)})", stacklevel=2
                )

        # ── 处理 intra_relations ──
        for rspec in index.get("intra_relations", []):
            gname = rspec["group"]
            src = rspec["source"]
            tgt = rspec["target"]
            rtype_str = rspec.get("type", "CUSTOM").upper()
            rtype = irt_map.get(rtype_str.lower(), IntraRelationType.CUSTOM)
            rdesc = rspec.get("desc", "")

            if gname not in self._groups:
                warnings.warn(
                    f"跳过组内关系 (分组不存在: {gname})", stacklevel=2
                )
                continue

            try:
                self.add_intra_relation(
                    gname, source=src, target=tgt,
                    relation_type=rtype, description=rdesc,
                )
            except ValueError as e:
                warnings.warn(f"跳过组内关系: {e}", stacklevel=2)

        return result

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
            ep_bytes = self._build_encryption_params()
            ep_size = len(ep_bytes)
            self._file.write(ep_bytes)
            cursor += ep_size

        # ── Step 1: 写入 Magic Index ──
        magic_index_offset = cursor
        mi_bytes = self._build_magic_index()
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            mi_bytes = self._encrypt_control(mi_bytes)
        mi_encrypted_size = len(mi_bytes)  # 存入 header，供 reader 定位 MI
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
                blob = self._encrypt_blob(blob, original_idx)
                entry.stored_size = len(blob)
            self._file.write(blob)
            cursor += len(blob)

        # ── Step 3: 写入 Group Index ──
        group_index_offset = cursor
        gi_bytes = self._build_group_index()
        gi_original_size = len(gi_bytes)  # 保存原始大小
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            gi_bytes = self._encrypt_control(gi_bytes)
        self._file.write(gi_bytes)
        cursor += len(gi_bytes)

        # ── Step 4: 写入 TOC ──
        toc_offset = cursor
        toc_bytes = self._build_toc()
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            toc_bytes = self._encrypt_control(toc_bytes)
        self._file.write(toc_bytes)
        cursor += len(toc_bytes)

        # ── Step 5: 写入 Footer ──
        footer_raw = struct.pack(FOOTER_FMT, MAGIC, toc_offset, 0)
        footer_crc = binascii.crc32(footer_raw[:12]) & 0xFFFFFFFF
        self._file.write(struct.pack(FOOTER_FMT, MAGIC, toc_offset, footer_crc))

        # ── Step 6: 回写 Header ──
        flags = FLAG_ENCRYPTED if self._encrypted else 0
        # header 第 10 个字段（group_index_size 位置）存储 mi_encrypted_size
        # Reader 用它精确读取 MI，GI 大小通过 toc_offset - gi_offset 计算
        header = struct.pack(
            HEADER_FMT,
            MAGIC, VERSION, flags, packed_at,
            ep_offset, ep_size,
            len(self._entries), len(self._groups),
            group_index_offset, mi_encrypted_size,
            toc_offset,
        )
        self._file.seek(0)
        self._file.write(header)
        self._file.close()

    # ── 加密/解密内部方法 ───────────────────────────────────

    def _encrypt_control(self, data: bytes) -> bytes:
        """加密控制区数据。"""
        if self._kdf_type == KdfType.PBKDF2_AES:
            return aes_gcm_encrypt(self._control_key, data, aad=b"mcpk-ctrl")
        else:
            return xor_bytes(data, self._control_key)

    def _encrypt_blob(self, blob: bytes, entry_id: int) -> bytes:
        """加密数据区 blob，返回 [salt(16B)] + [加密数据]。"""
        entry_salt = os.urandom(16)
        if self._kdf_type == KdfType.PBKDF2_AES:
            blob_key = _derive_blob_key_aes(self._data_key_base, entry_id, entry_salt)
            encrypted = aes_gcm_encrypt(blob_key, blob, aad=struct.pack("<I", entry_id))
        else:
            blob_key = _derive_blob_key(self._master_key, entry_id, entry_salt)
            encrypted = xor_bytes(blob, blob_key)
        return entry_salt + encrypted

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

        # 分组归属
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
            m = _get_zstd()
            if m is not None:
                return m.compress(data, 3)
            return zlib.compress(data, level=6)
        elif compression == Compression.LZ4:
            m = _get_lz4()
            if m is not None:
                return m.compress(data)
            return zlib.compress(data, level=6)
        else:
            raise ValueError(f"未知压缩算法: {compression}")

    def _build_encryption_params(self) -> bytes:
        """构建 Encryption Params 区。"""
        if self._kdf_type == KdfType.PBKDF2_AES:
            key_verify = hashlib.sha256(
                self._master_key + b"verify"
            ).digest()
            return struct.pack(
                ENCRYPTION_PARAMS_FMT_V2,
                ENCRYPTION_PARAMS_MAGIC,
                KdfType.PBKDF2_AES,
                self._encrypt_mode,
                b"\x00" * 2,
                self._kdf_iterations,
                self._salt,
                key_verify,
            )
        else:
            key_hash = hashlib.sha256(self._control_key).digest()
            return struct.pack(
                ENCRYPTION_PARAMS_FMT_LEGACY,
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
            # 用字符串操作替代 Path() 构造
            dot = entry.name.rfind(".")
            ext = entry.name[dot:].lower() if dot >= 0 else ""
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

            # tags 序列化
            tag_parts = []
            for tag in group.tags:
                tag_bytes = tag.encode("utf-8")
                tag_parts.append(struct.pack("<H", len(tag_bytes)))
                tag_parts.append(tag_bytes)

            # entry_ids 序列化
            eid_parts = []
            for eid in group.entry_ids:
                eid_parts.append(struct.pack("<I", eid))

            # intra_relations 序列化
            ir_parts = []
            for ir in group.intra_relations:
                desc_bytes = ir.description.encode("utf-8") if ir.description else b""
                ir_parts.append(struct.pack(
                    "<II H H",
                    ir.source_entry, ir.target_entry,
                    ir.relation_type, len(desc_bytes),
                ))
                if desc_bytes:
                    ir_parts.append(desc_bytes)

            # 写入 group entry
            parts.append(struct.pack(
                "<BBH H", group.group_id, len(group.entry_ids),
                group.group_type, len(name_bytes),
            ))
            parts.append(name_bytes)
            parts.append(struct.pack("<H", len(meta_bytes)))
            if meta_bytes:
                parts.append(meta_bytes)
            # tags
            parts.append(struct.pack("<H", len(group.tags)))
            for tp in tag_parts:
                parts.append(tp)
            # entry_ids
            parts.append(struct.pack("<H", len(group.entry_ids)))
            for ep in eid_parts:
                parts.append(ep)
            # intra_relations
            parts.append(struct.pack("<H", len(group.intra_relations)))
            for ip in ir_parts:
                parts.append(ip)

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
            ep_bytes = self._build_encryption_params()
            ep_size = len(ep_bytes)
            self._file.write(ep_bytes)

        magic_index_offset = HEADER_SIZE + ep_size
        mi_bytes = struct.pack(
            MAGIC_INDEX_HEADER_FMT,
            MAGIC_INDEX_MAGIC, 0, MAGIC_INDEX_HEADER_SIZE,
        )
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            mi_bytes = self._encrypt_control(mi_bytes)
        mi_encrypted_size = len(mi_bytes)
        self._file.write(mi_bytes)

        group_index_offset = self._file.tell()
        gi_bytes = struct.pack(
            GROUP_INDEX_HEADER_FMT,
            GROUP_INDEX_MAGIC, 0, 0, GROUP_INDEX_HEADER_SIZE,
        )
        if self._encrypted and self._encrypt_mode in (
            EncryptionMode.FULL, EncryptionMode.METADATA_ONLY
        ):
            gi_bytes = self._encrypt_control(gi_bytes)
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
            group_index_offset, mi_encrypted_size,
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
