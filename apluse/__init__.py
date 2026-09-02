"""APLUSE ENGINE - 文件伪装/还原工具包。

公共 API 快捷导入：
    from apluse import DisguiseEngine, PathManager
"""

from .core import (
    APP_VERSION,
    DisguiseEngine,
    DisguiseError,
    PathManager,
    collect_files_from_paths,
    disguise_file,
    format_file_size,
    is_disguised_file,
    magic_to_display_text,
    reveal_file,
)
