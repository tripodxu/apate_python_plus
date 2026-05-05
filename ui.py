import sys
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QFileDialog,
    QTextEdit, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit,
    QListWidget, QFrame, QGridLayout, QProgressBar,
    QGraphicsDropShadowEffect, QComboBox
)

from core import (
    DisguiseEngine, DisguiseError, collect_files_from_paths,
    PathManager, magic_to_display_text
)
from themes import PALETTES, THEME_NAMES, build_qss, parse_shadow_color


# =================== 通用异步工作线程 ===================

class EngineWorker(QThread):
    """通用引擎工作线程，通过传入 callable 复用于不同任务。"""
    log_sig = pyqtSignal(str)
    prog_sig = pyqtSignal(int, int, str, str)
    done_sig = pyqtSignal(object)
    err_sig = pyqtSignal(str)

    def __init__(self, task_fn, *args):
        super().__init__()
        self.task_fn = task_fn
        self.extra_args = args

    def run(self):
        try:
            result = self.task_fn(
                self.prog_sig.emit,
                self.log_sig.emit,
                *self.extra_args,
            )
            self.done_sig.emit(result)
        except Exception as e:
            self.err_sig.emit(str(e))


# =================== 现代化 UI 组件 ===================

class CustomTitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(48)
        self.setObjectName("titleBar")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)
        
        title_label = QLabel("✨ APLUSE ENGINE v3.3")
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEME_NAMES)
        self.theme_combo.setObjectName("themeCombo")
        self.theme_combo.currentIndexChanged.connect(self.parent.change_theme)
        layout.addWidget(self.theme_combo)
        
        layout.addSpacing(16)
        
        self.btn_min = QPushButton()
        self.btn_min.setObjectName("macMin")
        self.btn_min.clicked.connect(self.parent.showMinimized)
        self.btn_min.setToolTip("最小化")
        
        self.btn_max = QPushButton()
        self.btn_max.setObjectName("macMax")
        self.btn_max.clicked.connect(self.toggle_maximize)
        self.btn_max.setToolTip("最大化/还原")

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("macClose")
        self.btn_close.clicked.connect(self.parent.close)
        self.btn_close.setToolTip("关闭")
        
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent.dragPos = event.globalPos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            if self.parent.isMaximized():
                self.parent.showNormal()
            self.parent.move(self.parent.pos() + event.globalPos() - self.parent.dragPos)
            self.parent.dragPos = event.globalPos()


class CustomDropList(QListWidget):
    def __init__(self, placeholder_text, drop_type, window_ref):
        super().__init__()
        self.placeholder_text = placeholder_text
        self.drop_type = drop_type
        self.window_ref = window_ref
        self.placeholder_color = "#52525B"
        
        self.setAcceptDrops(True)
        self.setObjectName("darkList")
        self.setSelectionMode(QListWidget.ExtendedSelection)
        
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrap(True)

    def set_placeholder_color(self, hex_color):
        self.placeholder_color = hex_color
        self.viewport().update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setProperty("drag", "active")
            self.style().unpolish(self); self.style().polish(self)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("drag", "none")
        self.style().unpolish(self); self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("drag", "none")
        self.style().unpolish(self); self.style().polish(self)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            if self.drop_type == "target": 
                self.window_ref.ui_add_target_paths(paths)
            elif self.drop_type == "mask": 
                self.window_ref.ui_add_mask_paths(paths)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(self.placeholder_color))
            font = self.font()
            font.setPointSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, self.placeholder_text)


