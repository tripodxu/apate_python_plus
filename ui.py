
import sys
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QKeySequence, QPixmap, QImage, QMovie
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate, QStackedWidget
from PyQt5.QtCore import QBuffer, QByteArray, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QFileDialog, QShortcut,
    QTextEdit, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit,
    QListWidget, QListWidgetItem, QFrame, QGridLayout, QProgressBar,
    QGraphicsDropShadowEffect, QComboBox, QMenu,
    QTreeWidget, QTreeWidgetItem, QInputDialog, QSplitter, QScrollArea, QSlider,
)

from core import (
    DisguiseEngine, DisguiseError, disguise_file, collect_files_from_paths,
    PathManager, magic_to_display_text, format_file_size, APP_VERSION,
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
    def __init__(self, parent=None, title=f"✨ APLUSE ENGINE v{APP_VERSION}", show_dev_btn=False, show_theme=True):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(48)
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)

        layout.addSpacing(16)

        # 开发者模式入口
        if show_dev_btn:
            self.btn_dev = QPushButton("\U0001f512")
            self.btn_dev.setObjectName("macMin")
            self.btn_dev.setFixedSize(28, 28)
            self.btn_dev.setToolTip("开发者模式")
            self.btn_dev.clicked.connect(parent._toggle_developer_mode)
            layout.addWidget(self.btn_dev)

        layout.addStretch()

        if show_theme:
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

    def set_dev_active(self, active):
        if hasattr(self, 'btn_dev'):
            self.btn_dev.setText("\U0001f513" if active else "\U0001f512")

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


# 分组配色：(左边条色, 背景色, 文字高亮色)
GROUP_PALETTES = [
    ("#4a9eff", "#4a9eff12", "#7ec8ff"),   # 蓝
    ("#b07eff", "#b07eff12", "#cca8ff"),   # 紫
    ("#ffa04a", "#ffa04a12", "#ffc080"),   # 橙
    ("#50d88a", "#50d88a12", "#80f0b0"),   # 绿
    ("#ff6b9d", "#ff6b9d12", "#ffa0c0"),   # 粉
    ("#e0d040", "#e0d04012", "#f0e880"),   # 黄
    ("#50c8d8", "#50c8d812", "#80e8f0"),   # 青
    ("#ff6060", "#ff606012", "#ff9090"),   # 红
]


class GroupedListDelegate(QStyledItemDelegate):
    """为分组文件绘制彩色左边条和背景色。"""

    def paint(self, painter, option, index):
        # 读取分组颜色数据 (stored as UserRole+1)
        border_color = index.data(Qt.UserRole + 1)
        bg_color = index.data(Qt.UserRole + 2)
        group_label = index.data(Qt.UserRole + 3)

        painter.save()

        # 绘制背景
        if bg_color:
            painter.fillRect(option.rect, QColor(bg_color))
        elif option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(255, 255, 255, 8))

        # 绘制左边条（4px 宽）
        if border_color:
            bar_rect = option.rect.adjusted(0, 0, 0, 0)
            bar_rect.setWidth(4)
            painter.fillRect(bar_rect, QColor(border_color))

        # 绘制文本
        text_rect = option.rect.adjusted(12, 0, -8, 0)
        text = index.data(Qt.DisplayRole) or ""
        painter.setPen(QColor(option.palette.color(
            option.palette.HighlightedText if (option.state & QStyle.State_Selected)
            else option.palette.Text
        )))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.TextSingleLine, text)

        # 绘制分组标签（右上角小字）
        if group_label and border_color:
            label_rect = option.rect.adjusted(0, 2, -8, 0)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            painter.setPen(QColor(border_color))
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignTop, group_label)

        painter.restore()

    def sizeHint(self, option, index):
        hint = QStyledItemDelegate.sizeHint(self, option, index)
        hint.setHeight(max(hint.height(), 28))
        return hint


class CustomDropList(QListWidget):
    def __init__(self, placeholder_text, drop_type, window_ref):
        super().__init__()
        self.placeholder_text = placeholder_text
        self.drop_type = drop_type
        self.window_ref = window_ref
        self.placeholder_color = "#52525B"

        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setObjectName("darkList")
        self.setSelectionMode(QListWidget.ExtendedSelection)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrap(True)

        # 设置分组绘制代理
        self._group_delegate = GroupedListDelegate(self)
        self.setItemDelegate(self._group_delegate)

    def set_placeholder_color(self, hex_color):
        self.placeholder_color = hex_color
        self.viewport().update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setProperty("drag", "active")
            self.style().unpolish(self); self.style().polish(self)
            event.accept()
        elif event.source() == self:
            # 内部拖拽
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.source() == self:
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("drag", "none")
        self.style().unpolish(self); self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("drag", "none")
        self.style().unpolish(self); self.style().polish(self)

        # 外部文件拖入（从文件管理器拖入的 URL）
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                if self.drop_type == "target":
                    self.window_ref.ui_add_target_paths(paths)
                elif self.drop_type == "mask":
                    self.window_ref.ui_add_mask_paths(paths)
                elif self.drop_type == "mcpk":
                    self.window_ref.ui_add_mcpk_pack_paths(paths)
            event.accept()
            return

        # 内部拖拽排序 — InternalMove 会自动移动 item
        super().dropEvent(event)
        # 移动后同步 mcpk_queue 顺序
        self._sync_queue_order()

    def _sync_queue_order(self):
        """将列表控件中的实际顺序同步回 mcpk_queue。"""
        if self.drop_type != "mcpk":
            return
        new_order = []
        for i in range(self.count()):
            item = self.item(i)
            if item:
                path = item.data(Qt.UserRole)
                if path:
                    new_order.append(path)
        self.window_ref.mcpk_queue = new_order

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


# =================== MCPK 分组卡片组件 ===================

# 分组卡片配色方案（header_bg, header_text, border）
GROUP_COLORS = [
    ("#2d5a8e", "#7eb8ff", "#1a3d6b"),   # 蓝
    ("#5a3d8e", "#b87eff", "#3d1a6b"),   # 紫
    ("#8e5a2d", "#ffce7e", "#6b3d1a"),   # 橙
    ("#2d8e5a", "#7effb8", "#1a6b3d"),   # 绿
    ("#8e2d5a", "#ff7eb8", "#6b1a3d"),   # 粉
    ("#5a8e2d", "#b8ff7e", "#3d6b1a"),   # 黄绿
    ("#2d8e8e", "#7effff", "#1a6b6b"),   # 青
    ("#8e2d2d", "#ff7e7e", "#6b1a1a"),   # 红
]


