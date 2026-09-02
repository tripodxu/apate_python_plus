"""DeveloperWindow（ui_dev）与 AdminWindow（admin_ui）的公共基类。

只收敛两窗口完全一致的机械逻辑（队列装载、文件对话框、异步任务、启动确认）；
文案与控件差异通过类属性 / 钩子方法注入，保证重构前后每个用户可见字符串
与交互行为逐字不变。子类必须实现：cb_log / cb_progress / set_ui_busy /
refresh_target_list / refresh_mask_list / rename_checkbox / mapping_checkbox。
"""
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QFileDialog, QMessageBox, QListWidgetItem,
)

from .core import collect_files_from_paths, format_file_size
from .ui import EngineWorker


class EngineWindowBase(QWidget):
    # ── 子类可覆盖的差异项（默认值为开发者窗口的文案）──
    WINDOW_FLAGS = Qt.FramelessWindowHint
    ITEM_TEXT_TMPL = "{name}    [{size}]"
    TARGET_DIALOG_TITLE = "选择目标文件"
    TARGET_DIR_DIALOG_TITLE = "选择目标文件夹"
    TARGET_FILE_FILTER = ""
    MASK_DIALOG_TITLE = "选择面具文件"
    MASK_DIR_DIALOG_TITLE = "选择面具文件夹"
    MASK_FILE_FILTER = ""
    MSG_TARGET_ADDED = "目标装载: +{added} 项"
    MSG_MASK_ADDED = "面具库扩充: +{added} 项"
    MSG_EMPTY_QUEUE = "中断: 目标队列为空"
    MSG_ERROR = "[ERROR] 内核异常: {err}"
    TOGGLE_TEXT = "即将对 {count} 个文件执行自动伪装/还原操作。\n\n确定继续吗？"

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.current_worker = None
        self.setWindowFlags(self.WINDOW_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1280, 860)

    # ── 控件工厂 ──
    @staticmethod
    def make_label(text, obj_name="subText"):
        lbl = QLabel(text)
        lbl.setObjectName(obj_name)
        return lbl

    @staticmethod
    def make_btn(text, role="default"):
        btn = QPushButton(text)
        btn.setProperty("role", role)
        return btn

    # ── 列表条目：显示「文件名 + 大小」，真实路径存 UserRole，悬停显示完整路径 ──
    def _make_file_item(self, filepath):
        try:
            size_str = format_file_size(Path(filepath).stat().st_size)
        except Exception:
            size_str = "?"
        item = QListWidgetItem(self.ITEM_TEXT_TMPL.format(name=Path(filepath).name, size=size_str))
        item.setData(Qt.UserRole, filepath)
        item.setToolTip(str(filepath))
        return item

    # ── 队列装载（结果与旧实现等价：按 collect 顺序去重追加）──
    def ui_add_target_paths(self, paths):
        added = 0
        for f in collect_files_from_paths(paths):
            if f not in self.engine.target_files:
                self.engine.target_files.append(f)
                added += 1
        self.refresh_target_list()
        self.cb_log(self.MSG_TARGET_ADDED.format(added=added))

    def ui_add_mask_paths(self, paths):
        added = 0
        for f in collect_files_from_paths(paths):
            if f not in self.engine.mask_library:
                self.engine.mask_library.append(f)
                added += 1
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log(self.MSG_MASK_ADDED.format(added=added))

    # ── 文件对话框 ──
    def ui_select_targets(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.TARGET_DIALOG_TITLE, "", self.TARGET_FILE_FILTER)
        if paths:
            self.ui_add_target_paths(paths)

    def ui_select_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.TARGET_DIR_DIALOG_TITLE)
        if folder:
            self.ui_add_target_paths([folder])

    def ui_select_masks(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.MASK_DIALOG_TITLE, "", self.MASK_FILE_FILTER)
        if paths:
            self.ui_add_mask_paths(paths)

    def ui_select_mask_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.MASK_DIR_DIALOG_TITLE)
        if folder:
            self.ui_add_mask_paths([folder])

    # ── 异步任务 ──
    def _run_task(self, task_fn, done_cb):
        self.set_ui_busy(True)
        self.current_worker = EngineWorker(task_fn)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(done_cb)
        self.current_worker.err_sig.connect(self._on_task_error)
        self.current_worker.start()

    def _on_task_error(self, err_msg):
        self.set_ui_busy(False)
        self.cb_log(self.MSG_ERROR.format(err=err_msg))

    # ── 引擎启动前的确认与映射准备 ──
    def prepare_toggle(self):
        if not self.engine.target_files:
            self.cb_log(self.MSG_EMPTY_QUEUE)
            return False
        reply = QMessageBox.question(
            self, "确认执行",
            self.TOGGLE_TEXT.format(count=len(self.engine.target_files)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False
        self.engine.rename_mapping = self.rename_checkbox().isChecked()
        self.engine.disguise_mapping_txt = self.mapping_checkbox().isChecked()
        if self.engine.rename_mapping:
            mapping_dir = self.engine.get_common_target_parent_dir()
            self.engine.mapping_output_path = str(mapping_dir / "mapping.txt")
        else:
            self.engine.mapping_output_path = None
        return True

    def rename_checkbox(self):
        raise NotImplementedError

    def mapping_checkbox(self):
        raise NotImplementedError

    # ── 子类必须实现的接口 ──
    def cb_log(self, text):
        raise NotImplementedError

    def cb_progress(self, curr, total, title, detail):
        raise NotImplementedError

    def set_ui_busy(self, busy):
        raise NotImplementedError

    def refresh_target_list(self):
        raise NotImplementedError

    def refresh_mask_list(self):
        raise NotImplementedError
