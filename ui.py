import sys
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPoint, QRect
from PyQt5.QtGui import QColor, QFont, QMouseEvent, QIcon, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog,
    QTextEdit, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit,
    QListWidget, QListWidgetItem, QFrame, QGridLayout, QProgressBar,
    QSpacerItem, QSizePolicy, QGraphicsDropShadowEffect, QComboBox
)

from core import (
    DisguiseEngine, DisguiseError, collect_files_from_paths,
    PathManager, magic_to_display_text
)

# =================== 异步工作线程 (完全保持不变) ===================

class DetectWorker(QThread):
    log_sig = pyqtSignal(str)
    prog_sig = pyqtSignal(int, int, str, str)
    done_sig = pyqtSignal(int, int, list)
    err_sig = pyqtSignal(str)
    def __init__(self, engine): super().__init__(); self.engine = engine
    def run(self):
        try:
            o, d, f = self.engine.detect_status(self.prog_sig.emit, self.log_sig.emit, lambda: None)
            self.done_sig.emit(o, d, f)
        except Exception as e: self.err_sig.emit(str(e))

class ToggleWorker(QThread):
    log_sig = pyqtSignal(str)
    prog_sig = pyqtSignal(int, int, str, str)
    done_sig = pyqtSignal(int, list)
    err_sig = pyqtSignal(str)
    def __init__(self, engine): super().__init__(); self.engine = engine
    def run(self):
        try:
            s, f = self.engine.handle_toggle(self.prog_sig.emit, self.log_sig.emit, lambda: None)
            self.done_sig.emit(s, f)
        except Exception as e: self.err_sig.emit(str(e))

