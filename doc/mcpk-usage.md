# MCPK Beta 功能使用指南

> **注意**：MCPK 打包功能目前为 Beta 实验性功能，API 可能在后续版本中调整。

## 快速上手

### 通过主界面使用

1. 启动 APLUSE ENGINE 主程序（`python main.py`）
2. 在主界面找到 MCPK 功能区域
3. 将文件/文件夹拖入 MCPK 打包队列
4. 点击「打包」按钮生成 `.mcpk` 文件

### 通过命令行使用

```bash
# 打包单个目录
python -m mcpk pack ./my_notes/ -o my_notes.mcpk

# 打包多个文件
python -m mcpk pack file1.txt file2.jpg file3.pdf -o archive.mcpk

# 带分组打包（按文件夹结构自动创建分组）
python -m mcpk pack ./project/ -o project.mcpk --group

# 使用自动分组（按文件类型分组）
python -m mcpk pack ./mixed_files/ -o archive.mcpk --auto-group
```

## 加密打包

### XOR 流加密（零依赖）

适合不希望安装额外依赖的场景：

```bash
# 全部加密
python -m mcpk pack ./secret/ -o secret.mcpk --password mypassword

# 仅加密元数据（保护文件结构）
python -m mcpk pack ./secret/ -o secret.mcpk --password mypassword --encrypt-mode metadata

# 仅加密数据内容
python -m mcpk pack ./secret/ -o secret.mcpk --password mypassword --encrypt-mode data
```

### AES-256-GCM 高强度加密

需要安装 `cryptography` 库：

```bash
pip install cryptography

# 使用 AES-256-GCM 加密
python -m mcpk pack ./secret/ -o secret.mcpk --password mypassword --encryption aes

# 从主界面使用：在打包时勾选「AES 加密」选项
```

## 浏览 .mcpk 文件

### 在主界面中浏览

1. 在主界面点击「打开 MCPK 文件」或直接将 `.mcpk` 文件拖入窗口
2. MCPK 浏览器会显示包内所有文件的列表
3. 支持预览：图片（jpg/png/gif）、视频（mp4/avi）、文本文件
4. 加密文件会提示输入密码

### 通过命令行列出

```bash
# 列出所有条目
python -m mcpk list archive.mcpk

# JSON 格式输出（便于程序处理）
python -m mcpk list archive.mcpk --json

# 按类型过滤
python -m mcpk list archive.mcpk --type video
python -m mcpk list archive.mcpk --type image
python -m mcpk list archive.mcpk --type document

# 列出分组信息
python -m mcpk groups archive.mcpk

# 检查文件详情（头部、加密参数、数据区分布等）
python -m mcpk inspect archive.mcpk
```

## 提取文件

### 在主界面中提取

1. 在 MCPK 浏览器中选择要提取的文件
2. 点击「提取选中」或「提取全部」
3. 选择输出目录

### 通过命令行提取

```bash
# 提取全部文件
python -m mcpk extract archive.mcpk -o ./output/

# 提取单个文件
python -m mcpk extract archive.mcpk report.pdf -o ./output/

# 提取加密文件（需要密码）
python -m mcpk extract secret.mcpk -o ./output/ --password mypassword
```

## 完整性验证

```bash
# 验证文件完整性（CRC32 校验）
python -m mcpk verify archive.mcpk

# 验证加密文件
python -m mcpk verify secret.mcpk --password mypassword
```

## 高级用法

### 从 JSON 索引打包

适用于需要精确控制打包内容和分组关系的场景：

```json
{
  "groups": [
    {
      "name": "项目文档",
      "type": "folder",
      "files": [
        {"path": "docs/readme.md", "type": "document"},
        {"path": "docs/api.md", "type": "document"}
      ]
    },
    {
      "name": "媒体素材",
      "type": "custom",
      "tags": ["素材", "2026"],
      "files": [
        {"path": "assets/logo.png", "type": "image"},
        {"path": "assets/demo.mp4", "type": "video"}
      ],
      "relations": [
        {"target_group": 0, "type": "related"}
      ]
    }
  ]
}
```

```bash
# 从索引文件打包
python -m mcpk pack --index index.json -o archive.mcpk

# 指定基础目录
python -m mcpk pack --index index.json --base-dir ./my_project/ -o archive.mcpk
```

### Python API 高级用法

```python
from apluse.mcpk import MCPKWriter, MCPKReader, EntryType, GroupType

# 创建带分组的归档
with MCPKWriter("archive.mcpk") as w:
    # 创建分组
    g1 = w.create_group("文档集", GroupType.SERIES, tags=["工作", "2026"])
    g2 = w.create_group("附件", GroupType.CUSTOM)

    # 添加关系
    w.add_group_relation(g2, g1, RelationType.DEPENDS)

    # 添加文件到指定分组
    w.add_file("report.pdf", group_id=g1)
    w.add_file("data.xlsx", group_id=g1)
    w.add_file("image.png", group_id=g2)

    # 从内存添加数据
    w.add_bytes(b"Hello, World!", "greeting.txt",
                entry_type=EntryType.DOCUMENT, group_id=g1)

# 流式读取大文件
with MCPKReader("archive.mcpk") as r:
    # 按名称查找
    entry = r.find("report.pdf")
    print(f"大小: {entry.original_size}, 类型: {entry.entry_type}")

    # 流式读取（不一次性加载到内存）
    for chunk in r.extract_stream("report.pdf", chunk_size=65536):
        process(chunk)

    # 按分组提取
    r.extract_group(g1, "./docs_output/")
```

## 与伪装引擎联动

MCPK 文件可以作为伪装引擎的目标文件或面具文件：

### 将 .mcpk 文件伪装为其他格式

1. 在主界面的 MCPK 浏览器中打开 `.mcpk` 文件
2. 点击「发送到伪装引擎」按钮
3. `.mcpk` 文件会被添加到开发者模式的目标队列
4. 选择面具文件（如 `.mp4`），启动引擎

### 将文件打包为 .mcpk 后伪装

1. 先将敏感文件打包为 `.mcpk`（可选择加密）
2. 再将 `.mcpk` 文件伪装为普通媒体格式
3. 双重保护：内容加密 + 格式伪装

## 常见问题

### Q: 打包大文件会很慢吗？

A: MCPK 采用流式处理，不会将整个文件加载到内存。在 SSD 上打包 114MB 数据约需 0.35 秒（~325 MB/s）。对于已压缩的多媒体文件（jpg/png/mp4），默认跳过压缩，速度更快。

### Q: 加密会影响提取速度吗？

A: XOR 流加密几乎无性能影响。AES-256-GCM 会有一定开销，但对正常使用场景影响不大。

### Q: .mcpk 文件可以在其他程序中打开吗？

A: 不能。MCPK 是自定义二进制格式，需要使用 APLUSE ENGINE 或 `python -m mcpk` 工具打开。如果需要分享文件，建议先提取再分发。

### Q: 如何选择加密方式？

A:
- **XOR 流加密**：零依赖，适合一般隐私保护
- **AES-256-GCM**：高强度认证加密，适合敏感数据，需安装 `cryptography`
