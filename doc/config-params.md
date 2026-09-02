# 配置参数参考

## 配置文件

### `apluse_config.json`

运行时自动生成，存储在持久化目录中。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `magic` | string | `"4447534B"` (DGSK) | 魔术字（HEX 格式） |
| `magic_text` | string | `null` | 魔术字的文本表示（可打印 ASCII 时显示） |
| `target_files` | string[] | `[]` | 目标文件路径列表 |
| `mask_library` | string[] | `[]` | 面具文件路径列表 |
| `rename_mapping` | bool | `false` | 是否启用序号重命名伪装 |
| `disguise_mapping_txt` | bool | `false` | 是否生成映射清单文件 |
| `developer_password` | string | 默认密码 | 开发者窗口密码 |
| `last_theme` | int | `0` | 上次使用的主题索引（0-6） |

### 配置迁移

旧版 `mask_config.json` 会在首次启动时自动迁移到新版 `apluse_config.json`，字段映射：

| 旧字段 | 新字段 |
|--------|--------|
| `magic` | `magic` |
| `files` | `target_files` |
| `masks` | `mask_library` |

## 魔术字

魔术字是伪装文件的唯一标识标记，写入每个伪装文件的末尾。

### 格式

- **HEX 格式**：十六进制字符串，如 `4447534B`（对应 ASCII "DGSK"）
- **文本格式**：可直接输入 ASCII 文本，如 `DGSK`
- **随机生成**：点击「随机」按钮生成 4 字节随机魔术字

### 约束

- 长度：1-255 字节
- 还原时必须使用与伪装时相同的魔术字
- 生成的恢复工具会内置魔术字，但也支持手动输入

## 主题系统

7 套内置主题，通过索引选择：

| 索引 | 名称 | 风格 |
|------|------|------|
| 0 | 暗色极客 | 深色背景 + 绿色/青色高亮 |
| 1 | 亮色极简 | 浅色背景 + 蓝色主调 |
| 2 | 渐变幽蓝 | 深蓝渐变 + 蓝色高亮 |
| 3 | 暗金奢华 | 深色背景 + 金色高亮 |
| 4 | 猛男猛粉 | 深色背景 + 粉色高亮 |
| 5 | 辐射废土 | 暗绿背景 + 黄绿色高亮 |
| 6 | 低调暗紫 | 深色背景 + 紫色高亮 |

主题定义在 `apluse/themes.py` 的 `PALETTES` 字典中，每套主题包含以下颜色参数：

| 参数 | 说明 |
|------|------|
| `bg` | 主背景色 |
| `bg2` | 次背景色（输入框、列表） |
| `text` | 主文字色 |
| `sub_text` | 次文字色 |
| `accent` | 强调色（按钮、选中项） |
| `accent_hover` | 强调色悬停态 |
| `border` | 边框色 |
| `danger` | 危险色（删除按钮） |
| `shadow` | 阴影色 |

## 伪装参数

### 分块大小

```python
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
```

伪装/还原操作以 4MB 为单位分块处理，平衡内存占用和 I/O 效率。

### 序号重命名

启用后，伪装文件会被重命名为 `{index}.{mask_ext}` 格式：
- `0.mp4`, `1.mp4`, `2.mp4`, ...
- 同时生成 `mapping.txt` 映射清单，记录原始文件名与伪装文件名的对应关系

### 映射清单格式

```
# APLUSE ENGINE 伪装映射清单
# 生成时间: 2026-09-02 16:00:00
# 魔术字: 4447534B
original_1.pdf → 0.mp4
original_2.docx → 1.mp4
original_3.jpg → 2.mp4
```

## MCPK 参数

### 打包参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `compression` | enum | AUTO | 压缩算法（NONE/ZLIB/ZSTD/LZ4/AUTO） |
| `encryption` | enum | NONE | 加密方式（XOR/AES） |
| `encrypt_mode` | enum | FULL | 加密范围（FULL/METADATA/DATA） |
| `password` | string | `null` | 加密密码 |
| `group` | bool | `false` | 是否创建分组 |
| `auto_group` | bool | `false` | 是否按文件类型自动分组 |

### 条目类型自动识别

| 扩展名 | 条目类型 |
|--------|---------|
| txt, md, json, csv, html, xml, css, js, py, java, c, cpp, h, log | DOCUMENT |
| jpg, jpeg, png, gif, bmp, svg, webp, tiff, ico | IMAGE |
| mp3, wav, flac, aac, ogg, wma, m4a | AUDIO |
| mp4, avi, mkv, mov, wmv, flv, webm | VIDEO |
| py, js, java, c, cpp, h, go, rs, ts, rb, php, swift, kt | CODE |
| 其他 | DOCUMENT |

### 压缩算法自动选择

| 文件类型 | 压缩算法 | 原因 |
|---------|---------|------|
| 文本类文件 | ZLIB | 文本压缩率高 |
| 已压缩格式 | NONE | 再压缩无意义，浪费 CPU |
| 其他文件 | NONE | 默认不压缩 |

### 加密参数

**XOR 流加密：**
| 参数 | 值 |
|------|-----|
| 密钥派生 | PBKDF2-HMAC-SHA256 |
| 迭代轮数 | 100,000 |
| 盐长度 | 16 字节 |
| 密钥长度 | 32 字节 |

**AES-256-GCM：**
| 参数 | 值 |
|------|-----|
| 密钥派生 | PBKDF2-HMAC-SHA256 |
| 迭代轮数 | 600,000 |
| 盐长度 | 16 字节 |
| 密钥长度 | 32 字节 |
| Nonce 长度 | 12 字节（每块独立） |
| 认证标签 | 16 字节 |

## 恢复工具参数

### Windows 恢复程序

| 参数 | 说明 |
|------|------|
| 输入目录 | 恢复程序所在目录 |
| 扫描范围 | 递归扫描所有子目录 |
| 跳过文件 | `restore_all_disguised.exe` / `.py` 自身 |
| 输出位置 | 与伪装文件同目录 |
| 冲突处理 | 自动追加 `_restored_N` 后缀 |

### Android 恢复包

| 参数 | 说明 |
|------|------|
| 最低 SDK | API 21 (Android 5.0) |
| 目标 SDK | API 34 (Android 14) |
| 权限 | `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, `MANAGE_EXTERNAL_STORAGE` |
| 图标 | 自动从 `icon.ico` 转换（需 Pillow） |

## 开发者窗口密码

| 配置方式 | 说明 |
|---------|------|
| 默认密码 | 内置 fallback 密码 |
| 配置文件 | `apluse_config.json` 中的 `developer_password` 字段 |
| 修改方式 | 在配置文件中直接编辑，重启后生效 |

## 日志配置

| 参数 | 值 |
|------|-----|
| 日志文件 | `apluse.log`（持久化目录） |
| 格式 | `[时间] 消息内容` |
| 轮转阈值 | 5 MB |
| 轮转策略 | rename → `.1` → 删除旧文件 |
