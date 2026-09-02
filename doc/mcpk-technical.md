# MCPK 技术文档

## 概述

MCPK（MeCapsule Package）是一种自定义二进制容器格式，专为个人知识管理设计。它将文档、图片、音频、视频及其元数据打包为单一的 `.mcpk` 文件，支持智能分组、灵活加密和独立压缩。

完整规范见上游仓库：[tripodxu/MeCapsule](https://github.com/tripodxu/MeCapsule)

## 文件格式结构

```
┌────────────────────────────────┐
│ File Header (64B)              │ 文件头：MAGIC、版本、条目数等
├────────────────────────────────┤
│ Encryption Params (56/76B)     │ [可选] 加密参数（密钥派生、盐等）
├────────────────────────────────┤
│ Magic Index (变长)             │ 文件签名快速索引（按类型聚合）
├────────────────────────────────┤
│ Data Section (变长)            │ 按分组排列的实际数据（Blob）
├────────────────────────────────┤
│ Group Index (变长)             │ 分组元数据、标签及关系图
├────────────────────────────────┤
│ TOC (变长)                     │ 所有条目的目录索引
├────────────────────────────────┤
│ Footer (16B)                   │ 包含偏移量和校验和
└────────────────────────────────┘
```

### File Header（64 字节）

| 偏移 | 长度 | 字段 | 说明 |
|------|------|------|------|
| 0 | 4 | magic | 魔数 `0x4D43504B`（"MCPK"） |
| 4 | 2 | version | 格式版本（当前 v2） |
| 6 | 2 | flags | 标志位（加密、压缩等） |
| 8 | 4 | entry_count | 条目总数 |
| 12 | 4 | group_count | 分组数 |
| 16 | 8 | data_offset | 数据区起始偏移 |
| 24 | 8 | data_size | 数据区总大小 |
| 32 | 32 | reserved | 保留字段 |

### TOC Entry（目录索引条目）

每个条目记录一个文件的元信息：

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 文件名 |
| entry_type | enum | 条目类型（DOCUMENT/IMAGE/AUDIO/VIDEO/CODE） |
| compression | enum | 压缩算法（NONE/ZLIB/ZSTD/LZ4） |
| original_size | uint64 | 原始文件大小 |
| stored_size | uint64 | 存储大小（压缩+加密后） |
| offset | uint64 | 数据区中的偏移 |
| crc32 | uint32 | CRC32 校验和 |
| group_id | uint32 | 所属分组 ID |
| created_at | timestamp | 文件创建时间 |
| modified_at | timestamp | 文件修改时间 |
| packed_at | timestamp | 打包时间 |

## 压缩算法

| 算法 | 依赖 | 适用场景 | 说明 |
|------|------|---------|------|
| NONE | 无 | 已压缩格式（jpg/png/mp4/zip） | 跳过压缩，避免浪费 CPU |
| ZLIB | 标准库 | 文本/代码/文档 | 通用压缩，平衡速度与压缩比 |
| ZSTD | zstd 库 | 大文件/高压缩比需求 | 高压缩比，速度快于 zlib |
| LZ4 | lz4 库 | 实时/极速场景 | 极速压缩，压缩比最低 |

自动选择规则：
- 文本类文件（txt/md/json/csv/html/xml/css/js/py/java/c/cpp/h）→ ZLIB
- 已压缩格式（jpg/png/gif/mp4/avi/mkv/zip/rar/7z/gz/bz2/xz）→ NONE
- 其他文件 → NONE

## 加密架构

### XOR 流加密（零依赖）

完全基于 Python 标准库实现，适合零依赖环境。

- 密钥派生：`PBKDF2-HMAC-SHA256`（100,000 轮迭代）
- 加密方式：密钥循环 XOR
- 可选加密范围：全部 / 仅元数据 / 仅数据

### AES-256-GCM 认证加密（需 cryptography）

高强度认证加密，提供机密性 + 完整性 + 真实性。

- 密钥派生：`PBKDF2-HMAC-SHA256`（600,000 轮迭代）
- 密钥派生：`HKDF-SHA256` 为不同区域生成独立密钥
- 每个数据块使用独立随机数（nonce）
- 认证标签（tag）防止篡改

### 加密模式

| 模式 | 说明 |
|------|------|
| full | 加密全部内容（头部 + 数据） |
| metadata | 仅加密元数据（保护文件结构信息） |
| data | 仅加密数据内容 |

## 分组机制

分组允许将相关文件（如视频与字幕、文档与附件）物理相邻存储，提高访问效率。

### Group Entry

| 字段 | 说明 |
|------|------|
| group_id | 分组唯一 ID |
| group_type | 分组类型（FOLDER/SERIES/CUSTOM） |
| name | 分组名称 |
| tags | 标签列表 |
| relations | 组间关系（DEPENDS/RELATED/SEQUENCE） |
| intra_relations | 组内关系（ATTACHED/ALTERNATIVE） |

### 分组类型

| 类型 | 说明 | 典型场景 |
|------|------|---------|
| FOLDER | 文件夹分组 | 按目录结构打包 |
| SERIES | 序列分组 | 视频系列、文档集 |
| CUSTOM | 自定义分组 | 用户手动指定 |

## Python API

### MCPKWriter — 写入器

```python
from apluse.mcpk import MCPKWriter

# 基本打包
with MCPKWriter("archive.mcpk") as w:
    w.add_file("report.pdf")
    w.add_file("photo.jpg")
    w.add_file("notes.txt", entry_type=EntryType.DOCUMENT)

# 按文件夹打包（自动创建分组）
with MCPKWriter("archive.mcpk") as w:
    result = w.import_folder("./my_project/")
    print(f"打包 {result['files']} 文件，创建 {result['groups']} 分组")

# 带加密打包
with MCPKWriter("secret.mcpk", password="mypassword", encryption="aes") as w:
    w.add_file("secret.doc")

# 从 JSON 索引打包
with MCPKWriter("archive.mcpk") as w:
    result = w.load_index("index.json", base_dir="./data/")
```

### MCPKReader — 读取器

```python
from apluse.mcpk import MCPKReader

# 基本读取
with MCPKReader("archive.mcpk") as r:
    # 列出所有条目
    for entry in r.list_entries():
        print(f"{entry.name} ({entry.entry_type})")

    # 提取单个文件
    data = r.extract("report.pdf")

    # 提取全部
    r.extract_all("./output/")

    # 按分组提取
    r.extract_group(group_id=0, output_dir="./group0/")

    # 检查文件信息
    info = r.inspect()
    print(f"版本: {info['version']}, 条目数: {info['entry_count']}")

# 加密文件读取
with MCPKReader("secret.mcpk", password="mypassword") as r:
    data = r.extract("secret.doc")
```

### MCPKError

```python
from apluse.mcpk import MCPKError

try:
    with MCPKReader("corrupted.mcpk") as r:
        r.extract("file.txt")
except MCPKError as e:
    print(f"MCPK 错误: {e}")
```

## CLI 命令

```bash
# 打包文件/目录
python -m mcpk pack ./notes/ -o archive.mcpk

# 带分组打包
python -m mcpk pack ./project/ -o archive.mcpk --group

# 带加密打包
python -m mcpk pack ./secret/ -o secret.mcpk --password mypwd --encryption aes

# 列出条目
python -m mcpk list archive.mcpk

# 列出条目（JSON 格式）
python -m mcpk list archive.mcpk --json

# 按类型过滤
python -m mcpk list archive.mcpk --type video

# 列出分组
python -m mcpk groups archive.mcpk

# 提取全部
python -m mcpk extract archive.mcpk -o ./output/

# 提取单个文件
python -m mcpk extract archive.mcpk report.pdf -o ./output/

# 检查详情
python -m mcpk inspect archive.mcpk

# 验证完整性
python -m mcpk verify archive.mcpk
```

## 性能参考

在普通 PC（SSD）上的测试数据：

| 操作 | 数据量 | 速度 |
|------|--------|------|
| 打包 | 114 MB | ~325 MB/s |
| 提取 | 114 MB | ~1500 MB/s |

依赖说明：
- 核心功能仅需 Python 3.10+ 标准库
- 可选 `cryptography`：启用 AES-256-GCM 加密
- 可选 `zstd`：启用 ZSTD 压缩
- 可选 `lz4`：启用 LZ4 压缩

## 版本兼容

| 格式版本 | 状态 | 说明 |
|---------|------|------|
| v1 | 只读 | 旧版基础格式，可读取不可写入 |
| v2 | 读写 | 当前版本，支持全部特性 |