class GroupCard(QFrame):
    """可视化的分组卡片，支持拖入文件、显示组内文件列表。"""

    remove_requested = pyqtSignal(str)   # group_name
    file_remove_requested = pyqtSignal(str, str)  # group_name, file_path

    def __init__(self, group_name, color_index=0, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.color_index = color_index % len(GROUP_COLORS)
        self.file_paths = []
        self._selected = False

        bg, text, border = GROUP_COLORS[self.color_index]
        self.setObjectName("groupCard")
        self.setAcceptDrops(True)
        self.setMinimumWidth(180)
        self.setMaximumWidth(260)
        self.setStyleSheet(f"""
            QFrame#groupCard {{
                background: {bg}22;
                border: 2px solid {border};
                border-radius: 10px;
                margin: 2px;
            }}
            QFrame#groupCard[active="true"] {{
                border: 2px solid {text};
                background: {bg}44;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 头部 ──
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 1px solid {border};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 0, 6, 0)
        h_layout.setSpacing(6)

        # 分组图标 + 名称
        self._name_label = QLabel(f"\U0001f4c1 {group_name}")
        self._name_label.setStyleSheet(f"color: {text}; font-weight: bold; font-size: 12px; border: none;")
        h_layout.addWidget(self._name_label, 1)

        # 计数徽章
        self._count_badge = QLabel("0")
        self._count_badge.setFixedSize(22, 22)
        self._count_badge.setAlignment(Qt.AlignCenter)
        self._count_badge.setStyleSheet(f"""
            background: {text}33; color: {text};
            border-radius: 11px; font-size: 11px; font-weight: bold; border: none;
        """)
        h_layout.addWidget(self._count_badge)

        # 关闭按钮
        btn_close = QPushButton("×")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {text}aa;
                border: none; border-radius: 11px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {text}33; color: {text}; }}
        """)
        btn_close.clicked.connect(lambda: self.remove_requested.emit(self.group_name))
        h_layout.addWidget(btn_close)

        layout.addWidget(header)

        # ── 文件列表区 ──
        self._file_list = QListWidget()
        self._file_list.setObjectName("groupFileList")
        self._file_list.setStyleSheet(f"""
            QListWidget#groupFileList {{
                background: transparent;
                border: none;
                font-size: 11px;
                padding: 4px;
            }}
            QListWidget#groupFileList::item {{
                padding: 3px 6px;
                border-radius: 4px;
                color: {text}cc;
            }}
            QListWidget#groupFileList::item:hover {{
                background: {bg}44;
            }}
        """)
        self._file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._file_list.setMaximumHeight(120)
        layout.addWidget(self._file_list)

        self.set_selected(False)

    def set_selected(self, selected):
        self._selected = selected
        self.setProperty("active", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def add_file(self, file_path):
        if file_path in self.file_paths:
            return
        self.file_paths.append(file_path)
        name = Path(file_path).name
        self._file_list.addItem(name)
        self._update_count()

    def remove_file(self, file_path):
        if file_path not in self.file_paths:
            return
        idx = self.file_paths.index(file_path)
        self.file_paths.pop(idx)
        self._file_list.takeItem(idx)
        self._update_count()

    def _update_count(self):
        n = len(self.file_paths)
        self._count_badge.setText(str(n))

    def mousePressEvent(self, event):
        # 点击卡片头部区域时选中此分组
        if event.pos().y() < 40:
            parent = self.parent()
            while parent and not isinstance(parent, MainWindow):
                parent = parent.parent()
            if parent:
                parent._select_group_card(self.group_name)
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.set_selected(True)

    def dragLeaveEvent(self, event):
        if not self._selected:
            self.set_selected(False)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        parent = self.parent()
        while parent and not isinstance(parent, MainWindow):
            parent = parent.parent()
        if parent:
            for p in paths:
                parent._add_file_to_group(p, self.group_name)
        event.acceptProposedAction()


# =================== MCPK 内容查看对话框 ===================

class MCPKViewerDialog(QWidget):
    def __init__(self, mcpk_path, parent=None):
        super().__init__(parent)
        self.mcpk_path = Path(mcpk_path)
        self.parent_window = parent
        self._info = None
        self._password = None  # 加密文件的密码

        self.setWindowTitle(f"MCPK - {self.mcpk_path.name}")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setMinimumSize(900, 600)
        self.resize(1000, 650)

        self._load_data()
        self._init_ui()
        if parent:
            self.setStyleSheet(parent.styleSheet())

    def _load_data(self):
        try:
            self._info = DisguiseEngine.inspect_mcpk(self.mcpk_path)
        except Exception as e:
            err_msg = str(e)
            # 如果是加密文件，提示输入密码
            if "已加密" in err_msg or "密码" in err_msg:
                from PyQt5.QtWidgets import QInputDialog
                pwd, ok = QInputDialog.getText(
                    self, "需要密码", "此 MCPK 文件已加密，请输入密码：",
                    QLineEdit.Password
                )
                if ok and pwd:
                    self._password = pwd
                    try:
                        self._info = DisguiseEngine.inspect_mcpk(self.mcpk_path, password=pwd)
                        return
                    except Exception as e2:
                        err_msg = str(e2)
            self._info = {"error": err_msg, "entries": []}

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info_frame = QFrame()
        info_frame.setObjectName("card")
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(16, 12, 16, 12)

        if "error" in self._info:
            info_layout.addWidget(QLabel(f"加载失败: {self._info['error']}"))
        else:
            enc_str = ""
            if self._info.get("encrypted"):
                mode = self._info.get("encrypt_mode", "FULL")
                enc_str = f"  |  已加密 ({mode})"
            group_count = self._info.get("group_count", 0)
            group_str = f"  |  分组: {group_count}" if group_count > 0 else ""
            stats = [
                f"v{self._info.get('version', '?')}",
                f"文件: {format_file_size(self._info.get('file_size', 0))}",
                f"条目: {self._info.get('entry_count', 0)}",
                f"原始: {format_file_size(self._info.get('total_original_size', 0))}",
                f"压缩比: {self._info.get('overall_ratio', 'N/A')}",
            ]
            info_text = "  |  ".join(stats) + enc_str + group_str
            info_layout.addWidget(QLabel(info_text))
        layout.addWidget(info_frame)

        # ── 表格 + 预览 分割布局 ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("darkSplitter")

        # 左侧：文件列表
        self.table = QTreeWidget()
        self.table.setObjectName("darkList")
        self.table.setHeaderLabels(["类型", "文件名", "MIME", "原始大小", "存储大小", "压缩", "修改时间", "CRC32", "元数据"])
        self.table.setColumnCount(9)
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTreeWidget.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.currentItemChanged.connect(self._on_entry_selected)

        icons = {"DOCUMENT": "\U0001f4c4", "IMAGE": "\U0001f5bc️", "AUDIO": "\U0001f3b5", "VIDEO": "\U0001f3ac"}
        for entry in self._info.get("entries", []):
            item = QTreeWidgetItem()
            tn = entry.get("type", "?")
            fallback_icon = "\U0001f4ce"
            item.setText(0, f"{icons.get(tn, fallback_icon)} {tn}")
            item.setText(1, entry.get("name", ""))
            item.setText(2, entry.get("mime", ""))
            item.setText(3, format_file_size(entry.get("original_size", 0)))
            item.setText(4, format_file_size(entry.get("stored_size", 0)))
            item.setText(5, entry.get("compression", "-"))
            mod_iso = entry.get("modified_iso", "")
            mod_at = entry.get("modified_at", 0)
            if mod_iso:
                item.setText(6, mod_iso[:19].replace("T", " "))
            elif mod_at > 0:
                from datetime import datetime
                item.setText(6, datetime.fromtimestamp(mod_at / 1000).strftime("%Y-%m-%d %H:%M:%S"))
            else:
                item.setText(6, "-")
            item.setText(7, entry.get("crc32", ""))
            meta = entry.get("metadata", {})
            ms = ", ".join(f"{k}={v}" for k, v in meta.items() if k != "custom") if meta else "-"
            item.setText(8, ms)
            item.setData(0, Qt.UserRole, entry.get("name", ""))
            self.table.addTopLevelItem(item)

        for i in range(9):
            self.table.resizeColumnToContents(i)
        self.table.setColumnWidth(1, max(200, self.table.columnWidth(1)))

        splitter.addWidget(self.table)

        # 右侧：预览面板
        preview_frame = QFrame()
        preview_frame.setObjectName("card")
        preview_frame.setMinimumWidth(300)
        pv_layout = QVBoxLayout(preview_frame)
        pv_layout.setContentsMargins(12, 12, 12, 12)
        pv_layout.setSpacing(8)

        preview_title = QLabel("\U0001f441️ 预览")
        preview_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ccc;")
        pv_layout.addWidget(preview_title)

        # ── 预览切换器 ──
        self._preview_stack = QStackedWidget()

        # Page 0: 占位（未选择）
        self._preview_placeholder = QLabel("选择文件以预览")
        self._preview_placeholder.setAlignment(Qt.AlignCenter)
        self._preview_placeholder.setStyleSheet("color: #666; font-size: 13px; background: rgba(255,255,255,0.03); border-radius: 8px;")
        self._preview_stack.addWidget(self._preview_placeholder)

        # Page 1: 静态图片
        self._preview_image = QLabel()
        self._preview_image.setAlignment(Qt.AlignCenter)
        self._preview_image.setStyleSheet("background: rgba(255,255,255,0.03); border-radius: 8px;")
        self._preview_stack.addWidget(self._preview_image)

        # Page 2: GIF 动画
        self._preview_gif = QLabel()
        self._preview_gif.setAlignment(Qt.AlignCenter)
        self._preview_gif.setStyleSheet("background: rgba(255,255,255,0.03); border-radius: 8px;")
        self._preview_gif_movie = None
        self._preview_gif_buffer = None
        self._preview_stack.addWidget(self._preview_gif)

        # Page 3: 视频播放
        self._preview_video_widget = QVideoWidget()
        self._preview_video_widget.setStyleSheet("background: #111; border-radius: 8px;")
        self._preview_player = QMediaPlayer()
        self._preview_player.setVideoOutput(self._preview_video_widget)
        self._preview_stack.addWidget(self._preview_video_widget)

        # 视频控制栏
        video_ctrl = QHBoxLayout()
        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedSize(32, 32)
        self._btn_play.setStyleSheet("QPushButton { background: rgba(255,255,255,0.1); border-radius: 16px; font-size: 14px; } QPushButton:hover { background: rgba(255,255,255,0.2); }")
        self._btn_play.clicked.connect(self._toggle_video_play)
        self._btn_play.hide()
        video_ctrl.addWidget(self._btn_play)

        self._video_position = QLabel("00:00")
        self._video_position.setStyleSheet("color: #999; font-size: 11px;")
        self._video_position.hide()
        video_ctrl.addWidget(self._video_position)

        self._video_slider = QSlider(Qt.Horizontal)
        self._video_slider.setStyleSheet("QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,0.15); border-radius: 2px; } QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: #4a9eff; border-radius: 6px; }")
        self._video_slider.hide()
        self._video_slider.sliderMoved.connect(self._on_video_slider_moved)
        video_ctrl.addWidget(self._video_slider, 1)

        self._video_duration = QLabel("00:00")
        self._video_duration.setStyleSheet("color: #999; font-size: 11px;")
        self._video_duration.hide()
        video_ctrl.addWidget(self._video_duration)

        pv_layout.addWidget(self._preview_stack, 1)
        pv_layout.addLayout(video_ctrl)

        # 文件信息
        self._preview_info = QLabel("")
        self._preview_info.setWordWrap(True)
        self._preview_info.setObjectName("subText")
        pv_layout.addWidget(self._preview_info)

        # 视频播放器信号
        self._preview_player.positionChanged.connect(self._on_video_position_changed)
        self._preview_player.durationChanged.connect(self._on_video_duration_changed)
        self._preview_player.stateChanged.connect(self._on_video_state_changed)
        self._preview_temp_file = None  # 临时文件引用

        splitter.addWidget(preview_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_sel = QPushButton("\U0001f4e6 提取选中"); btn_sel.setProperty("role", "secondary"); btn_sel.clicked.connect(self._extract_selected); btn_row.addWidget(btn_sel)
        btn_all = QPushButton("\U0001f4c2 提取全部"); btn_all.setProperty("role", "secondary"); btn_all.clicked.connect(self._extract_all); btn_row.addWidget(btn_all)
        btn_row.addStretch()
        btn_dis = QPushButton("\U0001f3ad 发送到伪装引擎"); btn_dis.setProperty("role", "accent"); btn_dis.setToolTip("将此 .mcpk 发送到开发者模式的目标队列"); btn_dis.clicked.connect(self._disguise_mcpk); btn_row.addWidget(btn_dis)
        btn_close = QPushButton("关闭"); btn_close.clicked.connect(self.close); btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _on_entry_selected(self, current, previous):
        """当表格选中条目变化时，更新预览面板。"""
        # 停止之前的视频播放
        self._preview_player.stop()
        if self._preview_gif_movie:
            self._preview_gif_movie.stop()
        self._hide_video_controls()

        if not current:
            self._preview_stack.setCurrentIndex(0)
            self._preview_info.setText("")
            return

        name = current.data(0, Qt.UserRole)
        if not name:
            return

        # 查找条目信息
        entry_info = None
        for e in self._info.get("entries", []):
            if e.get("name") == name:
                entry_info = e
                break
        if not entry_info:
            return

        entry_type = entry_info.get("type", "")
        mime = entry_info.get("mime", "")
        ext = Path(name).suffix.lower()

        # 更新信息标签
        info_lines = [
            f"文件: {name}",
            f"类型: {entry_type} ({mime})",
            f"大小: {format_file_size(entry_info.get('original_size', 0))}",
        ]
        if entry_info.get("created_iso"):
            info_lines.append(f"创建: {entry_info['created_iso'][:19].replace('T', ' ')}")
        if entry_info.get("modified_iso"):
            info_lines.append(f"修改: {entry_info['modified_iso'][:19].replace('T', ' ')}")
        meta = entry_info.get("metadata", {})
        if meta.get("title"):
            info_lines.append(f"标题: {meta['title']}")
        if meta.get("tags"):
            info_lines.append(f"标签: {', '.join(meta['tags'])}")
        self._preview_info.setText("\n".join(info_lines))

        # 根据类型路由预览
        TEXT_EXTS = {".md", ".txt", ".json", ".csv", ".srt", ".vtt", ".ass", ".xml", ".yaml", ".yml", ".html", ".htm"}
        IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".ico"}
        GIF_EXTS = {".gif"}
        VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v"}

        try:
            if ext in GIF_EXTS or (entry_type == "IMAGE" and ext == ".gif"):
                self._show_gif_preview(name)
            elif entry_type == "VIDEO" or ext in VIDEO_EXTS:
                self._show_video_preview(name)
            elif entry_type == "IMAGE" or ext in IMAGE_EXTS:
                self._show_image_preview(name)
            elif entry_type == "DOCUMENT" or ext in TEXT_EXTS:
                self._show_text_preview(name)
            else:
                self._show_placeholder(entry_type, name)
        except Exception as e:
            self._preview_stack.setCurrentIndex(1)
            self._preview_image.setPixmap(QPixmap())
            self._preview_image.setText(f"预览失败:\n{e}")

    def _show_image_preview(self, name):
        """静态图片预览。"""
        from mcpk import MCPKReader
        with MCPKReader(self.mcpk_path, password=self._password) as reader:
            data = reader.extract(name)

        img = QImage()
        img.loadFromData(data)
        if img.isNull():
            self._preview_image.setText("无法加载图片")
            self._preview_stack.setCurrentIndex(1)
            return

        pixmap = QPixmap.fromImage(img)
        scaled = pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._preview_image.setPixmap(scaled)
        self._preview_image.setText("")
        self._preview_stack.setCurrentIndex(1)

    def _show_gif_preview(self, name):
        """GIF 动画预览。"""
        from mcpk import MCPKReader
        with MCPKReader(self.mcpk_path, password=self._password) as reader:
            data = reader.extract(name)

        # 停止旧动画
        if self._preview_gif_movie:
            self._preview_gif_movie.stop()

        # QBuffer 保持对 data 的引用
        self._preview_gif_buffer = QBuffer()
        self._preview_gif_buffer.setData(QByteArray(data))
        self._preview_gif_buffer.open(QBuffer.ReadOnly)

        movie = QMovie()
        movie.setDevice(self._preview_gif_buffer)
        if not movie.isValid():
            self._preview_gif.setText("无法加载 GIF")
            self._preview_stack.setCurrentIndex(2)
            return

        self._preview_gif_movie = movie
        self._preview_gif.setMovie(movie)
        movie.start()
        self._preview_stack.setCurrentIndex(2)

    def _show_video_preview(self, name):
        """视频预览（提取到临时文件后播放）。"""
        import tempfile
        from mcpk import MCPKReader

        with MCPKReader(self.mcpk_path, password=self._password) as reader:
            data = reader.extract(name)

        # 写入临时文件
        ext = Path(name).suffix.lower()
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(data)
        tmp.close()
        self._preview_temp_file = tmp.name

        self._preview_player.setMedia(QMediaContent(QUrl.fromLocalFile(tmp.name)))
        self._preview_stack.setCurrentIndex(3)
        self._show_video_controls()
        self._preview_player.play()

    def _show_text_preview(self, name, max_chars=8000):
        """文本预览。"""
        from mcpk import MCPKReader
        with MCPKReader(self.mcpk_path, password=self._password) as reader:
            data = reader.extract(name)

        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                text = data.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            self._preview_image.setText("无法解码文本")
            self._preview_stack.setCurrentIndex(1)
            return

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... (已截断，共 {len(data)} 字节)"

        self._preview_image.setText(text)
        self._preview_image.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._preview_image.setStyleSheet(
            "background: rgba(255,255,255,0.03); border-radius: 8px; "
            "padding: 8px; font-family: Consolas, 'Courier New', monospace; font-size: 12px; color: #ddd;"
        )
        self._preview_stack.setCurrentIndex(1)

    def _show_placeholder(self, entry_type, name):
        """其他类型：显示图标。"""
        type_icons = {"VIDEO": "\U0001f3ac", "AUDIO": "\U0001f3b5", "DOCUMENT": "\U0001f4c4"}
        icon = type_icons.get(entry_type, "\U0001f4ce")
        self._preview_image.setPixmap(QPixmap())
        self._preview_image.setText(f"{icon}\n{entry_type}\n{name}")
        self._preview_image.setStyleSheet("background: rgba(255,255,255,0.03); border-radius: 8px; color: #999;")
        self._preview_stack.setCurrentIndex(1)

    # ── 视频控制 ──

    def _show_video_controls(self):
        self._btn_play.show()
        self._video_position.show()
        self._video_slider.show()
        self._video_duration.show()

    def _hide_video_controls(self):
        self._btn_play.hide()
        self._video_position.hide()
        self._video_slider.hide()
        self._video_duration.hide()

    def _toggle_video_play(self):
        if self._preview_player.state() == QMediaPlayer.PlayingState:
            self._preview_player.pause()
        else:
            self._preview_player.play()

    def _on_video_position_changed(self, pos):
        self._video_position.setText(self._format_ms(pos))
        self._video_slider.setValue(pos)

    def _on_video_duration_changed(self, dur):
        self._video_duration.setText(self._format_ms(dur))
        self._video_slider.setRange(0, dur)

    def _on_video_state_changed(self, state):
        self._btn_play.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_video_slider_moved(self, pos):
        self._preview_player.setPosition(pos)

    @staticmethod
    def _format_ms(ms):
        s = ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"

    def _get_selected_names(self):
        return [i.data(0, Qt.UserRole) for i in self.table.selectedItems() if i.data(0, Qt.UserRole)]

    def _extract_selected(self):
        names = self._get_selected_names()
        if not names:
            return QMessageBox.information(self, "提示", "请先选择要提取的条目")
        output_dir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not output_dir: return
        try:
            from mcpk import MCPKReader
            with MCPKReader(self.mcpk_path, password=self._password) as reader:
                for name in names:
                    reader.extract_to(name, output_dir)
            QMessageBox.information(self, "完成", f"已提取 {len(names)} 个文件到:\n{output_dir}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"提取失败: {e}")

    def _extract_all(self):
        output_dir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not output_dir: return
        try:
            paths = DisguiseEngine.extract_mcpk_all(self.mcpk_path, output_dir, password=self._password)
            QMessageBox.information(self, "完成", f"已提取 {len(paths)} 个文件到:\n{output_dir}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"提取失败: {e}")

    def closeEvent(self, event):
        """关闭时清理播放器和临时文件。"""
        self._preview_player.stop()
        if self._preview_gif_movie:
            self._preview_gif_movie.stop()
        if self._preview_temp_file:
            try:
                import os
                os.unlink(self._preview_temp_file)
            except Exception:
                pass
        event.accept()

    def _disguise_mcpk(self):
        if self.parent_window:
            if not hasattr(self.parent_window, 'dev_window') or not self.parent_window.dev_window or not self.parent_window.dev_window.isVisible():
                QMessageBox.information(self, "提示", "请先在主界面点击锁图标开启「开发者模式」。")
                return
            self.parent_window.dev_window.ui_add_target_paths([str(self.mcpk_path)])
            QMessageBox.information(self, "已加入队列",
                f"{self.mcpk_path.name} 已添加到开发者模式的目标队列。\n请在面具库中选择文件，然后启动引擎。")
            self.close()


# =================== 主窗口（MCPK Manager） ===================

class MainWindow(QWidget):
    DEV_PASSWORD = "1080"

    def __init__(self):
        super().__init__()
        self.engine = DisguiseEngine()
        self.current_worker = None
        self.current_theme_index = 0
        self.dev_window = None
        self.mcpk_queue = []
        self.mcpk_group_map = {}  # {file_path: group_name}

        self.log_file_path = PathManager.get_persist_dir() / "apluse.log"

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.init_ui()
        self._setup_shortcuts()

        saved_theme = self.engine.config.get("theme_index", 0)
        self.title_bar.theme_combo.setCurrentIndex(saved_theme)
        self.change_theme(saved_theme)

        self.cb_log("MCPK Manager 初始化成功")

    def init_ui(self):
        self.resize(1280, 860)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)

        self.container = QFrame()
        self.container.setObjectName("mainContainer")

        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(25)
        self.shadow.setColor(QColor(0, 0, 0, 100))
        self.shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(self.shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self, title="✨ MCPK Manager v2.0", show_dev_btn=True)
        container_layout.addWidget(self.title_bar)

        dashboard_layout = QVBoxLayout()
        dashboard_layout.setContentsMargins(24, 20, 24, 24)
        dashboard_layout.setSpacing(16)

        # ==================== 中行：MCPK 打包 + MCPK 浏览 ====================
        file_row = QHBoxLayout()
        file_row.setSpacing(16)

        # MCPK 打包卡片
        pack_card = QFrame()
        pack_card.setObjectName("card")
        p_layout = QVBoxLayout(pack_card)
        p_layout.setContentsMargins(20, 16, 20, 16)

        p_header = QHBoxLayout()
        p_header.addWidget(self.make_label("\U0001f4e6 MCPK 打包", "cardTitle"))
        self.mcpk_count_label = self.make_label("0 项", "badge")
        p_header.addWidget(self.mcpk_count_label)
        p_header.addStretch()

        self.btn_mcpk_add = self.make_btn("➕ 文件", "secondary")
        self.btn_mcpk_add.clicked.connect(self.ui_mcpk_add_files)
        self.btn_mcpk_add_dir = self.make_btn("\U0001f4c1 目录", "secondary")
        self.btn_mcpk_add_dir.clicked.connect(self.ui_mcpk_add_dir)
        self.btn_mcpk_clr = self.make_btn("\U0001f5d1️ 清空", "danger")
        self.btn_mcpk_clr.clicked.connect(self.ui_mcpk_clear)

        p_header.addWidget(self.btn_mcpk_add)
        p_header.addWidget(self.btn_mcpk_add_dir)
        p_header.addWidget(self.btn_mcpk_clr)
        p_layout.addLayout(p_header)

        self.mcpk_pack_list = CustomDropList("\U0001f4e5 拖拽文件/文件夹至此打包为 .mcpk", "mcpk", self)
        p_layout.addWidget(self.mcpk_pack_list)

        # ── 分组操作栏 ──
        group_bar = QHBoxLayout()
        group_bar.setSpacing(6)

        self.btn_group_create = self.make_btn("＋ 分组", "secondary")
        self.btn_group_create.setToolTip("新建分组")
        self.btn_group_create.clicked.connect(self.ui_mcpk_create_group)
        group_bar.addWidget(self.btn_group_create)

        self.btn_group_assign = self.make_btn("→ 归入", "secondary")
        self.btn_group_assign.setToolTip("将选中文件归入当前分组")
        self.btn_group_assign.clicked.connect(self.ui_mcpk_assign_to_group)
        group_bar.addWidget(self.btn_group_assign)

        self.btn_group_ungroup = self.make_btn("← 移出", "secondary")
        self.btn_group_ungroup.setToolTip("将选中文件移出分组")
        self.btn_group_ungroup.clicked.connect(self.ui_mcpk_ungroup_selected)
        group_bar.addWidget(self.btn_group_ungroup)

        # 当前分组指示器
        self.mcpk_group_indicator = QLabel("未选择分组")
        self.mcpk_group_indicator.setStyleSheet("color: #888; font-size: 11px; padding: 4px 8px;")
        group_bar.addWidget(self.mcpk_group_indicator)

        group_bar.addStretch()

        # 分组选择下拉
        self.mcpk_group_combo = QComboBox()
        self.mcpk_group_combo.setPlaceholderText("选择分组")
        self.mcpk_group_combo.setMinimumWidth(100)
        self.mcpk_group_combo.setObjectName("searchInput")
        self.mcpk_group_combo.currentTextChanged.connect(self._on_group_combo_changed)
        group_bar.addWidget(self.mcpk_group_combo)

        p_layout.addLayout(group_bar)

        # 分组数据
        self.mcpk_groups = {}        # {group_name: [file_paths]}
        self.mcpk_group_colors = {}  # {group_name: (border, bg, text)}
        self.mcpk_group_color_idx = 0
        self.mcpk_selected_group = None

        self.btn_mcpk_pack = self.make_btn("\U0001f4e6 打包为 MCPK", "primary")
        self.btn_mcpk_pack.setFixedHeight(50)
        font = self.btn_mcpk_pack.font()
        font.setBold(True)
        font.setPointSize(11)
        self.btn_mcpk_pack.setFont(font)
        self.btn_mcpk_pack.clicked.connect(self.ui_mcpk_pack)
        p_layout.addWidget(self.btn_mcpk_pack)

        file_row.addWidget(pack_card)

        # 右侧面板：浏览 + 日志
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)

        # MCPK 浏览卡片
        browse_card = QFrame()
        browse_card.setObjectName("card")
        b_layout = QVBoxLayout(browse_card)
        b_layout.setContentsMargins(20, 16, 20, 16)

        b_layout.addWidget(self.make_label("\U0001f50d MCPK 浏览", "cardTitle"))
        desc = self.make_label("打开已有的 .mcpk 文件，查看内容、提取文件、验证完整性。", "subText")
        desc.setWordWrap(True)
        b_layout.addWidget(desc)
        b_layout.addStretch()

        self.btn_mcpk_view = self.make_btn("\U0001f4c2 打开 MCPK 文件", "accent")
        self.btn_mcpk_view.setFixedHeight(50)
        self.btn_mcpk_view.clicked.connect(self.ui_mcpk_view)
        b_layout.addWidget(self.btn_mcpk_view)

        right_layout.addWidget(browse_card)

        # 日志卡片
        log_card = QFrame()
        log_card.setObjectName("card")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(20, 16, 20, 20)

        log_header = QHBoxLayout()
        log_header.addWidget(self.make_label("\U0001f4dd 运行日志", "cardTitle"))
        log_header.addStretch()
        self.progress_label = self.make_label("就绪", "subText")
        log_header.addWidget(self.progress_label)
        log_layout.addLayout(log_header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("neonProgress")
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        log_layout.addWidget(self.progress_bar)

        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("terminal")
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)

        right_layout.addWidget(log_card, 1)

        file_row.addWidget(right_panel)
        dashboard_layout.addLayout(file_row, 1)

        container_layout.addLayout(dashboard_layout)
        main_layout.addWidget(self.container)

    # ── 工具方法 ──────────────────────────────────────────

    def make_label(self, text, obj_name):
        lbl = QLabel(text)
        lbl.setObjectName(obj_name)
        return lbl

    def make_btn(self, text, role="default"):
        btn = QPushButton(text)
        btn.setProperty("role", role)
        return btn

    def _make_file_item(self, filepath):
        try:
            size_str = format_file_size(Path(filepath).stat().st_size)
        except Exception:
            size_str = "?"
        item = QListWidgetItem(f"{Path(filepath).name}    [{size_str}]")
        item.setData(Qt.UserRole, filepath)
        item.setToolTip(filepath)
        return item

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Delete"), self).activated.connect(self.ui_mcpk_remove_selected)

    # ── 开发者模式 ────────────────────────────────────────

    def _toggle_developer_mode(self):
        if self.dev_window and self.dev_window.isVisible():
            self.dev_window.raise_()
            self.dev_window.activateWindow()
            return

        pwd, ok = QInputDialog.getText(self, "身份验证", "输入开发者密码:", QLineEdit.Password)
        if ok and pwd == self.DEV_PASSWORD:
            self.title_bar.set_dev_active(True)
            from ui_dev import DeveloperWindow
            self.dev_window = DeveloperWindow(self.engine, self)
            self.dev_window.show()
            self.cb_log("已开启开发者独立窗口")
        elif ok:
            QMessageBox.warning(self, "错误", "密码不正确")

    # ── 主题 ──────────────────────────────────────────────

    def change_theme(self, index):
        self.current_theme_index = index
        self.engine.config["theme_index"] = index
        self.engine.save_config()

        p = PALETTES[index]
        self.mcpk_pack_list.set_placeholder_color(p["TEXT_SUB"])

        shadow_rgba = parse_shadow_color(p["SHADOW"])
        if shadow_rgba:
            self.shadow.setColor(QColor(*shadow_rgba))

        qss = build_qss(p)
        self.setStyleSheet(qss)

        # 同步开发者窗口主题
        if self.dev_window:
            self.dev_window.setStyleSheet(qss)
            if hasattr(self.dev_window, 'target_list'):
                self.dev_window.target_list.set_placeholder_color(p["TEXT_SUB"])
                self.dev_window.mask_list.set_placeholder_color(p["TEXT_SUB"])

    # ── 日志与状态 ────────────────────────────────────────

    def cb_log(self, text):
        self.log_edit.append(f"> {text}")
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {text}\n")
        except Exception:
            pass

    def cb_progress(self, curr, total, title, detail):
        self.progress_bar.setValue(0 if total <= 0 else int((curr / total) * 100))
        self.progress_label.setText(f"{title} | {detail}")

    def set_ui_busy(self, busy):
        for b in [self.btn_mcpk_pack, self.btn_mcpk_add, self.btn_mcpk_add_dir, self.btn_mcpk_clr]:
            b.setEnabled(not busy)
        self.mcpk_pack_list.setEnabled(not busy)
        if self.dev_window:
            for b in [self.dev_window.btn_toggle, self.dev_window.btn_detect, self.dev_window.btn_gen]:
                b.setEnabled(not busy)

    def _on_worker_err(self, err_msg):
        self.set_ui_busy(False)
        self.cb_progress(0, 1, "系统崩溃", "ERR_FATAL")
        self.cb_log(f"[ERROR] 内核异常: {err_msg}")

    # ── MCPK 打包队列 ────────────────────────────────────

    def ui_add_mcpk_pack_paths(self, paths):
        added = 0
        for f in collect_files_from_paths(paths):
            if f not in self.mcpk_queue:
                self.mcpk_queue.append(f)
                added += 1
        self._refresh_mcpk_pack_list()
        self.cb_log(f"MCPK 队列: +{added} 项")

    def ui_mcpk_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if paths:
            self.ui_add_mcpk_pack_paths(paths)

    def ui_mcpk_add_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.ui_add_mcpk_pack_paths([folder])

    def ui_mcpk_remove_selected(self):
        if not self.mcpk_pack_list.hasFocus():
            return
        selected = self.mcpk_pack_list.selectedItems()
        if not selected:
            return
        sels = {i.data(Qt.UserRole) for i in selected}
        self.mcpk_queue = [p for p in self.mcpk_queue if p not in sels]
        for p in sels:
            self._remove_file_from_group(p)
        self._refresh_mcpk_pack_list()

    def ui_mcpk_create_group(self):
        """弹出输入框创建新分组。"""
        name, ok = QInputDialog.getText(self, "新建分组", "分组名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.mcpk_groups:
            return QMessageBox.information(self, "提示", f"分组「{name}」已存在")
        # 分配颜色
        colors = GROUP_PALETTES[self.mcpk_group_color_idx % len(GROUP_PALETTES)]
        self.mcpk_group_color_idx += 1
        self.mcpk_groups[name] = []
        self.mcpk_group_colors[name] = colors
        self.mcpk_group_combo.addItem(name)
        self.mcpk_group_combo.setCurrentText(name)
        self.cb_log(f"已创建分组「{name}」")

    def _on_group_combo_changed(self, text):
        """分组下拉切换时更新指示器。"""
        if text and text in self.mcpk_groups:
            self.mcpk_selected_group = text
            border, bg, txt_color = self.mcpk_group_colors.get(text, ("#888", "#88812", "#aaa"))
            self.mcpk_group_indicator.setText(f"● {text}")
            self.mcpk_group_indicator.setStyleSheet(f"color: {txt_color}; font-size: 11px; padding: 4px 8px; font-weight: bold;")
        else:
            self.mcpk_selected_group = None
            self.mcpk_group_indicator.setText("未选择分组")
            self.mcpk_group_indicator.setStyleSheet("color: #888; font-size: 11px; padding: 4px 8px;")

    def ui_mcpk_assign_to_group(self):
        """将选中文件归入当前分组。"""
        if not self.mcpk_selected_group:
            return QMessageBox.information(self, "提示", "请先在下拉框中选择一个分组")
        selected = self.mcpk_pack_list.selectedItems()
        if not selected:
            return QMessageBox.information(self, "提示", "请先在列表中选择文件")
        group_name = self.mcpk_selected_group
        count = 0
        for item in selected:
            path = item.data(Qt.UserRole)
            if path:
                self._assign_file_to_group(path, group_name)
                count += 1
        self._refresh_mcpk_pack_list()
        self.cb_log(f"已将 {count} 个文件归入「{group_name}」")

    def ui_mcpk_ungroup_selected(self):
        """将选中文件移出分组。"""
        selected = self.mcpk_pack_list.selectedItems()
        if not selected:
            return QMessageBox.information(self, "提示", "请先在列表中选择文件")
        count = 0
        for item in selected:
            path = item.data(Qt.UserRole)
            if path:
                self._remove_file_from_group(path)
                count += 1
        self._refresh_mcpk_pack_list()
        if count:
            self.cb_log(f"已将 {count} 个文件移出分组")

    def _assign_file_to_group(self, file_path, group_name):
        """将文件归入指定分组（内部方法）。"""
        # 从旧分组移除
        self._remove_file_from_group(file_path)
        # 加入新分组
        if group_name not in self.mcpk_groups:
            colors = GROUP_PALETTES[self.mcpk_group_color_idx % len(GROUP_PALETTES)]
            self.mcpk_group_color_idx += 1
            self.mcpk_groups[group_name] = []
            self.mcpk_group_colors[group_name] = colors
            self.mcpk_group_combo.addItem(group_name)
        self.mcpk_groups[group_name].append(file_path)
        self.mcpk_group_map[file_path] = group_name

    def _remove_file_from_group(self, file_path):
        """将文件从其当前分组中移除。"""
        old_group = self.mcpk_group_map.pop(file_path, None)
        if old_group and old_group in self.mcpk_groups:
            glist = self.mcpk_groups[old_group]
            if file_path in glist:
                glist.remove(file_path)
            # 自动清理空分组
            if not glist:
                del self.mcpk_groups[old_group]
                del self.mcpk_group_colors[old_group]
                idx = self.mcpk_group_combo.findText(old_group)
                if idx >= 0:
                    self.mcpk_group_combo.removeItem(idx)
                if self.mcpk_selected_group == old_group:
                    self.mcpk_selected_group = None

    def ui_mcpk_clear(self):
        self.mcpk_queue.clear()
        self.mcpk_group_map.clear()
        self.mcpk_groups.clear()
        self.mcpk_group_colors.clear()
        self.mcpk_group_color_idx = 0
        self.mcpk_selected_group = None
        self.mcpk_group_combo.clear()
        self._refresh_mcpk_pack_list()

    def _refresh_mcpk_pack_list(self):
        self.mcpk_pack_list.clear()
        for f in self.mcpk_queue:
            item = self._make_file_item(f)
            group = self.mcpk_group_map.get(f)
            if group and group in self.mcpk_group_colors:
                border, bg, txt = self.mcpk_group_colors[group]
                item.setData(Qt.UserRole + 1, border)     # 左边条颜色
                item.setData(Qt.UserRole + 2, bg)          # 背景色
                item.setData(Qt.UserRole + 3, f" {group} ") # 分组标签
                item.setText(f"{item.text()}")
            self.mcpk_pack_list.addItem(item)
        self.mcpk_count_label.setText(f"{len(self.mcpk_queue)} 项")

    # ── MCPK 打包 ────────────────────────────────────────

    def ui_mcpk_pack(self):
        if not self.mcpk_queue:
            return self.cb_log("中断: 队列为空，请先添加文件")

        output_path, _ = QFileDialog.getSaveFileName(
            self, "保存 MCPK 文件", "capsule.mcpk",
            "MCPK 文件 (*.mcpk);;所有文件 (*)"
        )
        if not output_path:
            return

        # 询问是否加密
        password = None
        encrypt_mode = "full"
        reply = QMessageBox.question(
            self, "加密选项", "是否对 MCPK 文件加密？",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.No
        )
        if reply == QMessageBox.Cancel:
            return
        if reply == QMessageBox.Yes:
            from PyQt5.QtWidgets import QInputDialog
            pwd, ok = QInputDialog.getText(
                self, "设置密码", "请输入加密密码：", QLineEdit.Password
            )
            if not ok or not pwd:
                return
            password = pwd

        self.set_ui_busy(True)
        original_targets = self.engine.target_files.copy()
        self.engine.target_files = self.mcpk_queue
        # 传递按文件分组映射（仅包含已分组的文件）
        group_map = dict(self.mcpk_group_map) if self.mcpk_group_map else None

        def pack_task(progress_cb, log_cb):
            return self.engine.generate_mcpk(
                output_path, log_cb, progress_cb,
                password=password, encrypt_mode=encrypt_mode,
                group_map=group_map
            )

        self.current_worker = EngineWorker(pack_task)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(lambda res: self._on_mcpk_pack_done(res, original_targets))
        self.current_worker.err_sig.connect(self._on_worker_err)
        self.current_worker.start()

    def _on_mcpk_pack_done(self, result, original_targets):
        self.engine.target_files = original_targets
        self.set_ui_busy(False)
        self.cb_progress(1, 1, "打包完成", Path(result).name)
        self.cb_log(f"MCPK 文件已生成: {result}")

        # ── 承载记忆流程 ──
        disguise_reply = QMessageBox.question(
            self, "承载记忆",
            f"你的记忆碎片已打包：\n{result}\n\n"
            "是否让它承载在一个平凡的外表之下？\n\n"
            "记忆会被藏进一段视频、一张图片之中，\n"
            "唯有那把属于你的钥匙，才能重新唤醒它。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if disguise_reply == QMessageBox.Yes:
            self._carry_memory_after_pack(result)

        # ── 查看内容 ──
        else:
            view_reply = QMessageBox.question(
                self, "打包完成",
                "是否查看记忆碎片的内容？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if view_reply == QMessageBox.Yes:
                self._open_mcpk_viewer(result)

    def _carry_memory_after_pack(self, mcpk_path):
        """打包后承载记忆流程：铸钥匙 → 选外壳 → 承载。"""

        # Step 1: 铸造钥匙
        magic_input, ok = QInputDialog.getText(
            self, "铸造你的钥匙",
            "为这段记忆铸造一把钥匙：\n\n"
            "它可以是一句暗语、一个日期、一个名字——\n"
            "任何对你而言有特殊意义的字符。\n"
            "也可以是十六进制（如 DEADBEEF）。\n\n"
            "请铭记它，遗忘即永失。",
            QLineEdit.Normal,
        )
        if not ok or not magic_input.strip():
            return

        # 解析钥匙
        try:
            magic_bytes = self.engine.parse_and_set_magic(magic_input.strip())
        except DisguiseError as e:
            return QMessageBox.warning(self, "铸造失败", str(e))

        magic_display = magic_to_display_text(magic_bytes)
        self.cb_log(f"记忆钥匙: {magic_display}")

        # Step 2: 选择承载的外壳
        mask_path = self._pick_memory_shell()
        if not mask_path:
            return

        # Step 3: 确认
        confirm = QMessageBox.question(
            self, "确认承载",
            f"记忆即将沉入平凡的外表之下：\n\n"
            f"  记忆: {Path(mcpk_path).name}\n"
            f"  外壳: {Path(mask_path).name}\n"
            f"  钥匙: {magic_display}\n\n"
            f"承载之后，它看起来只是一段普通的文件。\n"
            f"确认？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return

        # Step 4: 承载
        try:
            self.set_ui_busy(True)
            disguised_path = disguise_file(
                str(mcpk_path), str(mask_path), magic_bytes,
                reserved_output_paths=[str(mcpk_path)],
            )
            self.set_ui_busy(False)
            self.cb_log(f"记忆已承载: {disguised_path}")
            QMessageBox.information(
                self, "承载完成",
                f"记忆已沉睡。\n\n"
                f"它现在安静地躺在这里：\n{disguised_path}\n\n"
                f"看起来只是一段平凡的文件，\n"
                f"但当你再次握住那把钥匙，\n"
                f"它就会醒来。\n\n"
                f"钥匙: {magic_display}"
            )
        except Exception as e:
            self.set_ui_busy(False)
            self.cb_log(f"承载失败: {e}")
            QMessageBox.warning(self, "承载失败", str(e))

    def _pick_memory_shell(self):
        """让用户选择承载记忆的外壳。"""
        valid_masks = [p for p in self.engine.mask_library if Path(p).is_file()]

        if valid_masks:
            choice_reply = QMessageBox.question(
                self, "选择外壳",
                f"你有 {len(valid_masks)} 个可用的外壳。\n\n"
                "「是」从已有外壳中选择\n「否」从磁盘中寻找一个",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if choice_reply == QMessageBox.Cancel:
                return None
            if choice_reply == QMessageBox.Yes:
                items = [f"{Path(p).name}  ({format_file_size(Path(p).stat().st_size)})"
                         for p in valid_masks]
                item, ok = QInputDialog.getItem(
                    self, "选择外壳", "外壳文件：", items, 0, False,
                )
                if ok and item:
                    idx = items.index(item)
                    return valid_masks[idx]
                return None

        # 浏览选择
        mask_path, _ = QFileDialog.getOpenFileName(
            self, "选择外壳文件", "",
            "视频 (*.mp4 *.mkv *.avi *.mov);;图片 (*.jpg *.png *.bmp);;所有文件 (*)"
        )
        return mask_path if mask_path else None

    # ── MCPK 浏览 ────────────────────────────────────────

    def ui_mcpk_view(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 MCPK 文件", "", "MCPK 文件 (*.mcpk);;所有文件 (*)"
        )
        if file_path:
            self._open_mcpk_viewer(file_path)

    def _open_mcpk_viewer(self, mcpk_path):
        if not DisguiseEngine.is_mcpk_file(mcpk_path):
            return QMessageBox.warning(self, "错误", "不是有效的 MCPK 文件")
        self._mcpk_viewer = MCPKViewerDialog(mcpk_path, parent=self)
        self._mcpk_viewer.show()
