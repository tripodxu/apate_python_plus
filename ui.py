import sys
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog,
    QTextEdit, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit,
    QListWidget, QListWidgetItem, QFrame, QGridLayout, QProgressBar,
    QStackedWidget, QGraphicsDropShadowEffect
)

from core import (
    DisguiseEngine, DisguiseError, collect_files_from_paths,
    get_app_dir, magic_to_display_text
)


# =================== 异步工作线程 (QThread) ===================

class DetectWorker(QThread):
    log_sig = pyqtSignal(str)
    prog_sig = pyqtSignal(int, int, str, str)
    done_sig = pyqtSignal(int, int, list)
    err_sig = pyqtSignal(str)

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            # 传入 emit 发送信号，传入 lambda: None 替代原来的 processEvents
            o, d, f = self.engine.detect_status(self.prog_sig.emit, self.log_sig.emit, lambda: None)
            self.done_sig.emit(o, d, f)
        except Exception as e:
            self.err_sig.emit(str(e))


class ToggleWorker(QThread):
    log_sig = pyqtSignal(str)
    prog_sig = pyqtSignal(int, int, str, str)
    done_sig = pyqtSignal(int, list)
    err_sig = pyqtSignal(str)

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            s, f = self.engine.handle_toggle(self.prog_sig.emit, self.log_sig.emit, lambda: None)
            self.done_sig.emit(s, f)
        except Exception as e:
            self.err_sig.emit(str(e))


class ExeWorker(QThread):
    log_sig = pyqtSignal(str)
    prog_sig = pyqtSignal(int, int, str, str)
    done_sig = pyqtSignal(str)
    err_sig = pyqtSignal(str)

    def __init__(self, engine, out_dir):
        super().__init__()
        self.engine = engine
        self.out_dir = out_dir

    def run(self):
        try:
            exe_path = self.engine.generate_restore_exe(self.out_dir, self.log_sig.emit, lambda: None)
            self.done_sig.emit(str(exe_path))
        except Exception as e:
            self.err_sig.emit(str(e))


# =================== UI 核心 ===================

def build_shadow(blur: int = 28, offset_y: int = 8, alpha: int = 28):
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(blur)
    effect.setOffset(0, offset_y)
    effect.setColor(QColor(25, 42, 70, alpha))
    return effect


class SectionCard(QFrame):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.setObjectName("sectionCard")
        self.setGraphicsEffect(build_shadow())
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and [u for u in event.mimeData().urls() if u.isLocalFile()]:
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()
        else:
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
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return event.ignore()
        if self.window_ref:
            if self.drop_type == "target": self.window_ref.ui_add_target_paths(paths)
            elif self.drop_type == "mask": self.window_ref.ui_add_mask_paths(paths)
        event.acceptProposedAction()


