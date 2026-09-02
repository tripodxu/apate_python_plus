# 开发日志

## v3.4.2 — 文件夹结构优化（2026-09-02）

### 目标
将根目录散落的 10 个 `.py` 模块收拢到 `apluse/` 包内，形成清晰的包层次结构。

### 变更清单
- 创建 `apluse/` 包，移动 `core.py`、`ui.py`、`ui_dev.py`、`admin_ui.py`、`themes.py`、`android_templates.py`、`restore_template.py`、`app_bootstrap.py`、`engine_window.py`、`mcpk/` 至包内
- 包内所有 import 改为相对导入（`from .core import ...`）
- 创建 `apluse/__init__.py` 提供公共 API 快捷导入
- 删除 `old/` 目录（废弃的 `disguise_ui.py`）和过期的 `beta.md`
- 更新所有测试文件的 import 路径和 `unittest.mock.patch` 目标字符串
- 更新 CI 覆盖率参数、`pyproject.toml` 配置

### 验证结果
- 82 测试全绿 + 2 skipped（与重构前一致）
- 功能零变更

---

## v3.4.1 — 工程优化三阶段（2026-09-02）

### Phase 1+2：工程架构优化

**公共基类抽取**
- 新增 `engine_window.py`，从 `ui_dev.py` 和 `admin_ui.py` 中提取共约 150 行重复逻辑
- 收敛内容：队列装载、文件对话框、异步任务管理、启动确认弹窗
- 文案与控件差异通过类属性/钩子方法注入，保证重构前后用户可见字符串逐字不变

**模板独立化**
- 新增 `restore_template.py`，将 180 行恢复脚本模板从 `core.py` 中抽出
- 模板以 `.replace()` 填充占位符，独立模块便于维护和测试

**入口引导抽象**
- 新增 `app_bootstrap.py`，统一 `main.py` 和 `admin_main.py` 的启动流程
- 包含：安全自检（调试器检测）、QApplication 创建、图标加载

**版本号统一**
- 消除多处硬编码，统一为 `core.APP_VERSION` 单一来源

**代码质量工具链**
- 新增 `pyproject.toml` 配置 pytest 和 ruff
- ruff 仅启用错误级规则（E9/F63/F7/F82），避免对既有代码产生非必要 churn
- 新增 `.pre-commit-config.yaml`
- 新增 GitHub Actions CI（Python 3.8–3.13 矩阵）

### Phase 2.5：测试覆盖率提升

- 测试从 45 条增至 90 条
- 新增 `test_mcpk_cli.py`：覆盖 CLI 全部 6 个命令（pack/list/groups/extract/inspect/verify）及辅助函数
- 新增 `test_core_restore_gen.py`：覆盖恢复工具生成逻辑（Python 路径检测、PyInstaller 安装、exe/apk 生成成功/失败分支）
- 覆盖率从 50% 提升至 65%

### Phase 3：行为级修复

**`reveal_file` 防覆盖**
- 还原时若目标文件名已存在，自动追加 `_restored_N` 后缀
- 通过 `reserved_output_paths` 集合追踪已占用路径

**平台守卫 `self_check`**
- `app_bootstrap.self_check` 仅在 Windows 下启用调试器检测
- 使用 `sys.platform != "win32"` 守卫，避免 Linux/macOS 下 `ctypes.windll` 不存在导致崩溃

**日志轮转**
- `ui.py` 日志文件超过 5MB 时自动轮转（rename → `.1` → 删除旧文件）
- 防止长时间运行导致日志文件无限膨胀

**可配置开发者密码**
- 支持通过配置文件自定义开发者窗口密码
- 配置缺失时 fallback 到默认密码

**README 嵌入脚本修复**
- 修复恢复源码示例中 `reveal_file` 的 double-read bug（先读 metadata 再 seek 回去重复读取）

---

## v3.4 — MCPK 集成与管理员模式

### MCPK 子包
- 集成 [MeCapsule Package v2](https://github.com/tripodxu/MeCapsule) 格式支持
- 支持 `.mcpk` 文件的打包、读取、提取、验证
- CLI 工具：`python -m mcpk pack/list/groups/extract/inspect/verify`
- 加密支持：XOR 流加密（零依赖）+ AES-256-GCM（需 cryptography）
- 分组存储、Magic Index、完整时间戳

### 管理员窗口
- 新增 `admin_ui.py` 独立管理员模式入口
- 精简界面，专注伪装/还原核心功能
- 独立入口：`python admin_main.py`

### UI 增强
- MCPK 浏览器：支持在主界面内预览 `.mcpk` 包内容（图片/GIF/视频/文本）
- 文件列表条目改为「文件名 + 大小」显示，完整路径移至悬停提示
- 开发者窗口密钥信息改为紧凑显示

---

## v3.3 — 多版本兼容与 Android 恢复

- 支持 v1 / v2 / v3 / v4 四种元数据格式的解析与还原
- Android 恢复包生成：自动创建完整 Android 项目，编译为 `.apk`
- 恢复程序支持手动输入魔术字

## v3.1 — 主题系统与批量操作

- 7 套主题配色方案
- 拖拽添加文件/文件夹
- 文件大小显示
- 键盘快捷键支持

## v3.0 — 核心引擎重构

- 一键伪装/还原：自动识别文件当前状态
- 批量处理支持
- 配置文件自动迁移
- 跨分区兼容