class ExeWorker(QThread):
    log_sig = pyqtSignal(str)
    prog_sig = pyqtSignal(int, int, str, str)
    done_sig = pyqtSignal(str)
    err_sig = pyqtSignal(str)
    def __init__(self, engine, out_dir): super().__init__(); self.engine = engine; self.out_dir = out_dir
    def run(self):
        try:
            exe_path = self.engine.generate_restore_exe(self.out_dir, self.log_sig.emit, lambda: None)
            self.done_sig.emit(str(exe_path))
        except Exception as e: self.err_sig.emit(str(e))


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
        self.theme_combo.addItems([
            "🌑 暗色极客", 
            "☀️ 亮色极简", 
            "🌌 渐变幽蓝", 
            "👑 暗金奢华",
            "🌸 猛男猛粉",
            "☢️ 辐射废土",
            "🔮 低调暗紫"
        ])
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
        
        m_card = QFrame()
        m_card.setObjectName("card")
        m_layout = QVBoxLayout(m_card)
        m_header = QHBoxLayout()
        m_header.addWidget(self.make_label("🎭 伪装面具文件库", "cardTitle"))
        self.m_count_label = self.make_label("0 项", "badge")
        m_header.addWidget(self.m_count_label)
        m_header.addStretch()
        m_layout.addLayout(m_header)
        
        self.mask_list = CustomDropList("🖼️ 拖拽面具文件/文件夹至此", "mask", self)
        m_layout.addWidget(self.mask_list)
        
        m_btn_row = QHBoxLayout()
        self.btn_m_add = self.make_btn("📂选择面具", "secondary")
        self.btn_m_add.clicked.connect(self.ui_select_masks)
        self.btn_m_rm = self.make_btn("➖移除选中", "secondary")
        self.btn_m_rm.clicked.connect(self.ui_rm_masks)
        self.btn_m_clr = self.make_btn("🗑️清空", "danger")
        self.btn_m_clr.clicked.connect(self.ui_clr_masks)
        m_btn_row.addWidget(self.btn_m_add); m_btn_row.addWidget(self.btn_m_rm); m_btn_row.addWidget(self.btn_m_clr)
        m_layout.addLayout(m_btn_row)
        file_row.addWidget(m_card)
        
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
        
        # 🟢 【核心修改】：主题切换时，自动保存索引到 JSON 配置文件
        if hasattr(self, 'engine'):
            self.engine.config["theme_index"] = index
            self.engine.save_config()
            
        palettes = [
            { # 0: 🌑 暗色极客 (Zinc Theme)
                "BG_MAIN": "#09090B", "BG_CARD": "#121217", "BORDER": "#27272A", 
                "TEXT_MAIN": "#F4F4F5", "TEXT_SUB": "#A1A1AA", "TEXT_TITLE": "#A1A1AA",
                "BTN_SEC": "#27272A", "BTN_SEC_HOVER": "#3F3F46", "BTN_SEC_TEXT": "#E4E4E7",
                "PRI_START": "#2563EB", "PRI_END": "#6D28D9", "PRI_H_START": "#3B82F6", "PRI_H_END": "#8B5CF6",
                "LIST_BG": "#09090B", "LIST_ITEM": "#18181B", "LIST_HOVER": "#27272A", "LIST_SEL": "#1D4ED8",
                "TERM_BG": "#000000", "TERM_TEXT": "#10B981", "SHADOW": "rgba(0,0,0,150)",
                "DIS_BG": "rgba(255, 255, 255, 0.06)", "DIS_TEXT": "rgba(255, 255, 255, 0.35)",
                "DIS_BORDER": "rgba(255, 255, 255, 0.15)", "DIS_PRI_BG": "rgba(255, 255, 255, 0.12)",
                "INPUT_DIS_BG": "rgba(255, 255, 255, 0.03)"
            },
            { # 1: ☀️ 亮色极简 (Light Theme)
                "BG_MAIN": "#F3F4F6", "BG_CARD": "#FFFFFF", "BORDER": "#D1D5DB", 
                "TEXT_MAIN": "#111827", "TEXT_SUB": "#6B7280", "TEXT_TITLE": "#1F2937",
                "BTN_SEC": "#F3F4F6", "BTN_SEC_HOVER": "#E5E7EB", "BTN_SEC_TEXT": "#374151",
                "PRI_START": "#3B82F6", "PRI_END": "#8B5CF6", "PRI_H_START": "#60A5FA", "PRI_H_END": "#A78BFA",
                "LIST_BG": "#F9FAFB", "LIST_ITEM": "#FFFFFF", "LIST_HOVER": "#F3F4F6", "LIST_SEL": "#3B82F6",
                "TERM_BG": "#F8FAFC", "TERM_TEXT": "#0284C7", "SHADOW": "rgba(0,0,0,30)",
                "DIS_BG": "rgba(0, 0, 0, 0.04)", "DIS_TEXT": "rgba(0, 0, 0, 0.35)",
                "DIS_BORDER": "rgba(0, 0, 0, 0.15)", "DIS_PRI_BG": "rgba(0, 0, 0, 0.08)",
                "INPUT_DIS_BG": "rgba(0, 0, 0, 0.02)"
            },
            { # 2: 🌌 渐变幽蓝 (Cyan/Blue Theme)
                "BG_MAIN": "#0B1120", "BG_CARD": "#1E293B", "BORDER": "#0EA5E9", 
                "TEXT_MAIN": "#F0F9FF", "TEXT_SUB": "#94A3B8", "TEXT_TITLE": "#38BDF8",
                "BTN_SEC": "#0F172A", "BTN_SEC_HOVER": "#1E293B", "BTN_SEC_TEXT": "#BAE6FD",
                "PRI_START": "#0284C7", "PRI_END": "#2563EB", "PRI_H_START": "#0EA5E9", "PRI_H_END": "#3B82F6",
                "LIST_BG": "#0B1120", "LIST_ITEM": "#0F172A", "LIST_HOVER": "#1E293B", "LIST_SEL": "#0284C7",
                "TERM_BG": "#020617", "TERM_TEXT": "#38BDF8", "SHADOW": "rgba(2,132,199,80)",
                "DIS_BG": "rgba(255, 255, 255, 0.06)", "DIS_TEXT": "rgba(255, 255, 255, 0.4)",
                "DIS_BORDER": "rgba(255, 255, 255, 0.2)", "DIS_PRI_BG": "rgba(255, 255, 255, 0.15)",
                "INPUT_DIS_BG": "rgba(255, 255, 255, 0.05)"
            },
            { # 3: 👑 暗金奢华 (Dark Gold Theme)
                "BG_MAIN": "#18181B", "BG_CARD": "#27272A", "BORDER": "#B45309", 
                "TEXT_MAIN": "#FEF08A", "TEXT_SUB": "#D4AF37", "TEXT_TITLE": "#FDE68A",
                "BTN_SEC": "#3F3F46", "BTN_SEC_HOVER": "#52525B", "BTN_SEC_TEXT": "#FEF08A",
                "PRI_START": "#B45309", "PRI_END": "#D97706", "PRI_H_START": "#D97706", "PRI_H_END": "#F59E0B",
                "LIST_BG": "#18181B", "LIST_ITEM": "#27272A", "LIST_HOVER": "#3F3F46", "LIST_SEL": "#B45309",
                "TERM_BG": "#09090B", "TERM_TEXT": "#FBBF24", "SHADOW": "rgba(180,83,9,80)",
                "DIS_BG": "rgba(255, 255, 255, 0.04)", "DIS_TEXT": "rgba(212, 175, 55, 0.4)",
                "DIS_BORDER": "rgba(180, 83, 9, 0.3)", "DIS_PRI_BG": "rgba(180, 83, 9, 0.15)",
                "INPUT_DIS_BG": "rgba(255, 255, 255, 0.02)"
            },
            { # 4: 🌸 猛男猛粉 (Cyber Pink)
                "BG_MAIN": "#1A0B13", "BG_CARD": "#2A1220", "BORDER": "#DB2777", 
                "TEXT_MAIN": "#FCE7F3", "TEXT_SUB": "#F472B6", "TEXT_TITLE": "#F9A8D4",
                "BTN_SEC": "#37172A", "BTN_SEC_HOVER": "#501E3C", "BTN_SEC_TEXT": "#FBCFE8",
                "PRI_START": "#DB2777", "PRI_END": "#9D174D", "PRI_H_START": "#F472B6", "PRI_H_END": "#BE185D",
                "LIST_BG": "#1A0B13", "LIST_ITEM": "#2A1220", "LIST_HOVER": "#37172A", "LIST_SEL": "#DB2777",
                "TERM_BG": "#0D0509", "TERM_TEXT": "#F9A8D4", "SHADOW": "rgba(219,39,119,80)",
                "DIS_BG": "rgba(255, 255, 255, 0.05)", "DIS_TEXT": "rgba(244, 114, 182, 0.5)",
                "DIS_BORDER": "rgba(219, 39, 119, 0.3)", "DIS_PRI_BG": "rgba(219, 39, 119, 0.15)",
                "INPUT_DIS_BG": "rgba(255, 255, 255, 0.03)"
            },
            { # 5: ☢️ 辐射废土 (Wasteland)
                "BG_MAIN": "#292524", "BG_CARD": "#44403C", "BORDER": "#84CC16", 
                "TEXT_MAIN": "#D6D3D1", "TEXT_SUB": "#A8A29E", "TEXT_TITLE": "#BEF264",
                "BTN_SEC": "#57534E", "BTN_SEC_HOVER": "#78716C", "BTN_SEC_TEXT": "#E7E5E4",
                "PRI_START": "#65A30D", "PRI_END": "#4D7C0F", "PRI_H_START": "#84CC16", "PRI_H_END": "#65A30D",
                "LIST_BG": "#292524", "LIST_ITEM": "#44403C", "LIST_HOVER": "#57534E", "LIST_SEL": "#65A30D",
                "TERM_BG": "#1C1917", "TERM_TEXT": "#84CC16", "SHADOW": "rgba(101,163,13,60)",
                "DIS_BG": "rgba(0, 0, 0, 0.2)", "DIS_TEXT": "rgba(168, 162, 158, 0.5)",
                "DIS_BORDER": "rgba(101, 163, 13, 0.2)", "DIS_PRI_BG": "rgba(101, 163, 13, 0.1)",
                "INPUT_DIS_BG": "rgba(0, 0, 0, 0.3)"
            },
            { # 6: 🔮 低调暗紫 (Dark Violet)
                "BG_MAIN": "#0F0B15", "BG_CARD": "#1B1429", "BORDER": "#7C3AED", 
                "TEXT_MAIN": "#F5F3FF", "TEXT_SUB": "#A78BFA", "TEXT_TITLE": "#DDD6FE",
                "BTN_SEC": "#2E2244", "BTN_SEC_HOVER": "#3F2E5E", "BTN_SEC_TEXT": "#EDE9FE",
                "PRI_START": "#7C3AED", "PRI_END": "#5B21B6", "PRI_H_START": "#8B5CF6", "PRI_H_END": "#6D28D9",
                "LIST_BG": "#0F0B15", "LIST_ITEM": "#1B1429", "LIST_HOVER": "#2E2244", "LIST_SEL": "#7C3AED",
                "TERM_BG": "#09060D", "TERM_TEXT": "#C4B5FD", "SHADOW": "rgba(124,58,237,70)",
                "DIS_BG": "rgba(255, 255, 255, 0.04)", "DIS_TEXT": "rgba(167, 139, 250, 0.5)",
                "DIS_BORDER": "rgba(124, 58, 237, 0.3)", "DIS_PRI_BG": "rgba(124, 58, 237, 0.15)",
                "INPUT_DIS_BG": "rgba(255, 255, 255, 0.02)"
            }
        ]
        
        p = palettes[index]
        
        self.target_list.set_placeholder_color(p["TEXT_SUB"])
        self.mask_list.set_placeholder_color(p["TEXT_SUB"])
        
        rgb = p["SHADOW"].replace('rgba(','').replace(')','').split(',')
        if len(rgb) == 4:
            self.shadow.setColor(QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(rgb[3])))

        qss = f"""
            QWidget {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 13px; color: {p['TEXT_MAIN']}; }}
            
            ::selection {{ background-color: {p['PRI_H_START']}; color: white; }}
            
            QFrame#mainContainer {{ background-color: {p['BG_MAIN']}; border: 1px solid {p['BORDER']}; border-radius: 12px; }}
            QFrame#titleBar {{ background-color: {p['BG_MAIN']}; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: 1px solid {p['BORDER']}; }}
            QLabel#titleLabel {{ color: {p['TEXT_TITLE']}; font-size: 12px; font-weight: bold; letter-spacing: 1px; }}
            
            QPushButton#macClose, QPushButton#macMin, QPushButton#macMax {{
                padding: 0px !important; margin: 0px !important;
                border-radius: 7px;
                min-width: 14px; min-height: 14px; max-width: 14px; max-height: 14px;
            }}
            QPushButton#macMin {{ background-color: #FFBD2E; border: 1px solid #E1A326; }}
            QPushButton#macMin:hover {{ background-color: #FFDF6E; border: 1px solid #FFBD2E; }}
            QPushButton#macMax {{ background-color: #27C93F; border: 1px solid #1DAE34; }}
            QPushButton#macMax:hover {{ background-color: #58E36D; border: 1px solid #27C93F; }}
            QPushButton#macClose {{ background-color: #FF5F56; border: 1px solid #E0443E; }}
            QPushButton#macClose:hover {{ background-color: #FF8982; border: 1px solid #FF5F56; }}
            
            QComboBox#themeCombo {{ background-color: {p['BTN_SEC']}; color: {p['TEXT_MAIN']}; border: 1px solid {p['BORDER']}; border-radius: 6px; padding: 4px 10px; font-weight: bold; }}
            QComboBox#themeCombo:hover {{ background-color: {p['BTN_SEC_HOVER']}; }}
            QComboBox#themeCombo::drop-down {{ border: none; }}
            QComboBox#themeCombo QAbstractItemView {{ background-color: {p['BG_CARD']}; color: {p['TEXT_MAIN']}; border: 1px solid {p['BORDER']}; selection-background-color: {p['PRI_START']}; border-radius: 6px; }}

            QFrame#card {{ background-color: {p['BG_CARD']}; border: 1px solid {p['BORDER']}; border-radius: 10px; }}
            QLabel#cardTitle {{ color: {p['TEXT_MAIN']}; font-size: 15px; font-weight: 700; }}
            QLabel#subText {{ color: {p['TEXT_SUB']}; font-size: 12px; }}
            QLabel#badge {{ background: {p['BORDER']}; color: {p['BG_MAIN']}; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: bold; }}
            
            QListWidget#darkList {{
                background: {p['LIST_BG']}; border: 1.5px dashed {p['BORDER']}; border-radius: 8px; outline: none; padding: 6px; color: {p['TEXT_MAIN']}; font-size: 13px;
            }}
            QListWidget#darkList[drag="active"] {{ border: 2px dashed {p['PRI_H_START']}; background: {p['LIST_ITEM']}; }}
            QListWidget#darkList::item {{ padding: 8px 10px; border-radius: 6px; margin-bottom: 3px; background: {p['LIST_ITEM']}; border: 1px solid transparent; }}
            QListWidget#darkList::item:hover {{ background: {p['LIST_HOVER']}; border-color: {p['BORDER']}; }}
            QListWidget#darkList::item:selected {{ background: {p['LIST_SEL']}; color: white; border-color: {p['PRI_H_START']}; }}
            
            QLineEdit#neonInput {{
                background: {p['LIST_BG']}; border: 1px solid {p['BORDER']}; border-radius: 6px; padding: 8px 12px; color: {p['PRI_H_START']}; font-family: "Consolas", monospace; font-weight: bold;
            }}
            QLineEdit#neonInput:focus {{ border: 1px solid {p['PRI_H_START']}; background: {p['LIST_ITEM']}; }}
            
            QTextEdit#terminal {{ 
                background: {p['TERM_BG']}; color: {p['TERM_TEXT']}; border: 1px solid {p['BORDER']}; 
                font-family: "Consolas", monospace; font-size: 13px; border-radius: 8px; line-height: 1.5; padding: 8px;
            }}
            
            QProgressBar#neonProgress {{ background: {p['BORDER']}; border: none; border-radius: 4px; }}
            QProgressBar#neonProgress::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['PRI_START']}, stop:1 {p['PRI_END']}); border-radius: 4px; }}
            
            QPushButton {{ border: none; border-radius: 6px; padding: 8px 14px; font-weight: 600; transition: all 0.3s ease; }}
            
            QPushButton[role="primary"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['PRI_START']}, stop:1 {p['PRI_END']});
                color: white; font-size: 14px; letter-spacing: 1px;
                border: 1px solid rgba(255, 255, 255, 0.15);
            }}
            QPushButton[role="primary"]:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['PRI_H_START']}, stop:1 {p['PRI_H_END']});
                border: 1px solid rgba(255, 255, 255, 0.4);
            }}
            
            QPushButton[role="secondary"] {{ background: {p['BTN_SEC']}; color: {p['BTN_SEC_TEXT']}; border: 1px solid transparent; }}
            QPushButton[role="secondary"]:hover {{ background: {p['BTN_SEC_HOVER']}; border: 1px solid {p['BORDER']}; }}
            
            QPushButton[role="accent"] {{ background: transparent; color: {p['PRI_H_START']}; border: 1px solid {p['PRI_START']}; }}
            QPushButton[role="accent"]:hover {{ background: {p['PRI_START']}; color: white; }}
            
            QPushButton[role="danger"] {{ background: transparent; color: #F43F5E; border: 1px solid #E11D48; }}
            QPushButton[role="danger"]:hover {{ background: #E11D48; color: white; }}
            
            QPushButton:disabled {{ 
                background: {p['DIS_BG']}; color: {p['DIS_TEXT']}; border: 1px dashed {p['DIS_BORDER']}; 
            }}
            QPushButton[role="primary"]:disabled {{ 
                background: {p['DIS_PRI_BG']}; color: {p['DIS_TEXT']}; border: 1px solid {p['DIS_BORDER']}; 
            }}
            QLineEdit:disabled {{ 
                background: {p['INPUT_DIS_BG']}; color: {p['DIS_TEXT']}; border: 1px solid {p['DIS_BORDER']}; 
            }}
            
            QScrollBar:horizontal {{ border: none; background: transparent; height: 0px; margin: 0px; }}
            QScrollBar::handle:horizontal {{ background: transparent; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
            
            QScrollBar:vertical {{ border: none; background: transparent; width: 6px; margin: 0px; }}
            QScrollBar::handle:vertical {{ background: {p['BORDER']}; border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: {p['TEXT_SUB']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """
        self.setStyleSheet(qss)


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
        if not self.engine.target_files: return self.cb_log("中断: 目标队列为空")
        self.set_ui_busy(True)
        self.current_worker = DetectWorker(self.engine)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(self._on_detect_done)
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_detect_done(self, o, d, f):
        self.set_ui_busy(False)
        self.cb_progress(1, 1, "分析完毕", f"原装:{o} | 伪装:{d} | 异常:{len(f)}")
        if f:
            for line in f: self.cb_log(f"[WARN] {line}")

    def ui_toggle(self):
        if not self.engine.target_files: return self.cb_log("中断: 目标队列为空")
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
        self.cb_progress(1, 1, "引擎挂起", f"成功:{s} | 失败:{len(f)}")
        self.cb_log(f"执行周期结束。成功:{s} 失败:{len(f)}")

    def ui_gen_exe(self):
        try: out_dir = self.engine.get_common_target_parent_dir()
        except Exception as e: return self.cb_log(f"中断: {e}")
        self.set_ui_busy(True)
        self.current_worker = ExeWorker(self.engine, out_dir)
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