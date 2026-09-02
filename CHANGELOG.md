# 更新日志

## 3.4.1（工程优化，未发布）

### 修复
- 修复 `ui.py` 中 f-string 表达式含反斜杠导致的 Python 3.8–3.11 启动失败（SyntaxError）
- 修复管理员窗口删除条目按"文件名"匹配的问题：两个不同目录下的同名文件不再被同时误删，改为按真实路径精确删除
- 修复测试套件改写真实 `apluse_config.json` 的问题（测试现已完全隔离到临时目录）
- 修复管理员窗口在列表文件已消失时刷新崩溃（大小显示 `?`）

### 变更
- 三个窗口的文件列表条目改为「文件名 + 大小」显示，完整路径移至悬停提示
- 开发者窗口密钥信息改为紧凑显示（`HEX=… ｜ 文本=…`），完整详情移至悬停提示
- 仓库不再跟踪生成的 `apluse_restore_android/` 产物与运行时配置 `apluse_config.json`
- 清理 7 个文件的 UTF-8 BOM；修复 gradle 模板中的非法转义序列

### 工程
- 测试从 29 条增至 45 条：新增恢复脚本模板回归（生成脚本与主引擎往返）、GUI 离屏冒烟（三窗口构建 + 主题切换）、引擎级伪装→还原双向往返
- 新增 `engine_window.py` 公共基类，`ui_dev.py` / `admin_ui.py` 收敛约 150 行重复逻辑（用户可见字符串逐字不变）
- 新增 `restore_template.py`（恢复脚本模板独立模块）、`app_bootstrap.py`（入口引导）、`tools/render_ui_preview.py`（UI 截图对比工具）
- 版本号统一为 `core.APP_VERSION` 单一来源
- 新增 `pyproject.toml`、ruff（错误级 lint）、pre-commit、GitHub Actions 测试矩阵（3.8–3.13）、覆盖率统计
