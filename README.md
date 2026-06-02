# MCPK Manager v1.2

个人知识管理容器工具。将文档、图片、音频打包为单一 `.mcpk` 归档文件，支持浏览、提取、完整性校验。

MCPK 格式规范与设计文档见 [MeCapsule](https://github.com/tripodxu/MeCapsule)。

## `.mcpk` 容器格式

MCPK（MeCapsule Package）是一种自定义二进制容器格式，专为个人知识管理设计。将多个文件及其元数据合并为单一 `.mcpk` 文件，无需解压即可随机访问任意条目。

### 文件布局

```
┌──────────────────────────────┐
│  FILE HEADER (64 B)          │  magic="MCPK", version, toc_offset, entry_count ...
├──────────────────────────────┤
│  Entry Blob 0                │  原始数据（可能已压缩）
│  Entry Blob 1                │
│  ...                         │
├──────────────────────────────┤
│  TOC (目录表, 变长)           │  每条目: type, compression, crc32, name, mime, metadata
├──────────────────────────────┤
│  FOOTER (16 B)               │  magic + toc_offset + crc32
└──────────────────────────────┘
```

### 条目类型

| 类型 | 扩展名示例 | 默认压缩 |
|------|-----------|---------|
| DOCUMENT | .md .txt .pdf .json .docx | 文本类 zlib，已压缩格式不压缩 |
| IMAGE | .jpg .png .gif .webp .bmp | 已压缩格式不压缩，BMP 等 zlib |
| AUDIO | .mp3 .wav .ogg .flac | 已压缩格式不压缩，WAV 等 zstd |

### 设计特点

- **流式写入**：顺序写入 blob，最后写 TOC，适合打包大量文件
- **随机读取**：通过 TOC 索引直接跳转到任意条目，无需顺序扫描
- **独立压缩**：每条目单独选择压缩算法（zlib/zstd/lz4），已压缩格式自动跳过
- **CRC32 校验**：每条目存储原始数据的 CRC32，读取时自动验证完整性
- **内建元数据**：每条目可附带 JSON 元数据（标题、标签、自定义字段）
- **条目关系**：通过 `parent_id` 和 `relationships` 建立条目间的关联（缩略图、附件、转写文本等）
- **自描述**：文件头包含完整布局信息，不依赖外部配置

### 二进制规格

| 结构 | 大小 | 说明 |
|------|------|------|
| Header | 64 B 固定 | magic(4B) + version(2B) + flags(2B) + created_at(8B) + toc_offset(8B) + toc_size(8B) + entry_count(4B) + data_section_size(4B) + reserved(24B) |
| TOC Entry | 变长 | type(1B) + compression(1B) + reserved(2B) + crc32(4B) + created_at(8B) + original_size(8B) + stored_size(8B) + blob_offset(8B) + name_len(2B) + name + mime_len(2B) + mime + meta_len(2B) + metadata |
| Footer | 16 B 固定 | magic(4B) + toc_offset(8B) + footer_crc(4B) |

所有多字节整数采用小端序。完整规范见 [MCPK-DataFormat.md](https://github.com/tripodxu/MeCapsule/blob/main/MCPK-DataFormat.md)。

## 功能

- 将任意文件/文件夹打包为 `.mcpk` 容器
- 自动识别文件类型，按类型选择压缩策略
- 内建元数据和 CRC32 完整性校验
- 打开已有 `.mcpk` 文件，浏览条目、按文件提取、验证完整性
- 拖拽添加文件，7 套主题切换，操作日志持久化

## 环境要求

- Python 3.8+
- PyQt5

```bash
pip install pyqt5
```

## 构建

### PyInstaller（推荐）

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico -n apluse --add-data "icon.ico;." --clean main.py
```

### Nuitka

```bash
nuitka --standalone --onefile --windows-console-mode=disable --enable-plugin=pyqt5 --windows-icon-from-ico=icon.ico --output-filename=apluse --include-data-files=icon.ico=icon.ico --clean-cache=all main.py
```

## 项目结构

```
apluse/
├── main.py              # 程序入口
├── core.py              # 核心引擎：MCPK 集成、配置管理
├── ui.py                # 主窗口（MCPK Manager）+ 共享 UI 组件
├── ui_dev.py            # 扩展功能界面
├── themes.py            # 主题配色方案
├── android_templates.py # Android 项目模板
├── mcpk/                # MCPK 容器格式库
│   ├── __init__.py
│   ├── constants.py     # 格式常量、MIME 映射
│   ├── types.py         # TocEntry / FileHeader
│   ├── writer.py        # MCPKWriter
│   └── reader.py        # MCPKReader
├── icon.ico             # 应用图标
└── apluse_config.json   # 配置文件（自动生成）
```
