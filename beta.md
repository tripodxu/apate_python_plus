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
