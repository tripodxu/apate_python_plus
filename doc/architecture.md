# 软件架构文档

## 整体架构

APLUSE ENGINE 采用分层架构，从底向上分为：核心引擎层、UI 组件层、窗口层、入口层。

```
┌─────────────────────────────────────────────────┐
│                  入口层                           │
│  main.py / admin_main.py                        │
│  ↓ run_app(MainWindow) / run_app(AdminWindow)   │
├─────────────────────────────────────────────────┤
│                  窗口层                           │
│  MainWindow (ui.py)                             │
│  DeveloperWindow (ui_dev.py)                    │
│  AdminWindow (admin_ui.py)                      │
│  ↕ 共享基类：EngineWindowBase (engine_window.py) │
├─────────────────────────────────────────────────┤
│                UI 组件层                          │
│  CustomTitleBar / CustomDropList (ui.py)        │
│  EngineWorker (ui.py)                           │
│  MCPKViewerDialog (ui.py)                       │
│  themes.py (7 套主题配色)                        │
├─────────────────────────────────────────────────┤
│               核心引擎层                          │
│  DisguiseEngine (core.py)                       │
│  PathManager / 配置管理 (core.py)               │
│  伪装/还原函数 (core.py)                         │
│  MCPK 子包 (mcpk/)                              │
│  模板：restore_template.py / android_templates.py│
├─────────────────────────────────────────────────┤
│               基础设施层                          │
│  PyQt5 / 文件系统 / 加密 / 压缩                  │
└─────────────────────────────────────────────────┘
```

## 包结构

```
apluse/
├── __init__.py            # 公共 API 导出
├── core.py                # 核心引擎（约 1000 行）
├── ui.py                  # PyQt5 主界面（约 1200 行）
├── ui_dev.py              # 开发者窗口
├── admin_ui.py            # 管理员窗口
├── themes.py              # 7 套主题配色方案
├── android_templates.py   # Android 项目模板（Java/Gradle/XML）
├── restore_template.py    # 恢复脚本 Python 模板
├── app_bootstrap.py       # 入口引导
├── engine_window.py       # 开发者/管理员窗口公共基类
└── mcpk/                  # MCPK 文件格式子包
    ├── __init__.py        # 公共 API（MCPKWriter / MCPKReader）
    ├── __main__.py        # python -m mcpk 入口
    ├── cli.py             # CLI 命令实现
    ├── constants.py       # 常量、枚举、MAGIC 魔数
    ├── types.py           # 数据类（TocEntry / FileHeader / GroupEntry 等）
    ├── reader.py          # MCPK 读取器（支持流式/随机读取）
    └── writer.py          # MCPK 写入器（支持流式写入/分组/加密）
```

## 核心模块职责

### `core.py` — 核心引擎

**DisguiseEngine 类**
- 管理配置（魔术字、目标文件列表、面具库）
- 提供伪装/还原的高层 API
- 生成 Windows 恢复程序（`.exe`）和 Android 恢复包（`.apk`）
- MCPK 文件的提取和检查

**文件伪装算法**
1. 读取面具文件（mask）的头部字节
2. XOR 加密原始文件名和头部数据
3. 将加密后的头部追加到伪装文件末尾
4. 追加元数据（原始文件名长度、头部长度、原始大小）
5. 追加魔术字标记

**文件还原算法**
1. 从文件末尾读取魔术字，确认为伪装文件
2. 解析元数据，获取原始文件名、头部长度、原始大小
3. 从末尾提取加密的头部数据
4. 将头部数据还原到文件开头
5. 截断文件到原始大小
6. 重命名为原始文件名（冲突时自动追加后缀）

**配置管理**
- `PathManager`：双路径策略（持久化目录 vs 资源目录）
- 配置文件：`apluse_config.json`（自动生成）
- 自动迁移旧版 `mask_config.json`

### `ui.py` — 主界面

**MainWindow**
- 核心密钥区域：魔术字输入与显示
- 目标执行队列：待处理文件列表
- 面具文件库：伪装用媒体文件列表
- MCPK 功能区域：打包、浏览、提取
- 主题切换：7 套配色方案
- 拖拽支持：文件/文件夹直接拖入

**MCPKViewerDialog**
- `.mcpk` 文件内容浏览器
- 支持预览：图片、GIF、视频、文本
- 支持提取单个/全部文件
- 支持发送到伪装引擎

**EngineWorker**
- 通用异步工作线程
- 信号：log_sig / prog_sig / done_sig / err_sig

### `engine_window.py` — 窗口基类

开发者窗口和管理员窗口的公共逻辑：
- 队列装载（目标文件 / 面具文件）
- 文件对话框（打开文件 / 打开文件夹）
- 异步任务管理
- 启动确认弹窗
- 列表条目格式化（文件名 + 大小）

### `mcpk/` — MCPK 子包

详见 [MCPK 技术文档](./mcpk-technical.md)。

## 数据流

### 伪装流程
```
用户选择目标文件 + 面具文件
  → DisguiseEngine.disguise_file()
    → 读取面具文件头部
    → XOR 加密元数据
    → 追加到目标文件末尾
    → 写入魔术字标记
    → 更新配置
```

### 还原流程
```
用户选择伪装文件
  → DisguiseEngine.reveal_file()
    → 读取魔术字确认
    → 解析元数据
    → 提取头部数据
    → 还原到文件开头
    → 截断 + 重命名
```

### MCPK 打包流程
```
用户选择文件/文件夹
  → MCPKWriter 创建 .mcpk 文件
    → 写入 File Header
    → [可选] 写入加密参数
    → 逐文件处理：压缩 → [加密] → 写入数据区 → 记录 TOC
    → [可选] 写入 Magic Index
    → [可选] 写入 Group Index
    → 写入 Footer
```

## 循环依赖处理

项目中存在两组循环依赖，均通过延迟导入（函数内 import）解决：

1. **`core.py` ↔ `mcpk/`**：`core.py` 在需要 MCPK 功能时才导入 `mcpk` 模块
2. **`ui.py` ↔ `ui_dev.py`**：`ui.py` 在打开开发者窗口时才导入 `ui_dev.DeveloperWindow`

## 测试架构

```
tests/
├── conftest.py              # 共享夹具：PathManager 隔离
├── test_smoke_imports.py    # 冒烟测试：所有模块可导入
├── test_core_basics.py      # 核心函数单元测试
├── test_disguise_reveal.py  # 伪装→还原往返测试
├── test_engine_behavior.py  # DisguiseEngine 行为测试
├── test_restore_script.py   # 恢复脚本模板回归
├── test_core_restore_gen.py # 恢复工具生成逻辑测试
├── test_rename_mapping.py   # 序号重命名与映射清单
├── test_gui_offscreen.py    # GUI 离屏冒烟测试
├── test_mcpk.py             # MCPK 读写测试
└── test_mcpk_cli.py         # MCPK CLI 命令测试
```

测试通过 `conftest.py` 的 `autouse` fixture 自动将 `PathManager.get_persist_dir` 重定向到临时目录，确保测试不会读写真实的 `apluse_config.json`。
