# APLUSE ENGINE + MCPK Manager

个人知识管理与文件伪装还原工具集。  
支持将文档/图片/音频打包为 `.mcpk` 归档，也支持把任意文件伪装成另一种格式并一键还原。  

本仓库提供两种可用模式：
- **伪装管理员模式（推荐给只做伪装/还原的用户）**
- **完整模式（伪装 + MCPK 管理）**

## 模式说明

### 1) 伪装管理员模式
仅保留伪装/还原相关能力，界面更聚焦，适合“管理员工具”场景。  
入口：`admin_main.py`

功能包含：
- 魔术字管理（应用/随机/默认）
- 目标文件队列管理
- 面具文件库管理
- 序号重命名输出（1.mp4, 2.mp4 ...）
- 映射清单生成（可选伪装映射文件）
- 扫描检测、伪装/还原执行、日志与进度

### 2) 完整模式
保留全部功能：伪装 + MCPK 打包浏览。  
入口：`main.py`

## 环境要求

- Python 3.8+
- PyQt5

```bash
pip install pyqt5
```

## 快速运行

### 运行伪装管理员模式
```bash
python admin_main.py
```

### 运行完整模式
```bash
python main.py
```

## TDD 与测试

本项目已补充完整的测试驱动开发用例，推荐在改动后执行：

```bash
python -m pytest -q
```

当前测试覆盖：
- 核心配置与工具函数边界
- 伪装/还原往返与异常场景
- MCPK 打包、提取、篡改检测
- 引擎行为（空队列、缺面具、映射开关）
- 序号重命名与映射清单生成

## 打包方式（两种）

### 方式一：伪装管理员版打包（只含伪装板块）

PyInstaller（推荐）：
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico -n apluse-admin --add-data "icon.ico;." --clean admin_main.py
```

Nuitka：
```bash
nuitka --standalone --onefile --windows-console-mode=disable --enable-plugin=pyqt5 --windows-icon-from-ico=icon.ico --output-filename=apluse-admin --include-data-files=icon.ico=icon.ico --clean-cache=all admin_main.py
```

### 方式二：完整版打包（伪装 + MCPK）

PyInstaller（推荐）：
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico -n apluse --add-data "icon.ico;." --clean main.py
```

Nuitka：
```bash
nuitka --standalone --onefile --windows-console-mode=disable --enable-plugin=pyqt5 --windows-icon-from-ico=icon.ico --output-filename=apluse --include-data-files=icon.ico=icon.ico --clean-cache=all main.py
```

## 项目结构

```
apluse/
├─ main.py                 # 完整模式入口
├─ admin_main.py           # 伪装管理员模式入口
├─ core.py                 # 核心引擎：伪装/还原、配置管理、MCPK集成
├─ ui.py                   # 完整模式UI（含 MCPK 管理）
├─ admin_ui.py             # 伪装管理员模式UI（仅伪装功能）
├─ ui_dev.py               # 开发者模式界面
├─ themes.py               # 主题配置
├─ android_templates.py    # Android 项目模板
├─ mcpk/                   # MCPK 容器格式库
│  ├─ __init__.py
│  ├─ constants.py
│  ├─ types.py
│  ├─ writer.py
│  └─ reader.py
├─ tests/                  # 自动化测试
│  ├─ test_core_basics.py
│  ├─ test_disguise_reveal.py
│  ├─ test_mcpk.py
│  ├─ test_engine_behavior.py
│  └─ test_rename_mapping.py
├─ icon.ico                # 应用图标
└─ apluse_config.json      # 自动生成配置文件
```

## 建议

- 若你只做“伪装/还原”工作，建议使用 `admin_main.py` 产物，界面更干净、操作更直接。
- 若你需要 `.mcpk` 打包浏览能力，请使用 `main.py` 完整模式。

## 致谢

思路来源：[apate](https://github.com/rippod/apate)









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

| 类型     | 扩展名示例                | 默认压缩                      |
| -------- | ------------------------- | ----------------------------- |
| DOCUMENT | .md .txt .pdf .json .docx | 文本类 zlib，已压缩格式不压缩 |
| IMAGE    | .jpg .png .gif .webp .bmp | 已压缩格式不压缩，BMP 等 zlib |
| AUDIO    | .mp3 .wav .ogg .flac      | 已压缩格式不压缩，WAV 等 zstd |

### 设计特点

- **流式写入**：顺序写入 blob，最后写 TOC，适合打包大量文件
- **随机读取**：通过 TOC 索引直接跳转到任意条目，无需顺序扫描
- **独立压缩**：每条目单独选择压缩算法（zlib/zstd/lz4），已压缩格式自动跳过
- **CRC32 校验**：每条目存储原始数据的 CRC32，读取时自动验证完整性
- **内建元数据**：每条目可附带 JSON 元数据（标题、标签、自定义字段）
- **条目关系**：通过 `parent_id` 和 `relationships` 建立条目间的关联（缩略图、附件、转写文本等）
- **自描述**：文件头包含完整布局信息，不依赖外部配置

### 二进制规格

| 结构      | 大小      | 说明                                                         |
| --------- | --------- | ------------------------------------------------------------ |
| Header    | 64 B 固定 | magic(4B) + version(2B) + flags(2B) + created_at(8B) + toc_offset(8B) + toc_size(8B) + entry_count(4B) + data_section_size(4B) + reserved(24B) |
| TOC Entry | 变长      | type(1B) + compression(1B) + reserved(2B) + crc32(4B) + created_at(8B) + original_size(8B) + stored_size(8B) + blob_offset(8B) + name_len(2B) + name + mime_len(2B) + mime + meta_len(2B) + metadata |
| Footer    | 16 B 固定 | magic(4B) + toc_offset(8B) + footer_crc(4B)                  |

所有多字节整数采用小端序。完整规范见 [MCPK-DataFormat.md](https://github.com/tripodxu/MeCapsule/blob/main/MCPK-DataFormat.md)。

## 功能

- 将任意文件/文件夹打包为 `.mcpk` 容器
- 自动识别文件类型，按类型选择压缩策略
- 内建元数据和 CRC32 完整性校验
- 打开已有 `.mcpk` 文件，浏览条目、按文件提取、验证完整性
- 拖拽添加文件，7 套主题切换，操作日志持久化