class FileDropLineEdit(QLineEdit):
    def __init__(self, drop_type: str, parent=None):
        super().__init__(parent)
        self.drop_type = drop_type
        self.window_ref = None
        self.setAcceptDrops(True)
        self.setReadOnly(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and [u for u in event.mimeData().urls() if u.isLocalFile()]:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths and self.window_ref and self.drop_type == "mask":
            self.window_ref.ui_add_mask_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = DisguiseEngine()
        self.current_worker = None  # 保持对当前线程的引用，防止被垃圾回收
        self.init_ui()
        self.refresh_mask_list()
        self.refresh_magic_ui()

    def init_ui(self):
        self.setWindowTitle("文件伪装 / 还原工具 v3.1 ")
        self.resize(1320, 940)
        self.apply_styles()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # ====== 顶部 Header ======
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        header_card.setGraphicsEffect(build_shadow(42, 12, 40))
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(10)

        title = QLabel("文件伪装 / 还原工具 v3.1 ")
        title.setObjectName("mainTitle")
        
        subtitle = QLabel("支持批量目标文件、面具文件库、随机面具伪装、配置持久化、自定义魔术字、生成匹配当前魔术字的恢复 EXE")
        subtitle.setObjectName("mainSubtitle")
        subtitle.setWordWrap(True)

        self.status_label = QLabel(f"程序目录：{get_app_dir()}")
        self.status_label.setObjectName("statusInfo")
        self.status_label.setWordWrap(True)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(10)
        self.target_stat = self.make_stat_chip("🎯 目标文件", "0")
        self.mask_stat = self.make_stat_chip("🎭 面具文件", "0")
        self.mode_stat = self.make_stat_chip("⚙️ 模式", "伪装 / 还原")
        stat_row.addWidget(self.target_stat)
        stat_row.addWidget(self.mask_stat)
        stat_row.addWidget(self.mode_stat)
        stat_row.addStretch(1)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.addWidget(self.status_label)
        header_layout.addLayout(stat_row)
        root.addWidget(header_card)

        # ====== 主体内容 ======
        body = QHBoxLayout()
        body.setSpacing(16)

        # 侧边栏
        sidebar = QFrame()
        sidebar.setObjectName("sidebarCard")
        sidebar.setFixedWidth(264)
        sidebar.setGraphicsEffect(build_shadow(36, 8, 24))
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 18, 16, 18)
        side.setSpacing(10)
        
        nav_title = QLabel("导航")
        nav_title.setObjectName("sidebarTitle")
        
        nav_tip = QLabel("切换不同功能模块 / 在日志中查看详细处理记录")
        nav_tip.setObjectName("sectionSubtitle")
        nav_tip.setWordWrap(True)

        self.nav_magic = self.make_nav_button("🔑 魔术字设置")
        self.nav_action = self.make_nav_button("⚡ 伪装 / 还原")
        self.nav_log = self.make_nav_button("📝 运行日志")
        self.nav_magic.clicked.connect(lambda: self.switch_module(0))
        self.nav_action.clicked.connect(lambda: self.switch_module(1))
        self.nav_log.clicked.connect(lambda: self.switch_module(2))
        
        side.addWidget(nav_title)
        side.addWidget(nav_tip)
        side.addSpacing(8)
        side.addWidget(self.nav_magic)
        side.addWidget(self.nav_action)
        side.addWidget(self.nav_log)
        side.addStretch(1)
        
        side_hint = QLabel("💡 建议先设置魔术字，再添加目标文件和面具文件后执行操作")
        side_hint.setObjectName("sidebarHint")
        side_hint.setWordWrap(True)
        side.addWidget(side_hint)
        body.addWidget(sidebar)

        # 右侧堆叠界面
        self.content_stack = QStackedWidget()
        body.addWidget(self.content_stack, 1)

        # ====== 1. 魔术字页面 ======
        magic_page = QWidget()
        magic_layout = QVBoxLayout(magic_page)
        magic_layout.setContentsMargins(0, 0, 0, 0)
        
        magic_card = SectionCard("魔术字设置", "用于识别当前伪装文件的尾部标记，可自定义、随机生成或恢复默认值")
        magic_row = QHBoxLayout()
        magic_row.setSpacing(10)
        self.magic_edit = QLineEdit()
        self.magic_edit.setObjectName("infoLine")
        self.magic_edit.setPlaceholderText("请输入魔术字，支持 ASCII，如 DGSK；也支持 HEX，如 44 47 53 4B")
        
        self.btn_apply = self.make_button("💾 应用魔术字", accent=True)
        self.btn_apply.setToolTip("保存并应用左侧文本框中的魔术字")
        self.btn_apply.clicked.connect(self.ui_apply_magic)
        
        self.btn_rand = self.make_button("🎲 随机生成", secondary=True)
        self.btn_rand.clicked.connect(self.ui_rand_magic)
        
        self.btn_reset = self.make_button("🔄 恢复默认", danger=True)
        self.btn_reset.clicked.connect(self.ui_reset_magic)
        
        magic_row.addWidget(self.magic_edit, 1)
        magic_row.addWidget(self.btn_apply)
        magic_row.addWidget(self.btn_rand)
        magic_row.addWidget(self.btn_reset)
        
        self.magic_info_label = QLabel("")
        self.magic_info_label.setObjectName("sectionSubtitle")
        self.magic_info_label.setWordWrap(True)
        
        magic_hint = QLabel("HEX 输入支持带或不带 0x 前缀；普通文本按 UTF-8 编码处理，长度需在 1 到 32 字节之间")
        magic_hint.setObjectName("sectionSubtitle")
        magic_hint.setWordWrap(True)
        
        magic_card.body_layout.addLayout(magic_row)
        magic_card.body_layout.addWidget(self.magic_info_label)
        magic_card.body_layout.addWidget(magic_hint)
        magic_layout.addWidget(magic_card)
        magic_layout.addStretch(1)
        self.content_stack.addWidget(magic_page)

        # ====== 2. 操作页面 ======
        action_page = QWidget()
        action_root = QVBoxLayout(action_page)
        action_root.setContentsMargins(0, 0, 0, 0)
        action_cols = QHBoxLayout()
        action_cols.setSpacing(14)
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        left_col.setSpacing(14)
        right_col.setSpacing(14)
        
        # 目标文件框
        self.target_drop = DropLabel("📥 拖拽目标文件或文件夹到这里\n支持批量添加", "target")
        self.target_drop.window_ref = self
        
        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.target_list.setAlternatingRowColors(True)
        self.target_list.setObjectName("fileList")
        
        target_card = SectionCard("🎯 目标文件", "可添加多个文件或整个目录，目录会自动递归收集其中所有文件")
        target_card.body_layout.addWidget(self.target_drop)
        target_card.body_layout.addWidget(self.target_list)
        
        t_grid = QGridLayout()
        t_grid.setHorizontalSpacing(10)
        t_grid.setVerticalSpacing(10)
        self.btn_t_add = self.make_button("📂 选择文件"); self.btn_t_add.clicked.connect(self.ui_select_targets)
        self.btn_t_rm = self.make_button("➖ 移除选中", secondary=True); self.btn_t_rm.clicked.connect(self.ui_rm_targets)
        self.btn_t_clr = self.make_button("🗑️ 清空列表", danger=True); self.btn_t_clr.clicked.connect(self.ui_clr_targets)
        self.btn_detect = self.make_button("🔍 扫描状态", secondary=True); self.btn_detect.clicked.connect(self.ui_detect)
        self.btn_exe = self.make_button("📦 生成专属恢复 EXE", accent=True)
        self.btn_exe.setToolTip("为当前绑定的魔术字生成一个独立运行的恢复程序")
        self.btn_exe.clicked.connect(self.ui_gen_exe)
        
        t_grid.addWidget(self.btn_t_add, 0, 0)
        t_grid.addWidget(self.btn_t_rm, 0, 1)
        t_grid.addWidget(self.btn_t_clr, 1, 0)
        t_grid.addWidget(self.btn_detect, 1, 1)
        t_grid.addWidget(self.btn_exe, 2, 0, 1, 2)
        target_card.body_layout.addLayout(t_grid)
        left_col.addWidget(target_card)

        # 进度框
        prog_card = SectionCard("📊 处理进度", "显示当前批处理任务的执行进度和阶段说明")
        self.progress_label = QLabel("等待开始任务")
        self.progress_label.setObjectName("progressText")
        self.progress_detail = QLabel("尚未执行")
        self.progress_detail.setObjectName("sectionSubtitle")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        prog_card.body_layout.addWidget(self.progress_label)
        prog_card.body_layout.addWidget(self.progress_bar)
        prog_card.body_layout.addWidget(self.progress_detail)
        left_col.addWidget(prog_card)

        # 面具文件框
        self.mask_drop = DropLabel("🎭 拖拽面具文件或文件夹到这里\n可作为伪装外观文件库", "mask")
        self.mask_drop.window_ref = self
        self.mask_edit = FileDropLineEdit("mask")
        self.mask_edit.window_ref = self
        self.mask_edit.setObjectName("infoLine")
        self.mask_edit.setPlaceholderText("显示当前已加载的面具文件数量 / 支持拖拽添加")
        
        self.mask_list = QListWidget()
        self.mask_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.mask_list.setAlternatingRowColors(True)
        self.mask_list.setObjectName("fileList")
        
        mask_card = SectionCard("🎭 面具文件库", "伪装时会从面具文件库中随机选择一个文件作为外观来源")
        mask_card.body_layout.addWidget(self.mask_drop)
        mask_card.body_layout.addWidget(self.mask_edit)
        mask_card.body_layout.addWidget(self.mask_list)
        
        m_grid = QGridLayout()
        m_grid.setHorizontalSpacing(10)
        m_grid.setVerticalSpacing(10)
        self.btn_m_add = self.make_button("📂 添加面具"); self.btn_m_add.clicked.connect(self.ui_select_masks)
        self.btn_m_rm = self.make_button("➖ 移除选中", secondary=True); self.btn_m_rm.clicked.connect(self.ui_rm_masks)
        self.btn_m_clr = self.make_button("🗑️ 清空面具库", danger=True); self.btn_m_clr.clicked.connect(self.ui_clr_masks)
        m_grid.addWidget(self.btn_m_add, 0, 0)
        m_grid.addWidget(self.btn_m_rm, 0, 1)
        m_grid.addWidget(self.btn_m_clr, 1, 0, 1, 2)
        mask_card.body_layout.addLayout(m_grid)
        right_col.addWidget(mask_card)

        # 启动操作框
        act_card = SectionCard("⚡ 一键执行", "程序会自动判断：原始文件 -> 执行伪装 | 伪装文件 -> 执行还原")
        self.btn_toggle = self.make_button("🚀 开始 伪装 / 还原 切换", primary=True)
        self.btn_toggle.setMinimumHeight(54)
        self.btn_toggle.clicked.connect(self.ui_toggle)
        act_card.body_layout.addWidget(self.btn_toggle)
        right_col.addWidget(act_card)
        right_col.addStretch(1)

        action_cols.addLayout(left_col, 1)
        action_cols.addLayout(right_col, 1)
        action_root.addLayout(action_cols)
        self.content_stack.addWidget(action_page)

        # ====== 3. 日志页面 ======
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_card = SectionCard("📝 运行日志", "显示每一步处理细节、错误信息，以及 EXE 生成过程中的输出")
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setObjectName("logEdit")
        self.log_edit.setFont(QFont("Consolas", 10))
        log_card.body_layout.addWidget(self.log_edit)
        log_layout.addWidget(log_card)
        self.content_stack.addWidget(log_page)

        root.addLayout(body, 1)
        self.switch_module(1)

    def apply_styles(self):
        # 加入对 disabled 状态的拦截，提供禁用时的视觉反馈
        self.setStyleSheet("""
            QWidget { background: #eef3f9; color: #1f2937; font-size: 14px; font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI"; }
            
            QScrollBar:vertical { border: none; background: #f1f5f9; width: 8px; border-radius: 4px; margin: 0px 0px 0px 0px; }
            QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 4px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #94a3b8; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal { border: none; background: #f1f5f9; height: 8px; border-radius: 4px; margin: 0px 0px 0px 0px; }
            QScrollBar::handle:horizontal { background: #cbd5e1; border-radius: 4px; min-width: 20px; }
            QScrollBar::handle:horizontal:hover { background: #94a3b8; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

            QFrame#headerCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #1b5fcf, stop:0.56 #4382eb, stop:1 #79adff); border-radius: 24px; border: 1px solid rgba(255,255,255,0.20); }
            QLabel#mainTitle { color: white; font-size: 30px; font-weight: 700; background: transparent; }
            QLabel#mainSubtitle, QLabel#statusInfo, QLabel#statLabel, QLabel#statValue, QLabel#sectionTitle, QLabel#sectionSubtitle, QLabel#sidebarTitle, QLabel#sidebarHint, QLabel#progressText { background: transparent; }
            QLabel#mainSubtitle { color: rgba(255,255,255,0.92); font-size: 13px; }
            QLabel#statusInfo { color: rgba(255,255,255,0.92); font-size: 12px; }
            QFrame#statChip { background: rgba(255,255,255,0.17); border-radius: 16px; border: 1px solid rgba(255,255,255,0.22); }
            QLabel#statLabel { color: rgba(255,255,255,0.78); font-size: 12px; }
            QLabel#statValue { color: white; font-size: 18px; font-weight: 700; }
            QFrame#sidebarCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f9fbff, stop:1 #eef4ff); border: 1px solid rgba(191,205,226,0.9); border-radius: 24px; }
            QLabel#sidebarTitle { font-size: 18px; font-weight: 700; color: #0f172a; }
            QLabel#sidebarHint, QLabel#sectionSubtitle { color: #64748b; line-height: 1.5em; }
            QFrame#sectionCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #f9fbff); border: 1px solid rgba(208,218,234,0.95); border-radius: 22px; }
            QLabel#sectionTitle { font-size: 18px; font-weight: 700; color: #0f172a; }
            QLabel#dropZone { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #f8fbff, stop:1 #eef4ff); border: 2px dashed #98b7ff; border-radius: 18px; padding: 26px; font-size: 15px; font-weight: 600; color: #3157c8; min-height: 92px; }
            QLabel#dropZone[dragging="true"] { background: #eaf2ff; border: 2px dashed #4b79ff; color: #2141a6; }
            
            QListWidget#fileList { background: rgba(255,255,255,0.88); alternate-background-color: #f8fafc; border: 1px solid #dbe3f0; border-radius: 16px; padding: 8px; min-height: 200px; outline: none; }
            QListWidget#fileList::item { padding: 8px 10px; border-radius: 8px; margin: 1px 0; }
            QListWidget#fileList::item:hover { background: #f1f5f9; }
            QListWidget#fileList::item:selected { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #dfe8ff, stop:1 #edf3ff); color: #183b9b; font-weight: 600; }
            
            QLineEdit#infoLine { background: rgba(255,255,255,0.94); border: 1px solid #d3dbe8; border-radius: 14px; padding: 11px 14px; color: #334155; }
            QLineEdit#infoLine:focus { border: 1px solid #75a2ff; background: #ffffff; }
            QTextEdit#logEdit { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0f172a, stop:1 #111c34); color: #e2e8f0; border: 1px solid #1e293b; border-radius: 18px; padding: 12px; line-height: 1.4; }
            
            QLabel#progressText { color: #0f172a; font-size: 15px; font-weight: 700; }
            QProgressBar#progressBar { min-height: 18px; background: #e2e8f0; border: none; border-radius: 9px; color: white; text-align: center; font-weight: 700; font-size: 12px;}
            QProgressBar#progressBar::chunk { border-radius: 9px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3b82f6, stop:1 #2563eb); }
            
            QPushButton { border: 1px solid rgba(197,209,226,0.95); border-radius: 14px; padding: 10px 14px; font-weight: 600; min-height: 18px; background: rgba(255,255,255,0.92); transition: background 0.2s; }
            QPushButton[role="default"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #edf4ff); color: #2742b8; }
            QPushButton[role="default"]:hover { background: #e8f0ff; border-color: #a5b4fc; }
            QPushButton[role="secondary"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #f1f5f9); color: #374151; }
            QPushButton[role="secondary"]:hover { background: #e2e8f0; }
            QPushButton[role="accent"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f7f1ff, stop:1 #ebe4ff); color: #5b21b6; border-color: #ddd6fe; }
            QPushButton[role="accent"]:hover { background: #ede9fe; }
            QPushButton[role="danger"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fff6f6, stop:1 #fee7e7); color: #b91c1c; border-color: #fecaca; }
            QPushButton[role="danger"]:hover { background: #fee2e2; }
            QPushButton[role="primary"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3b82f6, stop:1 #2563eb); color: white; font-size: 15px; border: 1px solid rgba(37,99,235,0.9); }
            QPushButton[role="primary"]:hover { background: #1d4ed8; }
            
            /* 禁用状态的按钮样式 */
            QPushButton:disabled { background: #e2e8f0; color: #94a3b8; border: 1px solid #cbd5e1; }
            
            QPushButton[role="nav"] { text-align: left; padding: 14px 16px; border-radius: 18px; background: rgba(255,255,255,0.76); color: #1e3a8a; font-weight: 600; }
            QPushButton[role="nav"]:hover { background: rgba(219,234,254,0.7); }
            QPushButton[role="nav"][active="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #dbeafe, stop:1 #eff6ff); border: 1px solid #bfdbfe; color: #1e40af; }
        """)

    def make_button(self, text, primary=False, secondary=False, danger=False, accent=False):
        btn = QPushButton(text)
        if primary: btn.setProperty("role", "primary")
        elif secondary: btn.setProperty("role", "secondary")
        elif danger: btn.setProperty("role", "danger")
        elif accent: btn.setProperty("role", "accent")
        else: btn.setProperty("role", "default")
        
        btn.setGraphicsEffect(build_shadow(18, 4, 20))
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    def make_nav_button(self, text):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setProperty("role", "nav")
        btn.setProperty("active", False)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    def make_stat_chip(self, label_text: str, value_text: str):
        frame = QFrame()
        frame.setObjectName("statChip")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        
        label = QLabel(label_text)
        label.setObjectName("statLabel")
        value = QLabel(value_text)
        value.setObjectName("statValue")
        
        layout.addWidget(label)
        layout.addWidget(value)
        frame.value_label = value
        return frame

    def switch_module(self, index: int):
        self.content_stack.setCurrentIndex(index)
        labels = ["魔术字设置", "伪装 / 还原", "运行日志"]
        for i, btn in enumerate([self.nav_magic, self.nav_action, self.nav_log]):
            active = (i == index)
            btn.setChecked(active)
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.mode_stat.value_label.setText(labels[index])

    def set_ui_busy(self, busy: bool):
        """全局锁定/解锁控制，防重入与误触"""
        controls = [
            self.btn_t_add, self.btn_t_rm, self.btn_t_clr, self.btn_detect,
            self.btn_m_add, self.btn_m_rm, self.btn_m_clr, self.btn_exe,
            self.btn_apply, self.btn_rand, self.btn_reset, self.btn_toggle
        ]
        for c in controls:
            c.setEnabled(not busy)
            
        if busy:
            self.btn_toggle.setText("⏳ 任务正在后台安全执行中...")
        else:
            self.btn_toggle.setText("🚀 开始 伪装 / 还原 切换")

    # ======== 槽函数 (跨线程回调) ========
    def cb_log(self, text: str):
        self.log_edit.append(text)
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def cb_progress(self, curr, total, title, detail):
        self.progress_bar.setValue(0 if total <= 0 else int((curr / total) * 100))
        self.progress_label.setText(title)
        self.progress_detail.setText(detail)

    def refresh_status(self):
        self.target_stat.value_label.setText(str(len(self.engine.target_files)))
        self.mask_stat.value_label.setText(str(len(self.engine.mask_library)))

    def refresh_target_list(self):
        self.target_list.clear()
        self.target_list.addItems(self.engine.target_files)
        self.target_drop.setText(f"📥 已添加目标文件 {len(self.engine.target_files)} 个\n继续拖拽可追加")
        self.refresh_status()

    def refresh_mask_list(self):
        self.mask_list.clear()
        self.mask_list.addItems(self.engine.mask_library)
        self.mask_drop.setText(f"🎭 已添加面具文件 {len(self.engine.mask_library)} 个\n继续拖拽可追加到文件库")
        self.mask_edit.setText(f"当前共有 {len(self.engine.mask_library)} 个面具文件")
        self.refresh_status()

    def refresh_magic_ui(self):
        m = self.engine.get_magic_bytes()
        self.magic_edit.setText(m.hex().upper())
        self.magic_info_label.setText(f"当前魔术字：{magic_to_display_text(m)}")

    # ======== UI 交互事件 ========
    def ui_apply_magic(self):
        try:
            magic = self.engine.parse_and_set_magic(self.magic_edit.text())
            self.refresh_magic_ui()
            self.cb_log(f"已应用新的魔术字：{magic_to_display_text(magic)}")
            QMessageBox.information(self, "提示", "魔术字已保存并生效")
        except Exception as e:
            QMessageBox.warning(self, "警告", f"应用魔术字失败：{e}")

    def ui_rand_magic(self):
        try:
            magic = self.engine.generate_random_magic()
            self.refresh_magic_ui()
            self.cb_log(f"已随机生成魔术字：{magic_to_display_text(magic)}")
            QMessageBox.information(self, "提示", "已生成新的随机魔术字")
        except Exception as e:
            QMessageBox.warning(self, "警告", f"随机生成失败：{e}")

    def ui_reset_magic(self):
        magic = self.engine.reset_magic()
        self.refresh_magic_ui()
        self.cb_log(f"已恢复默认魔术字：{magic_to_display_text(magic)}")
        QMessageBox.information(self, "提示", "默认魔术字已恢复")

    def ui_add_target_paths(self, paths):
        added = 0
        for f in collect_files_from_paths(paths):
            if f not in self.engine.target_files:
                self.engine.target_files.append(f)
                added += 1
        self.refresh_target_list()
        self.cb_log(f"已添加 {added} 个目标文件，当前共 {len(self.engine.target_files)} 个")

    def ui_select_targets(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择目标文件")
        if paths:
            self.ui_add_target_paths(paths)

    def ui_rm_targets(self):
        selected_items = self.target_list.selectedItems()
        if not selected_items:
            return QMessageBox.information(self, "提示", "请先选择要移除的目标文件")
        sels = {i.text() for i in selected_items}
        self.engine.target_files = [p for p in self.engine.target_files if p not in sels]
        self.refresh_target_list()
        self.cb_log(f"已移除 {len(sels)} 个目标文件")

    def ui_clr_targets(self):
        self.engine.target_files.clear()
        self.refresh_target_list()
        self.cb_progress(0, 0, "等待开始任务", "尚未执行")
        self.cb_log("已清空目标文件列表")

    def ui_add_mask_paths(self, paths):
        added = 0
        for f in collect_files_from_paths(paths):
            if f not in self.engine.mask_library:
                self.engine.mask_library.append(f)
                added += 1
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log(f"已添加 {added} 个面具文件，当前共 {len(self.engine.mask_library)} 个")

    def ui_select_masks(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择面具文件")
        if paths:
            self.ui_add_mask_paths(paths)

    def ui_rm_masks(self):
        selected_items = self.mask_list.selectedItems()
        if not selected_items:
            return QMessageBox.information(self, "提示", "请先选择要移除的面具文件")
        sels = {i.text() for i in selected_items}
        self.engine.mask_library = [p for p in self.engine.mask_library if p not in sels]
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log(f"已移除 {len(sels)} 个面具文件")

    def ui_clr_masks(self):
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空整个面具文件库吗？此操作不会删除磁盘上的原文件。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.engine.mask_library.clear()
            self.engine.save_config()
            self.refresh_mask_list()
            self.cb_log("已清空面具文件库")

    # ======== 异步执行方法 ========
    
    def ui_detect(self):
        if not self.engine.target_files:
            return QMessageBox.warning(self, "警告", "请先添加需要处理的目标文件")
            
        self.switch_module(1)
        self.set_ui_busy(True)
        
        self.current_worker = DetectWorker(self.engine)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(self._on_detect_done)
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_detect_done(self, o, d, f):
        self.set_ui_busy(False)
        self.cb_progress(1, 1, "检测完成", f"原始文件 {o} 个，伪装文件 {d} 个，失败 {len(f)} 个")
        msg = f"检测完成\n原始文件 {o} 个\n伪装文件 {d} 个"
        if f: msg += f"\n失败 {len(f)} 个"
        QMessageBox.information(self, "检测结果", msg)
        if f:
            self.cb_log("以下文件检测失败：")
            for line in f: self.cb_log(line)

    def ui_toggle(self):
        if not self.engine.target_files:
            return QMessageBox.warning(self, "警告", "请先添加需要处理的目标文件")
            
        self.switch_module(1)
        self.set_ui_busy(True)
        
        self.current_worker = ToggleWorker(self.engine)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(self._on_toggle_done)
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_toggle_done(self, s, f):
        self.set_ui_busy(False)
        self.refresh_target_list()
        self.cb_progress(1, 1, "批处理完成", f"成功 {s} 个，失败 {len(f)} 个")
        QMessageBox.information(self, "提示", f"处理已结束\n成功 {s} 个\n失败 {len(f)} 个")
        if f:
            self.cb_log("以下文件处理失败：")
            for line in f: self.cb_log(line)

    def ui_gen_exe(self):
        try:
            out_dir = self.engine.get_common_target_parent_dir()
        except Exception as e:
            return QMessageBox.warning(self, "警告", str(e))
            
        self.cb_log(f"准备生成恢复 EXE，输出目录：{out_dir}")
        self.cb_progress(0, 1, "正在生成恢复 EXE...", str(out_dir))
        self.set_ui_busy(True)
        
        self.current_worker = ExeWorker(self.engine, out_dir)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(self._on_exe_done)
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_exe_done(self, exe_path):
        self.set_ui_busy(False)
        out_dir = Path(exe_path).parent
        self.cb_progress(1, 1, "恢复 EXE 已生成", str(out_dir))
        magic = self.engine.get_magic_bytes()
        QMessageBox.information(
            self, "生成成功",
            f"批量恢复 EXE 已生成：\n{exe_path}\n\n"
            f"当前绑定魔术字：{magic.hex().upper()}\n"
            f"输出目录：{out_dir}\n"
            f"规则：目标文件共同最近父目录。"
        )

    def _on_worker_err(self, err_msg):
        self.set_ui_busy(False)
        self.cb_progress(0, 1, "任务失败", "发生异常")
        self.cb_log(f"❌ 发生异常: {err_msg}")
        QMessageBox.critical(self, "错误", f"操作失败: {err_msg}")