# =================== 主窗口 ===================

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = DisguiseEngine()
        self.current_worker = None
        self.current_theme_index = 0
        
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.init_ui()
        
        # 🟢 【核心修改】：从核心配置中读取持久化的主题索引
        saved_theme = self.engine.config.get("theme_index", 0)
        
        self.title_bar.theme_combo.setCurrentIndex(saved_theme)
        self.change_theme(saved_theme)
        
        self.refresh_mask_list()
        self.refresh_magic_ui()

    def init_ui(self):
        self.resize(1280, 860)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.container = QFrame()
        self.container.setObjectName("mainContainer")
        
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setOffset(0, 0)
        self.container.setGraphicsEffect(self.shadow)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        self.title_bar = CustomTitleBar(self)
        container_layout.addWidget(self.title_bar)
        
        dashboard_layout = QVBoxLayout()
        dashboard_layout.setContentsMargins(24, 16, 24, 24)
        dashboard_layout.setSpacing(20)
        
        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        
        magic_card = QFrame()
        magic_card.setObjectName("card")
        m_layout = QVBoxLayout(magic_card)
        m_layout.addWidget(self.make_label("🔑 核心密钥 (MAGIC WORD)", "cardTitle"))
        
        m_input_row = QHBoxLayout()
        self.magic_edit = QLineEdit()
        self.magic_edit.setObjectName("neonInput")
        self.magic_edit.setPlaceholderText("输入 ASCII 或 HEX 密钥...")
        m_input_row.addWidget(self.magic_edit, 1)
        
        btn_apply = self.make_btn("应用", "accent")
        btn_apply.clicked.connect(self.ui_apply_magic)
        btn_rand = self.make_btn("随机", "secondary")
        btn_rand.clicked.connect(self.ui_rand_magic)
        btn_reset = self.make_btn("默认", "danger")
        btn_reset.clicked.connect(self.ui_reset_magic)
        
        m_input_row.addWidget(btn_apply)
        m_input_row.addWidget(btn_rand)
        m_input_row.addWidget(btn_reset)
        m_layout.addLayout(m_input_row)
        
        self.magic_info_label = self.make_label("当前状态：未加载", "subText")
        m_layout.addWidget(self.magic_info_label)
        top_row.addWidget(magic_card, 2)
        
        stat_card = QFrame()
        stat_card.setObjectName("card")
        stat_layout = QVBoxLayout(stat_card)
        stat_layout.addWidget(self.make_label("📡 系统状态", "cardTitle"))
        self.status_label = self.make_label(f"持久化：{PathManager.get_persist_dir()}", "subText")
        self.status_label.setWordWrap(True)
        stat_layout.addWidget(self.status_label)
        stat_layout.addStretch()
        top_row.addWidget(stat_card, 1)
        
        dashboard_layout.addLayout(top_row)
        
        file_row = QHBoxLayout()
        file_row.setSpacing(20)
        
        t_card = QFrame()
        t_card.setObjectName("card")
        t_layout = QVBoxLayout(t_card)
        t_header = QHBoxLayout()
        t_header.addWidget(self.make_label("🎯 目标执行队列", "cardTitle"))
        self.t_count_label = self.make_label("0 项", "badge")
        t_header.addWidget(self.t_count_label)
        t_header.addStretch()
        t_layout.addLayout(t_header)
        
        self.target_list = CustomDropList("📥 拖拽目标文件/文件夹至此", "target", self)
        t_layout.addWidget(self.target_list)
        
        t_btn_row = QHBoxLayout()
        self.btn_t_add = self.make_btn("📂选择文件", "secondary")
        self.btn_t_add.clicked.connect(self.ui_select_targets)
        self.btn_t_rm = self.make_btn("➖移除选中", "secondary")
        self.btn_t_rm.clicked.connect(self.ui_rm_targets)
        self.btn_t_clr = self.make_btn("🗑️清空", "danger")
        self.btn_t_clr.clicked.connect(self.ui_clr_targets)
        t_btn_row.addWidget(self.btn_t_add); t_btn_row.addWidget(self.btn_t_rm); t_btn_row.addWidget(self.btn_t_clr)
        t_layout.addLayout(t_btn_row)
        file_row.addWidget(t_card)
        
        mask_card = QFrame()
        mask_card.setObjectName("card")
        mask_card_layout = QVBoxLayout(mask_card)
        mask_header = QHBoxLayout()
        mask_header.addWidget(self.make_label("🎭 伪装面具文件库", "cardTitle"))
        self.m_count_label = self.make_label("0 项", "badge")
        mask_header.addWidget(self.m_count_label)
        mask_header.addStretch()
        mask_card_layout.addLayout(mask_header)

        self.mask_list = CustomDropList("🖼️ 拖拽面具文件/文件夹至此", "mask", self)
        mask_card_layout.addWidget(self.mask_list)

        mask_btn_row = QHBoxLayout()
        self.btn_m_add = self.make_btn("📂选择面具", "secondary")
        self.btn_m_add.clicked.connect(self.ui_select_masks)
        self.btn_m_rm = self.make_btn("➖移除选中", "secondary")
        self.btn_m_rm.clicked.connect(self.ui_rm_masks)
        self.btn_m_clr = self.make_btn("🗑️清空", "danger")
        self.btn_m_clr.clicked.connect(self.ui_clr_masks)
        mask_btn_row.addWidget(self.btn_m_add)
        mask_btn_row.addWidget(self.btn_m_rm)
        mask_btn_row.addWidget(self.btn_m_clr)
        mask_card_layout.addLayout(mask_btn_row)
        file_row.addWidget(mask_card)
        
        dashboard_layout.addLayout(file_row, 1) 
        
        bot_row = QHBoxLayout()
        bot_row.setSpacing(20)
        
        log_card = QFrame()
        log_card.setObjectName("card")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(10, 10, 10, 10)
        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("terminal")
        self.log_edit.setReadOnly(True)
        self.log_edit.append("> APLUSE ENGINE 初始化成功...")
        log_layout.addWidget(self.log_edit)
        bot_row.addWidget(log_card, 2)
        
        act_card = QFrame()
        act_card.setObjectName("card")
        act_layout = QVBoxLayout(act_card)
        
        self.progress_label = self.make_label("等待任务指令...", "subText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("neonProgress")
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        act_layout.addWidget(self.progress_label)
        act_layout.addWidget(self.progress_bar)
        act_layout.addSpacing(10)
        
        act_btn_grid = QGridLayout()
        act_btn_grid.setSpacing(10)
        self.btn_detect = self.make_btn("🔍 扫描分析队列", "secondary")
        self.btn_detect.clicked.connect(self.ui_detect)
        self.btn_exe = self.make_btn("📦 封装脱壳程序", "secondary")
        self.btn_exe.clicked.connect(self.ui_gen_exe)
        act_btn_grid.addWidget(self.btn_detect, 0, 0)
        act_btn_grid.addWidget(self.btn_exe, 0, 1)
        act_layout.addLayout(act_btn_grid)
        
        self.btn_toggle = self.make_btn("⚡ 引擎启动 (伪装/还原)", "primary")
        self.btn_toggle.setFixedHeight(56)
        self.btn_toggle.clicked.connect(self.ui_toggle)
        act_layout.addWidget(self.btn_toggle)
        
        bot_row.addWidget(act_card, 1)
        dashboard_layout.addLayout(bot_row)
        
        container_layout.addLayout(dashboard_layout)
        main_layout.addWidget(self.container)

    def make_label(self, text, obj_name):
        lbl = QLabel(text)
        lbl.setObjectName(obj_name)
        return lbl

    def make_btn(self, text, role="default"):
        btn = QPushButton(text)
        btn.setProperty("role", role)
        return btn

    def change_theme(self, index):
        self.current_theme_index = index

        # 主题切换时，自动保存索引到 JSON 配置文件
        if hasattr(self, 'engine'):
            self.engine.config["theme_index"] = index
            self.engine.save_config()

        p = PALETTES[index]

        self.target_list.set_placeholder_color(p["TEXT_SUB"])
        self.mask_list.set_placeholder_color(p["TEXT_SUB"])

        shadow_rgba = parse_shadow_color(p["SHADOW"])
        if shadow_rgba:
            self.shadow.setColor(QColor(*shadow_rgba))

        self.setStyleSheet(build_qss(p))


    # ======== UI 交互方法 ========

    def set_ui_busy(self, busy: bool):
        controls = [
            self.btn_t_add, self.btn_t_rm, self.btn_t_clr, self.btn_detect,
            self.btn_m_add, self.btn_m_rm, self.btn_m_clr, self.btn_exe,
            self.magic_edit, self.btn_toggle, self.title_bar.theme_combo
        ]
        for c in controls: c.setEnabled(not busy)
        self.target_list.setEnabled(not busy)
        self.mask_list.setEnabled(not busy)
        
        self.btn_toggle.setText("⚡ 引擎高转速处理中..." if busy else "⚡ 引擎启动 (伪装/还原)")

    def cb_log(self, text: str):
        self.log_edit.append(f"> {text}")
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def cb_progress(self, curr, total, title, detail):
        self.progress_bar.setValue(0 if total <= 0 else int((curr / total) * 100))
        self.progress_label.setText(f"{title} | {detail}")

    def refresh_status(self):
        self.t_count_label.setText(f"{len(self.engine.target_files)} 项")
        self.m_count_label.setText(f"{len(self.engine.mask_library)} 项")

    def refresh_target_list(self):
        self.target_list.clear()
        self.target_list.addItems(self.engine.target_files)
        self.refresh_status()

    def refresh_mask_list(self):
        self.mask_list.clear()
        self.mask_list.addItems(self.engine.mask_library)
        self.refresh_status()

    def refresh_magic_ui(self):
        m = self.engine.get_magic_bytes()
        self.magic_edit.setText(m.hex().upper())
        self.magic_info_label.setText(f"生效指令：{magic_to_display_text(m)}")

    def ui_apply_magic(self):
        try:
            magic = self.engine.parse_and_set_magic(self.magic_edit.text())
            self.refresh_magic_ui()
            self.cb_log(f"已覆写系统密钥：{magic.hex().upper()}")
        except Exception as e:
            QMessageBox.warning(self, "密钥异常", str(e))

    def ui_rand_magic(self):
        try:
            self.engine.generate_random_magic()
            self.refresh_magic_ui()
            self.cb_log("已生成动态安全密钥")
        except Exception as e: QMessageBox.warning(self, "异常", str(e))

    def ui_reset_magic(self):
        self.engine.reset_magic()
        self.refresh_magic_ui()
        self.cb_log("已回退至出厂默认密钥")

    def ui_add_target_paths(self, paths):
        added = 0
        for f in collect_files_from_paths(paths):
            if f not in self.engine.target_files:
                self.engine.target_files.append(f)
                added += 1
        self.refresh_target_list()
        self.cb_log(f"目标装载: +{added} 项")

    def ui_select_targets(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择目标文件")
        if paths: self.ui_add_target_paths(paths)

    def ui_rm_targets(self):
        sels = {i.text() for i in self.target_list.selectedItems()}
        if not sels: return
        self.engine.target_files = [p for p in self.engine.target_files if p not in sels]
        self.refresh_target_list()
        self.cb_log(f"目标释放: -{len(sels)} 项")

    def ui_clr_targets(self):
        self.engine.target_files.clear()
        self.refresh_target_list()
        self.cb_log("目标队列已格式化")

    def ui_add_mask_paths(self, paths):
        added = 0
        for f in collect_files_from_paths(paths):
            if f not in self.engine.mask_library:
                self.engine.mask_library.append(f)
                added += 1
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log(f"面具库扩充: +{added} 项")

    def ui_select_masks(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择面具文件")
        if paths: self.ui_add_mask_paths(paths)

    def ui_rm_masks(self):
        sels = {i.text() for i in self.mask_list.selectedItems()}
        if not sels: return
        self.engine.mask_library = [p for p in self.engine.mask_library if p not in sels]
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log(f"面具库清理: -{len(sels)} 项")

    def ui_clr_masks(self):
        self.engine.mask_library.clear()
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log("外观面具库已格式化")

    def ui_detect(self):
        if not self.engine.target_files:
            return self.cb_log("中断: 目标队列为空")
        self.set_ui_busy(True)
        self.current_worker = EngineWorker(self.engine.detect_status)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(self._on_detect_done)
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_detect_done(self, result):
        self.set_ui_busy(False)
        o, d, f = result
        self.cb_progress(1, 1, "分析完毕", f"原装:{o} | 伪装:{d} | 异常:{len(f)}")
        if f:
            for line in f:
                self.cb_log(f"[WARN] {line}")

    def ui_toggle(self):
        if not self.engine.target_files:
            return self.cb_log("中断: 目标队列为空")
        self.set_ui_busy(True)
        self.current_worker = EngineWorker(self.engine.handle_toggle)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(self._on_toggle_done)
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_toggle_done(self, result):
        self.set_ui_busy(False)
        s, f = result
        self.refresh_target_list()
        self.cb_progress(1, 1, "引擎挂起", f"成功:{s} | 失败:{len(f)}")
        self.cb_log(f"执行周期结束。成功:{s} 失败:{len(f)}")

    def ui_gen_exe(self):
        try:
            out_dir = self.engine.get_common_target_parent_dir()
        except Exception as e:
            return self.cb_log(f"中断: {e}")
        self.set_ui_busy(True)

        # generate_restore_exe 签名为 (output_dir, log_cb, process_events_cb)
        # 用 lambda 适配 EngineWorker 的统一调用格式 (progress_cb, log_cb)
        def exe_task(progress_cb, log_cb):
            return self.engine.generate_restore_exe(out_dir, log_cb)

        self.current_worker = EngineWorker(exe_task)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(self._on_exe_done)
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_exe_done(self, exe_path):
        self.set_ui_busy(False)
        self.cb_progress(1, 1, "编译完成", str(Path(exe_path).parent))
        self.cb_log(f"脱壳包导出成功: {exe_path}")

    def _on_worker_err(self, err_msg):
        self.set_ui_busy(False)
        self.cb_progress(0, 1, "系统崩溃", "ERR_FATAL")
        self.cb_log(f"[ERROR] 内核异常: {err_msg}")