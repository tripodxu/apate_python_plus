import os
import sys
import json
import random
import struct
import subprocess
import shutil
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog,
    QTextEdit, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit,
    QListWidget, QListWidgetItem, QFrame, QGridLayout
)

MAGIC = b"DGSK"
CONFIG_FILE_NAME = "mask_config.json"


class DisguiseError(Exception):
    pass


# =================== 路径 / 配置 ===================
def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILE_NAME


def load_config() -> dict:
    config_path = get_config_path()
    if not config_path.exists():
        return {"mask_library": []}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"mask_library": []}
        if "mask_library" not in data or not isinstance(data["mask_library"], list):
            data["mask_library"] = []
        return data
    except Exception:
        return {"mask_library": []}


def save_config(config: dict):
    config_path = get_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# =================== 核心逻辑 ===================
def is_disguised_file(file_path: str) -> bool:
    path = Path(file_path)
    if not path.is_file():
        return False
    try:
        if path.stat().st_size < 9:
            return False
        with open(path, "rb") as f:
            f.seek(-4, 2)
            return f.read(4) == MAGIC
    except Exception:
        return False


def read_mask_file(mask_path: str) -> bytes:
    path = Path(mask_path)
    if not path.is_file():
        raise FileNotFoundError(f"面具文件不存在: {mask_path}")
    with open(path, "rb") as f:
        data = f.read()
    if not data:
        raise DisguiseError("面具文件为空")
    return data


def disguise_file(file_path: str, mask_path: str) -> str:
    file_path = Path(file_path)
    mask_path = Path(mask_path)

    if is_disguised_file(str(file_path)):
        raise DisguiseError("该文件已经是伪装态")

    mask_bytes = read_mask_file(str(mask_path))
    mask_len = len(mask_bytes)
    original_suffix = file_path.suffix.encode("utf-8")
    original_suffix_len = len(original_suffix)
    mask_suffix = mask_path.suffix

    with open(file_path, "r+b") as f:
        original_head = f.read(mask_len)
        f.seek(0)
        f.write(mask_bytes)
        f.seek(0, os.SEEK_END)
        f.write(original_head[::-1])
        f.write(original_suffix)
        f.write(struct.pack("B", original_suffix_len))
        f.write(struct.pack("<I", len(original_head)))
        f.write(MAGIC)

    disguised_path = file_path.with_suffix(mask_suffix)
    os.replace(str(file_path), str(disguised_path))
    return str(disguised_path)


def reveal_file(file_path: str) -> str:
    file_path = Path(file_path)

    if not is_disguised_file(str(file_path)):
        raise DisguiseError("该文件不是本程序伪装的文件")

    with open(file_path, "r+b") as f:
        f.seek(-4, 2)
        magic = f.read(4)
        if magic != MAGIC:
            raise DisguiseError("文件尾标记无效")

        f.seek(-8, 2)
        head_len = struct.unpack("<I", f.read(4))[0]

        f.seek(-9, 2)
        suffix_len = struct.unpack("B", f.read(1))[0]

        suffix_pos = file_path.stat().st_size - 9 - suffix_len
        f.seek(suffix_pos)
        original_suffix = f.read(suffix_len).decode("utf-8")

        head_pos = suffix_pos - head_len
        f.seek(head_pos)
        original_head_reversed = f.read(head_len)
        original_head = original_head_reversed[::-1]

        f.truncate(head_pos)
        f.seek(0)
        f.write(original_head)

    restored_path = file_path.with_suffix(original_suffix)
    os.replace(str(file_path), str(restored_path))
    return str(restored_path)


def collect_files_from_paths(paths):
    results = []
    seen = set()

    for p in paths:
        path = Path(p)
        if not path.exists():
            continue

        if path.is_file():
            s = str(path.resolve())
            if s not in seen:
                seen.add(s)
                results.append(s)

        elif path.is_dir():
            for sub in path.rglob("*"):
                if sub.is_file():
                    s = str(sub.resolve())
                    if s not in seen:
                        seen.add(s)
                        results.append(s)

    return results


