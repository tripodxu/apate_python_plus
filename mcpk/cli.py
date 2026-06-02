"""MCPK v2 命令行工具。

支持：
- pack: 打包文件/目录（支持 --group 分组、--auto-group 自动分组、--index JSON 索引）
- list: 列出条目（支持 --type video 过滤）
- groups: 列出分组、标签、关系（含组内关系）
- extract: 提取文件/分组
- inspect: 检查详情
- verify: 验证完整性
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .writer import MCPKWriter
from .reader import MCPKReader, MCPKError
from .constants import EntryType, GroupType, RelationType, IntraRelationType


def cmd_pack(args):
    """打包文件/目录为 .mcpk。"""
    output = Path(args.output)
    if not output.suffix:
        output = output.with_suffix(".mcpk")

    password = getattr(args, 'password', None)
    encrypt_mode = getattr(args, 'encrypt_mode', 'full') or 'full'
    encryption = getattr(args, 'encryption', 'xor') or 'xor'

    start = time.time()

    # ── JSON 索引模式 ──
    if hasattr(args, 'index') and args.index:
        base_dir = getattr(args, 'base_dir', '.') or '.'
        with MCPKWriter(output, password=password, encrypt_mode=encrypt_mode,
                        encryption=encryption) as writer:
            result = writer.load_index(args.index, base_dir=base_dir)
            print(f"加载索引: {args.index}")
            print(f"  加载: {result['loaded']} 文件")
            if result['skipped']:
                print(f"  跳过: {len(result['skipped'])} 文件")
                for path, reason in result['skipped']:
                    print(f"    - {path}: {reason}")
            print(f"  创建分组: {result['groups_created']}")
            print(f"  创建关系: {result['relations_created']}")

        elapsed = time.time() - start
        file_size = output.stat().st_size
        print(f"\n打包完成: {output}")
        print(f"  文件大小: {_fmt_size(file_size)}")
        if password:
            print(f"  加密: {encrypt_mode} ({encryption})")
        print(f"  耗时: {elapsed:.2f}s")
        return

    # ── 普通模式 ──
    sources = [Path(p) for p in args.sources]
    for s in sources:
        if not s.exists():
            print(f"错误: 路径不存在: {s}", file=sys.stderr)
            sys.exit(1)

    auto_group = getattr(args, 'auto_group', False)

    with MCPKWriter(output, password=password, encrypt_mode=encrypt_mode,
                    encryption=encryption) as writer:
        group_name = args.group if hasattr(args, 'group') and args.group else None

        for source in sources:
            if source.is_file():
                entry = writer.add_file(source, group_name=group_name)
                print(f"  + {entry.name} ({_fmt_size(entry.original_size)})")
            elif source.is_dir():
                if auto_group:
                    # 每个目录自动创建同名分组
                    group = writer.import_folder(source)
                    count = len(group.entry_ids)
                    print(f"  [{group.name}] {count} 文件")
                else:
                    prefix = args.prefix or ""
                    entries = writer.add_directory(
                        source, prefix=prefix, group_name=group_name
                    )
                    for e in entries:
                        print(f"  + {e.name} ({_fmt_size(e.original_size)})")
            else:
                print(f"跳过: {source}", file=sys.stderr)

    elapsed = time.time() - start
    file_size = output.stat().st_size
    print(f"\n打包完成: {output}")
    print(f"  条目数: {writer.entry_count if hasattr(writer, '_entries') else '?'}")
    print(f"  文件大小: {_fmt_size(file_size)}")
    if writer.is_encrypted:
        print(f"  加密: {encrypt_mode} ({encryption})")
    print(f"  耗时: {elapsed:.2f}s")


def cmd_list(args):
    """列出 .mcpk 文件中的条目。"""
    try:
        password = getattr(args, 'password', None)
        with MCPKReader(args.file, password=password) as reader:
            entries = reader.entries
            if args.type:
                type_map = {
                    "doc": EntryType.DOCUMENT,
                    "image": EntryType.IMAGE,
                    "audio": EntryType.AUDIO,
                    "video": EntryType.VIDEO,
                }
                filter_type = type_map.get(args.type.lower())
                if filter_type:
                    entries = [e for e in entries if e.entry_type == filter_type]

            if args.json:
                info = reader.inspect()
                print(json.dumps(info, ensure_ascii=False, indent=2))
            else:
                print(f"文件: {reader.file_path}")
                print(f"版本: v{reader.version}")
                if reader.is_encrypted:
                    enc_info = f"{reader.encryption_params.encrypt_mode}"
                    if hasattr(reader.encryption_params, 'kdf_type'):
                        from .constants import KdfType
                        enc_info += f" ({KdfType(reader.encryption_params.kdf_type).name})"
                    print(f"加密: {enc_info}")
                print(f"条目数: {len(entries)}")
                if reader.version >= 2:
                    print(f"分组数: {len(reader.groups)}")
                print()
                print(f"{'类型':<6} {'大小':>10} {'压缩后':>10} {'压缩':>6} {'分组':>4} {'MIME':<30} {'名称'}")
                print("-" * 95)
                for e in entries:
                    type_name = {0x01: "DOC", 0x02: "IMG", 0x03: "AUD", 0x04: "VID"}.get(e.entry_type, "???")
                    comp_name = {0x00: "-", 0x01: "zlib", 0x02: "zstd", 0x03: "lz4"}.get(e.compression, "?")
                    group_str = str(e.group_id) if e.group_id != 0xFF else "-"
                    print(
                        f"{type_name:<6} {_fmt_size(e.original_size):>10} "
                        f"{_fmt_size(e.stored_size):>10} {comp_name:>6} "
                        f"{group_str:>4} {e.mime_type:<30} {e.name}"
                    )
    except MCPKError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_groups(args):
    """列出 .mcpk 文件中的分组、标签和关系。"""
    try:
        password = getattr(args, 'password', None)
        with MCPKReader(args.file, password=password) as reader:
            if reader.version < 2:
                print("该文件是 v1 格式，不支持分组功能。")
                return

            if not reader.groups:
                print("文件中没有分组。")
                return

            print(f"文件: {reader.file_path}")
            print(f"分组数: {len(reader.groups)}")
            print()

            for group in reader.groups:
                type_name = {
                    0x00: "GENERIC", 0x01: "VIDEO_SUB",
                    0x02: "DOC_SET", 0x03: "MEDIA",
                    0x04: "COURSE", 0x05: "MEETING",
                }.get(group.group_type, "???")
                print(f"  [{type_name}] {group.name} (ID={group.group_id}, {len(group.entry_ids)} 条目)")

                # 展示标签
                if group.tags:
                    print(f"    标签: {', '.join(group.tags)}")

                # 展示条目（含组内关系标注）
                intra_src_map = {}
                for ir in group.intra_relations:
                    intra_src_map.setdefault(ir.source_entry, []).append(ir)

                for idx, eid in enumerate(group.entry_ids):
                    if eid < len(reader.entries):
                        e = reader.entries[eid]
                        type_tag = {0x01: "DOC", 0x02: "IMG", 0x03: "AUD", 0x04: "VID"}.get(e.entry_type, "???")
                        line = f"    [{type_tag}] {e.name} ({_fmt_size(e.original_size)})"

                        # 检查是否有组内关系
                        if eid in intra_src_map:
                            for ir in intra_src_map[eid]:
                                tgt_name = reader.entries[ir.target_entry].name if ir.target_entry < len(reader.entries) else "?"
                                try:
                                    rt_name = IntraRelationType(ir.relation_type).name
                                except ValueError:
                                    rt_name = f"0x{ir.relation_type:02x}"
                                line += f"  --[{rt_name}]--> {tgt_name}"

                        print(line)

                meta = group.metadata_dict()
                if meta:
                    print(f"    元数据: {json.dumps(meta, ensure_ascii=False)}")
                print()

            if reader.relations:
                print("组间关系:")
                for rel in reader.relations:
                    type_name = {
                        0x00: "SEQUEL", 0x01: "RELATED",
                        0x02: "DEPENDS", 0x03: "VARIANT",
                        0x04: "REFS",
                    }.get(rel.relation_type, "???")
                    src = next((g.name for g in reader.groups if g.group_id == rel.source_group), f"?{rel.source_group}")
                    tgt = next((g.name for g in reader.groups if g.group_id == rel.target_group), f"?{rel.target_group}")
                    desc = f" ({rel.description})" if rel.description else ""
                    print(f"  {src} --[{type_name}]--> {tgt}{desc}")

    except MCPKError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_extract(args):
    """从 .mcpk 提取文件。"""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        password = getattr(args, 'password', None)
        with MCPKReader(args.file, password=password) as reader:
            # 提取指定分组
            if hasattr(args, 'group') and args.group:
                if reader.version < 2:
                    print("该文件是 v1 格式，不支持按分组提取。", file=sys.stderr)
                    sys.exit(1)
                try:
                    paths = reader.extract_group(args.group, output_dir)
                    print(f"已提取分组 '{args.group}' 的 {len(paths)} 个文件到 {output_dir}")
                except KeyError:
                    print(f"错误: 分组不存在: {args.group}", file=sys.stderr)
                    sys.exit(1)
            elif args.name:
                # 提取单个文件
                try:
                    path = reader.extract_to(args.name, output_dir)
                    print(f"已提取: {path}")
                except KeyError:
                    print(f"错误: 文件不存在: {args.name}", file=sys.stderr)
                    sys.exit(1)
            else:
                # 提取全部
                paths = reader.extract_all(output_dir)
                for p in paths:
                    print(f"  {p}")
                print(f"\n已提取 {len(paths)} 个文件到 {output_dir}")
    except MCPKError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_inspect(args):
    """检查 .mcpk 文件的详细信息。"""
    try:
        password = getattr(args, 'password', None)
        with MCPKReader(args.file, password=password) as reader:
            info = reader.inspect()
            print(json.dumps(info, ensure_ascii=False, indent=2))
    except MCPKError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_verify(args):
    """验证 .mcpk 文件的完整性。"""
    try:
        password = getattr(args, 'password', None)
        with MCPKReader(args.file, password=password) as reader:
            errors = reader.verify()
            if errors:
                print(f"验证失败，发现 {len(errors)} 个错误:")
                for err in errors:
                    print(f"  - {err}")
                sys.exit(1)
            else:
                print(f"验证通过: {reader.file_path}")
                print(f"  版本: v{reader.version}")
                print(f"  条目数: {reader.entry_count}")
                if reader.version >= 2:
                    print(f"  分组数: {len(reader.groups)}")
                print(f"  所有 CRC32 校验正确")
    except MCPKError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def _fmt_size(n: int) -> str:
    """格式化文件大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main():
    parser = argparse.ArgumentParser(
        prog="mcpk",
        description="MCPK v2 (MeCapsule Package) 读写工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # pack
    p_pack = subparsers.add_parser("pack", help="打包文件/目录为 .mcpk")
    p_pack.add_argument("sources", nargs="*", help="源文件或目录")
    p_pack.add_argument("-o", "--output", required=True, help="输出 .mcpk 文件路径")
    p_pack.add_argument("--prefix", help="包内路径前缀")
    p_pack.add_argument("--group", help="将所有文件归入指定分组")
    p_pack.add_argument("--auto-group", action="store_true",
                        help="每个顶级目录自动创建同名分组")
    p_pack.add_argument("--index", help="JSON 索引文件路径")
    p_pack.add_argument("--base-dir", dest="base_dir", default=".",
                        help="索引文件中路径的基准目录 (默认: 当前目录)")
    p_pack.add_argument("--password", "-p", help="加密密码（不指定则不加密）")
    p_pack.add_argument("--encrypt-mode", dest="encrypt_mode", default="full",
                        choices=["full", "metadata_only", "data_only"],
                        help="加密模式 (默认: full)")
    p_pack.add_argument("--encryption", default="xor",
                        choices=["aes", "xor"],
                        help="加密算法 (默认: xor, 零依赖)")
    p_pack.set_defaults(func=cmd_pack)

    # list
    p_list = subparsers.add_parser("list", help="列出 .mcpk 中的条目")
    p_list.add_argument("file", help=".mcpk 文件路径")
    p_list.add_argument("--type", choices=["doc", "image", "audio", "video"], help="按类型过滤")
    p_list.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_list.add_argument("--password", "-p", help="解密密码（加密文件必需）")
    p_list.set_defaults(func=cmd_list)

    # groups
    p_groups = subparsers.add_parser("groups", help="列出分组、标签和关系")
    p_groups.add_argument("file", help=".mcpk 文件路径")
    p_groups.add_argument("--password", "-p", help="解密密码")
    p_groups.set_defaults(func=cmd_groups)

    # extract
    p_extract = subparsers.add_parser("extract", help="提取 .mcpk 中的文件")
    p_extract.add_argument("file", help=".mcpk 文件路径")
    p_extract.add_argument("-o", "--output-dir", default=".", help="输出目录")
    p_extract.add_argument("-n", "--name", help="提取指定文件名（不指定则提取全部）")
    p_extract.add_argument("-g", "--group", help="提取指定分组的所有文件")
    p_extract.add_argument("--password", "-p", help="解密密码")
    p_extract.set_defaults(func=cmd_extract)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="检查 .mcpk 文件详情")
    p_inspect.add_argument("file", help=".mcpk 文件路径")
    p_inspect.add_argument("--password", "-p", help="解密密码")
    p_inspect.set_defaults(func=cmd_inspect)

    # verify
    p_verify = subparsers.add_parser("verify", help="验证 .mcpk 文件完整性")
    p_verify.add_argument("file", help=".mcpk 文件路径")
    p_verify.add_argument("--password", "-p", help="解密密码")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # pack 命令：非 index 模式下需要 sources
    if args.command == "pack" and not args.index and not args.sources:
        p_pack.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