# =================== PyInstaller 打包 ===================
def create_restore_exe(py_script_path: str):
    py_script_path = Path(py_script_path)
    app_dir = get_app_dir()
    exe_name = py_script_path.stem + ".exe"
    dist_path = app_dir / exe_name

    subprocess.run([
        "pyinstaller",
        "--onefile",
        "--distpath", str(app_dir),
        "--workpath", str(app_dir / "build"),
        "--specpath", str(app_dir),
        str(py_script_path)
    ], check=True)

    build_dir = app_dir / "build"
    if build_dir.exists() and build_dir.is_dir():
        shutil.rmtree(build_dir, ignore_errors=True)

    pycache_dir = app_dir / "__pycache__"
    if pycache_dir.exists() and pycache_dir.is_dir():
        shutil.rmtree(pycache_dir, ignore_errors=True)

    spec_file = app_dir / f"{py_script_path.stem}.spec"
    if spec_file.exists():
        spec_file.unlink()

    return dist_path


# =================== UI 组件 ===================
class SectionCard(QFrame):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.setObjectName("sectionCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("sectionSubtitle")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)

        self.body_layout = QVBoxLayout()
        self.body_layout.setSpacing(10)
        layout.addLayout(self.body_layout)


class DropLabel(QLabel):
    def __init__(self, title: str, drop_type: str, parent=None):
        super().__init__(parent)
        self.drop_type = drop_type
        self.window_ref = None
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setText(title)
        self.setObjectName("dropZone")
        self._default_text = title

    def set_display_text(self, text: str):
        self.setText(text)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            local_paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if local_paths:
                self.setProperty("dragging", True)
                self.style().unpolish(self)
                self.style().polish(self)
                event.acceptProposedAction()
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

        urls = event.mimeData().urls()
        local_paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if not local_paths:
            event.ignore()
            return

        if self.window_ref:
            if self.drop_type == "target":
                self.window_ref.add_target_paths(local_paths)
            elif self.drop_type == "mask":
                self.window_ref.add_mask_paths(local_paths)

        event.acceptProposedAction()


class FileDropLineEdit(QLineEdit):
    def __init__(self, drop_type: str, parent=None):
        super().__init__(parent)
        self.drop_type = drop_type
        self.window_ref = None
        self.setAcceptDrops(True)
        self.setReadOnly(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            local_paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if local_paths:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        local_paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if not local_paths:
            event.ignore()
            return

        if self.window_ref and self.drop_type == "mask":
            self.window_ref.add_mask_paths(local_paths)

        event.acceptProposedAction()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.target_files = []
        self.mask_library = []
        self.config = load_config()
        self.init_ui()
        self.load_mask_library_from_config()

    def init_ui(self):
        self.setWindowTitle("文件伪装 / 还原工具 v1.0")
        self.resize(1180, 900)
        self.apply_styles()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # 顶部标题
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        header_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1f4fd8,
                    stop:1 #4f46e5
                );
                border-radius: 18px;
            }
        """)

        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(6)

        title = QLabel("文件伪装 / 还原工具 v1.0")
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 28px;
                font-weight: 700;
                background: transparent;
            }
        """)

        subtitle = QLabel("支持批量目标文件、面具文件库、随机面具伪装、配置持久化，以及独立生成批量恢复 EXE")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 230);
                font-size: 13px;
                background: transparent;
            }
        """)

        self.status_label = QLabel(f"程序目录：{get_app_dir()}")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 210);
                font-size: 12px;
                padding-top: 4px;
                background: transparent;
            }
        """)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.addWidget(self.status_label)

        root.addWidget(header_card)

        # 双列区域
        content_layout = QHBoxLayout()
        content_layout.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(14)

        right_col = QVBoxLayout()
        right_col.setSpacing(14)

        # 目标文件区
        self.target_drop = DropLabel(
            "把目标文件或文件夹拖到这里\n支持多文件 / 多文件夹",
            "target"
        )
        self.target_drop.window_ref = self

        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.target_list.setObjectName("fileList")

        target_card = SectionCard(
            "目标文件区",
            "这里放需要伪装或还原的文件。支持拖入多个文件或整个文件夹。"
        )
        target_card.body_layout.addWidget(self.target_drop)
        target_card.body_layout.addWidget(self.target_list)

        target_btn_grid = QGridLayout()
        target_btn_grid.setHorizontalSpacing(10)
        target_btn_grid.setVerticalSpacing(10)

        btn_select_targets = self.make_button("选择目标文件（多选）")
        btn_select_targets.clicked.connect(self.select_target_files)

        btn_select_folder = self.make_button("选择目标文件夹")
        btn_select_folder.clicked.connect(self.select_target_folder)

        btn_remove_selected = self.make_button("移除选中目标", secondary=True)
        btn_remove_selected.clicked.connect(self.remove_selected_targets)

        btn_clear_targets = self.make_button("清空目标列表", danger=True)
        btn_clear_targets.clicked.connect(self.clear_target_files)

        btn_detect = self.make_button("检测当前状态", secondary=True)
        btn_detect.clicked.connect(self.detect_status)

        btn_generate_restore_exe = self.make_button("生成批量恢复 EXE", accent=True)
        btn_generate_restore_exe.clicked.connect(self.handle_generate_restore_exe)

        target_btn_grid.addWidget(btn_select_targets, 0, 0)
        target_btn_grid.addWidget(btn_select_folder, 0, 1)
        target_btn_grid.addWidget(btn_remove_selected, 1, 0)
        target_btn_grid.addWidget(btn_clear_targets, 1, 1)
        target_btn_grid.addWidget(btn_detect, 2, 0)
        target_btn_grid.addWidget(btn_generate_restore_exe, 2, 1)

        target_card.body_layout.addLayout(target_btn_grid)
        left_col.addWidget(target_card)

        # 面具库区
        self.mask_drop = DropLabel(
            "把面具文件或面具文件夹拖到这里\n会自动加入面具库，伪装时随机选取",
            "mask"
        )
        self.mask_drop.window_ref = self

        self.mask_edit = FileDropLineEdit("mask")
        self.mask_edit.window_ref = self
        self.mask_edit.setPlaceholderText("面具库拖拽入口（支持多文件 / 多文件夹）")
        self.mask_edit.setObjectName("infoLine")

        self.mask_list = QListWidget()
        self.mask_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.mask_list.setObjectName("fileList")

        mask_card = SectionCard(
            "面具文件库",
            "面具文件会持久化保存到 config。执行伪装时会随机选中一个面具文件。"
        )
        mask_card.body_layout.addWidget(self.mask_drop)
        mask_card.body_layout.addWidget(self.mask_edit)
        mask_card.body_layout.addWidget(self.mask_list)

        mask_btn_grid = QGridLayout()
        mask_btn_grid.setHorizontalSpacing(10)
        mask_btn_grid.setVerticalSpacing(10)

        btn_add_mask_files = self.make_button("添加面具文件（多选）")
        btn_add_mask_files.clicked.connect(self.select_mask_files)

        btn_add_mask_folder = self.make_button("添加面具文件夹")
        btn_add_mask_folder.clicked.connect(self.select_mask_folder)

        btn_remove_selected_masks = self.make_button("移除选中面具", secondary=True)
        btn_remove_selected_masks.clicked.connect(self.remove_selected_masks)

        btn_clear_masks = self.make_button("清空面具库", danger=True)
        btn_clear_masks.clicked.connect(self.clear_mask_library)

        btn_reload_masks = self.make_button("重新加载面具库", secondary=True)
        btn_reload_masks.clicked.connect(self.load_mask_library_from_config)

        mask_btn_grid.addWidget(btn_add_mask_files, 0, 0)
        mask_btn_grid.addWidget(btn_add_mask_folder, 0, 1)
        mask_btn_grid.addWidget(btn_remove_selected_masks, 1, 0)
        mask_btn_grid.addWidget(btn_clear_masks, 1, 1)
        mask_btn_grid.addWidget(btn_reload_masks, 2, 0, 1, 2)

        mask_card.body_layout.addLayout(mask_btn_grid)
        right_col.addWidget(mask_card)

        content_layout.addLayout(left_col, 1)
        content_layout.addLayout(right_col, 1)
        root.addLayout(content_layout)

        # 操作区
        action_card = SectionCard(
            "执行区",
            "点击下方按钮，根据文件当前状态自动执行批量伪装或批量还原。"
        )

        btn_toggle = self.make_button("一键 Toggle（批量伪装 / 还原）", primary=True)
        btn_toggle.setMinimumHeight(48)
        btn_toggle.clicked.connect(self.handle_toggle)

        action_card.body_layout.addWidget(btn_toggle)
        root.addWidget(action_card)

        # 日志区
        log_card = SectionCard("运行日志", "这里会输出检测、伪装、还原、生成 EXE 等详细过程。")
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setObjectName("logEdit")
        font = QFont("Consolas", 10)
        self.log_edit.setFont(font)
        log_card.body_layout.addWidget(self.log_edit)
        root.addWidget(log_card, 1)

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background: #f4f7fb;
                color: #1f2937;
                font-size: 14px;
                font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI";
            }

            QFrame#headerCard {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1f4fd8,
                    stop:1 #4f46e5
                );
                border-radius: 18px;
            }

            QLabel#mainTitle {
                color: white;
                font-size: 28px;
                font-weight: 700;
            }

            QLabel#mainSubtitle {
                color: rgba(255,255,255,0.92);
                font-size: 13px;
            }

            QLabel#statusInfo {
                color: rgba(255,255,255,0.92);
                font-size: 12px;
                padding-top: 4px;
            }

            QFrame#sectionCard {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 18px;
            }

            QLabel#sectionTitle {
                font-size: 18px;
                font-weight: 700;
                color: #111827;
            }

            QLabel#sectionSubtitle {
                color: #6b7280;
                font-size: 13px;
                line-height: 1.5em;
            }

            QLabel#dropZone {
                background: #f8fbff;
                border: 2px dashed #9db7ff;
                border-radius: 16px;
                padding: 24px;
                font-size: 15px;
                font-weight: 600;
                color: #3157c8;
                min-height: 90px;
            }

            QLabel#dropZone[dragging="true"] {
                background: #eef4ff;
                border: 2px dashed #4f46e5;
                color: #233da8;
            }

            QListWidget#fileList {
                background: #fcfdff;
                border: 1px solid #dbe3f0;
                border-radius: 14px;
                padding: 8px;
                min-height: 200px;
                outline: none;
            }

            QListWidget#fileList::item {
                padding: 8px 10px;
                border-radius: 8px;
                margin: 2px 0;
            }

            QListWidget#fileList::item:selected {
                background: #dfe8ff;
                color: #183b9b;
            }

            QLineEdit#infoLine {
                background: #f9fafb;
                border: 1px solid #d1d5db;
                border-radius: 12px;
                padding: 10px 12px;
                color: #374151;
            }

            QTextEdit#logEdit {
                background: #0f172a;
                color: #d1fae5;
                border: 1px solid #1e293b;
                border-radius: 14px;
                padding: 10px;
            }

            QPushButton {
                border: none;
                border-radius: 12px;
                padding: 10px 14px;
                font-weight: 600;
                min-height: 18px;
            }

            QPushButton[role="default"] {
                background: #edf2ff;
                color: #2742b8;
            }

            QPushButton[role="default"]:hover {
                background: #e2eaff;
            }

            QPushButton[role="secondary"] {
                background: #f3f4f6;
                color: #374151;
            }

            QPushButton[role="secondary"]:hover {
                background: #e5e7eb;
            }

            QPushButton[role="accent"] {
                background: #ede9fe;
                color: #5b21b6;
            }

            QPushButton[role="accent"]:hover {
                background: #ddd6fe;
            }

            QPushButton[role="danger"] {
                background: #fef2f2;
                color: #b91c1c;
            }

            QPushButton[role="danger"]:hover {
                background: #fee2e2;
            }

            QPushButton[role="primary"] {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb,
                    stop:1 #4f46e5
                );
                color: white;
                font-size: 15px;
            }

            QPushButton[role="primary"]:hover {
                background: #1d4ed8;
            }
        """)

    def make_button(self, text, primary=False, secondary=False, danger=False, accent=False):
        btn = QPushButton(text)
        if primary:
            btn.setProperty("role", "primary")
        elif secondary:
            btn.setProperty("role", "secondary")
        elif danger:
            btn.setProperty("role", "danger")
        elif accent:
            btn.setProperty("role", "accent")
        else:
            btn.setProperty("role", "default")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    # =================== 日志 / 刷新 ===================
    def log(self, text: str):
        self.log_edit.append(text)

    def refresh_target_list(self):
        self.target_list.clear()
        for path in self.target_files:
            self.target_list.addItem(QListWidgetItem(path))
        self.target_drop.set_display_text(f"已收集目标文件：{len(self.target_files)} 个\n支持继续拖入文件 / 文件夹")

    def refresh_mask_list(self):
        self.mask_list.clear()
        for path in self.mask_library:
            self.mask_list.addItem(QListWidgetItem(path))

        self.mask_drop.set_display_text(f"面具库文件数量：{len(self.mask_library)} 个\n支持继续拖入多文件 / 多文件夹")
        self.mask_edit.setText(f"当前面具库共 {len(self.mask_library)} 个文件")
        self.persist_mask_library()

    def persist_mask_library(self):
        self.config["mask_library"] = self.mask_library[:]
        save_config(self.config)

    def load_mask_library_from_config(self):
        config = load_config()
        library = config.get("mask_library", [])
        valid_files = []
        seen = set()

        for p in library:
            path = Path(p)
            if path.is_file():
                s = str(path.resolve())
                if s not in seen:
                    seen.add(s)
                    valid_files.append(s)

        self.mask_library = valid_files
        self.config = {"mask_library": self.mask_library[:]}
        save_config(self.config)
        self.refresh_mask_list()
        self.log(f"已加载面具库 {len(self.mask_library)} 个文件")

    # =================== 目标文件操作 ===================
    def add_target_paths(self, paths):
        files = collect_files_from_paths(paths)
        added = 0
        existing = set(self.target_files)

        for f in files:
            if f not in existing:
                self.target_files.append(f)
                existing.add(f)
                added += 1

        self.refresh_target_list()
        self.log(f"新增目标文件 {added} 个，当前共 {len(self.target_files)} 个")

    def replace_target_file(self, old_path: str, new_path: str):
        try:
            idx = self.target_files.index(old_path)
            self.target_files[idx] = str(Path(new_path).resolve())
        except ValueError:
            pass
        self.refresh_target_list()

    def clear_target_files(self):
        self.target_files.clear()
        self.refresh_target_list()
        self.log("已清空目标文件列表")

    def remove_selected_targets(self):
        selected_items = self.target_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请先选择要移除的目标文件")
            return

        selected_paths = {item.text() for item in selected_items}
        self.target_files = [p for p in self.target_files if p not in selected_paths]
        self.refresh_target_list()
        self.log(f"已移除 {len(selected_paths)} 个目标文件")

    def select_target_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择目标文件")
        if paths:
            self.add_target_paths(paths)

    def select_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择目标文件夹")
        if folder:
            self.add_target_paths([folder])

    # =================== 面具库操作 ===================
    def add_mask_paths(self, paths):
        files = collect_files_from_paths(paths)
        added = 0
        existing = set(self.mask_library)

        for f in files:
            if f not in existing:
                self.mask_library.append(f)
                existing.add(f)
                added += 1

        self.refresh_mask_list()
        self.log(f"新增面具文件 {added} 个，当前面具库共 {len(self.mask_library)} 个")

    def remove_selected_masks(self):
        selected_items = self.mask_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请先选择要移除的面具文件")
            return

        selected_paths = {item.text() for item in selected_items}
        self.mask_library = [p for p in self.mask_library if p not in selected_paths]
        self.refresh_mask_list()
        self.log(f"已移除 {len(selected_paths)} 个面具文件")

    def clear_mask_library(self):
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空面具库吗？这会同时更新持久化配置。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.mask_library.clear()
        self.refresh_mask_list()
        self.log("已清空面具库")

    def select_mask_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择面具文件（可多选）")
        if paths:
            self.add_mask_paths(paths)

    def select_mask_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择面具文件夹")
        if folder:
            self.add_mask_paths([folder])

    def get_random_mask_file(self) -> str:
        valid_masks = []
        for p in self.mask_library:
            path = Path(p)
            if path.is_file():
                valid_masks.append(str(path.resolve()))

        self.mask_library = valid_masks
        self.refresh_mask_list()

        if not self.mask_library:
            raise DisguiseError("面具库为空，请先添加面具文件或面具文件夹")

        return random.choice(self.mask_library)

    # =================== 状态检测 ===================
    def detect_status(self):
        if not self.target_files:
            QMessageBox.warning(self, "提示", "请先选择目标文件或文件夹")
            return

        disguised_count = 0
        original_count = 0
        failed = []

        for path in self.target_files:
            try:
                if is_disguised_file(path):
                    disguised_count += 1
                    self.log(f"[伪装态] {path}")
                else:
                    original_count += 1
                    self.log(f"[原始态] {path}")
            except Exception as e:
                failed.append(f"{path} -> {e}")

        msg = f"检测完成：\n原始态 {original_count} 个\n伪装态 {disguised_count} 个"
        if failed:
            msg += f"\n失败 {len(failed)} 个"

        QMessageBox.information(self, "检测结果", msg)

        if failed:
            self.log("以下文件检测失败：")
            for line in failed:
                self.log(line)

    # =================== Toggle ===================
    def handle_toggle(self):
        if not self.target_files:
            QMessageBox.warning(self, "提示", "请先选择目标文件或文件夹")
            return

        need_mask = False
        for path in self.target_files:
            try:
                if not is_disguised_file(path):
                    need_mask = True
                    break
            except Exception:
                pass

        if need_mask and not self.mask_library:
            QMessageBox.warning(self, "提示", "存在原始态文件，请先添加面具文件到面具库")
            return

        success = 0
        failed = []

        for old_path in self.target_files[:]:
            try:
                if is_disguised_file(old_path):
                    self.log(f"识别为伪装态，开始还原：{old_path}")
                    new_path = reveal_file(old_path)
                    self.log(f"还原完成：{new_path}")
                    self.replace_target_file(old_path, new_path)
                else:
                    mask_file = self.get_random_mask_file()
                    self.log(f"识别为原始态，开始伪装：{old_path}")
                    self.log(f"随机选中面具：{mask_file}")
                    new_path = disguise_file(old_path, mask_file)
                    self.log(f"伪装完成：{new_path}")
                    self.replace_target_file(old_path, new_path)

                success += 1
            except Exception as e:
                failed.append(f"{old_path} -> {e}")
                self.log(f"操作失败：{old_path} -> {e}")

        msg = f"批量处理完成：\n成功 {success} 个\n失败 {len(failed)} 个"
        QMessageBox.information(self, "完成", msg)

        if failed:
            self.log("以下文件处理失败：")
            for line in failed:
                self.log(line)

    # =================== 独立生成恢复 EXE ===================
    def handle_generate_restore_exe(self):
        app_dir = get_app_dir()
        try:
            self.create_folder_restore_exe(app_dir)
        except Exception as e:
            self.log(f"生成 exe 失败: {e}")
            QMessageBox.critical(self, "错误", f"生成 exe 失败: {e}")

    def create_folder_restore_exe(self, output_dir: Path):
        py_script_path = output_dir / "restore_all_disguised.py"

        script_content = r'''import sys
import struct
from pathlib import Path

MAGIC = b"DGSK"


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_disguised_file(file_path: Path) -> bool:
    if not file_path.is_file():
        return False
    try:
        if file_path.stat().st_size < 9:
            return False
        with open(file_path, "rb") as f:
            f.seek(-4, 2)
            return f.read(4) == MAGIC
    except Exception:
        return False


def reveal_file(file_path: Path) -> Path:
    with open(file_path, "r+b") as f:
        f.seek(-4, 2)
        magic = f.read(4)
        if magic != MAGIC:
            raise Exception("文件尾标记无效")

        f.seek(-8, 2)
        head_len = struct.unpack("<I", f.read(4))[0]

        f.seek(-9, 2)
        suffix_len = struct.unpack("B", f.read(1))[0]

        suffix_pos = file_path.stat().st_size - 9 - suffix_len
        f.seek(suffix_pos)
        original_suffix = f.read(suffix_len).decode("utf-8")

        head_pos = suffix_pos - head_len
        f.seek(head_pos)
        original_head_reversed = f.read(head_len)
        original_head = original_head_reversed[::-1]

        f.truncate(head_pos)
        f.seek(0)
        f.write(original_head)

    restored_path = file_path.with_suffix(original_suffix)
    file_path.replace(restored_path)
    return restored_path


def main():
    base_dir = get_base_dir()
    print(f"递归扫描目录: {base_dir}")
    print("-" * 60)

    restored = 0
    failed = 0

    for path in base_dir.rglob("*"):
        if not path.is_file():
            continue

        lower_name = path.name.lower()
        if lower_name in {"restore_all_disguised.exe", "restore_all_disguised.py"}:
            continue

        try:
            if is_disguised_file(path):
                new_path = reveal_file(path)
                restored += 1
                print(f"[已恢复] {path} -> {new_path}")
        except Exception as e:
            failed += 1
            print(f"[失败] {path} -> {e}")

    print("-" * 60)
    print(f"完成：恢复 {restored} 个，失败 {failed} 个")
    input("按回车退出...")


if __name__ == "__main__":
    main()
'''

        with open(py_script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        self.log(f"生成批量恢复脚本: {py_script_path}")

        exe_path = create_restore_exe(str(py_script_path))
        self.log(f"生成批量恢复 exe: {exe_path}")

        QMessageBox.information(
            self,
            "生成成功",
            f"批量恢复 EXE 已生成：\n{exe_path}\n\n输出目录固定为程序所在文件夹。"
        )


# =================== 运行 ===================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())