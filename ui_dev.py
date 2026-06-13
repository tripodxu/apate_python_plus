"""开发者窗口 — APLUSE ENGINE 伪装引擎（独立窗口）。"""

from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QFileDialog, QShortcut,
    QTextEdit, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit,
    QListWidget, QListWidgetItem, QFrame, QGridLayout, QProgressBar,
    QGraphicsDropShadowEffect, QComboBox, QMenu, QCheckBox,
)

from core import (
    DisguiseEngine, collect_files_from_paths,
    PathManager, magic_to_display_text, format_file_size,
)
from themes import PALETTES, THEME_NAMES, build_qss, parse_shadow_color
from ui import EngineWorker, CustomTitleBar, CustomDropList


class DeveloperWindow(QWidget):
    """独立的伪装引擎窗口，通过密码从主窗口打开。"""

    def __init__(self, engine, main_window):
        super().__init__()
        self.engine = engine
        self.main_window = main_window
        self.current_worker = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1280, 860)

        self.init_ui()
        self._setup_shortcuts()

        # 继承主窗口主题
        if main_window:
            self.setStyleSheet(main_window.styleSheet())

        self.refresh_target_list()
        self.refresh_mask_list()
        self.refresh_magic_ui()
        self.cb_log("开发者窗口已启动")

    def init_ui(self):
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

        self.title_bar = CustomTitleBar(self, title="\U0001f527 APLUSE ENGINE v3.4 - 开发者模式", show_theme=False)
        container_layout.addWidget(self.title_bar)

        dashboard_layout = QVBoxLayout()
        dashboard_layout.setContentsMargins(24, 20, 24, 24)
        dashboard_layout.setSpacing(16)

        # ==================== 顶行：密钥 + 状态 ====================
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        magic_card = QFrame()
        magic_card.setObjectName("card")
        m_layout = QVBoxLayout(magic_card)
        m_layout.setContentsMargins(20, 16, 20, 16)

        m_header = QHBoxLayout()
        m_header.addWidget(self.make_label("\U0001f511 核心密钥 (MAGIC WORD)", "cardTitle"))
        self.magic_info_label = self.make_label("当前状态：未加载", "subText")
        m_header.addStretch()
        m_header.addWidget(self.magic_info_label)
        m_layout.addLayout(m_header)

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
        top_row.addWidget(magic_card, 2)

        stat_card = QFrame()
        stat_card.setObjectName("card")
        stat_layout = QVBoxLayout(stat_card)
        stat_layout.setContentsMargins(20, 16, 20, 16)
        stat_layout.addWidget(self.make_label("\U0001f4e1 系统状态", "cardTitle"))
        self.status_label = self.make_label(f"持久化：\n{PathManager.get_persist_dir()}", "subText")
        self.status_label.setWordWrap(True)
        stat_layout.addWidget(self.status_label)
        stat_layout.addStretch()
        top_row.addWidget(stat_card, 1)

        dashboard_layout.addLayout(top_row)

        # ==================== 中行：目标 + 面具 ====================
        file_row = QHBoxLayout()
        file_row.setSpacing(16)

        # 目标卡片
        t_card = QFrame()
        t_card.setObjectName("card")
        t_layout = QVBoxLayout(t_card)
        t_layout.setContentsMargins(20, 16, 20, 16)

        t_header = QHBoxLayout()
        t_header.addWidget(self.make_label("\U0001f3af 目标执行队列", "cardTitle"))
        self.t_count_label = self.make_label("0 项", "badge")
        t_header.addWidget(self.t_count_label)
        t_header.addStretch()

        self.btn_t_add = self.make_btn("➕ 文件", "secondary")
        self.btn_t_add.clicked.connect(self.ui_select_targets)
        self.btn_t_add.setToolTip("Ctrl+O")
        self.btn_t_add_dir = self.make_btn("\U0001f4c1 目录", "secondary")
        self.btn_t_add_dir.clicked.connect(self.ui_select_target_folder)
        self.btn_t_rm = self.make_btn("➖ 移除", "secondary")
        self.btn_t_rm.clicked.connect(self.ui_rm_targets)
        self.btn_t_rm.setToolTip("Delete")
        self.btn_t_clr = self.make_btn("\U0001f5d1️ 清空", "danger")
        self.btn_t_clr.clicked.connect(self.ui_clr_targets)

        t_header.addWidget(self.btn_t_add)
        t_header.addWidget(self.btn_t_add_dir)
        t_header.addWidget(self.btn_t_rm)
        t_header.addWidget(self.btn_t_clr)
        t_layout.addLayout(t_header)

        self.target_list = CustomDropList("\U0001f4e5 拖拽目标文件/文件夹至此", "target", self)
        t_layout.addWidget(self.target_list)
        file_row.addWidget(t_card)

        # 面具卡片
        mask_card = QFrame()
        mask_card.setObjectName("card")
        mask_layout = QVBoxLayout(mask_card)
        mask_layout.setContentsMargins(20, 16, 20, 16)

        m_header2 = QHBoxLayout()
        m_header2.addWidget(self.make_label("\U0001f3ad 伪装面具图库", "cardTitle"))
        self.m_count_label = self.make_label("0 项", "badge")
        m_header2.addWidget(self.m_count_label)
        m_header2.addStretch()

        self.btn_m_add = self.make_btn("➕ 文件", "secondary")
        self.btn_m_add.clicked.connect(self.ui_select_masks)
        self.btn_m_add.setToolTip("Ctrl+Shift+O")
        self.btn_m_add_dir = self.make_btn("\U0001f4c1 目录", "secondary")
        self.btn_m_add_dir.clicked.connect(self.ui_select_mask_folder)
        self.btn_m_rm = self.make_btn("➖ 移除", "secondary")
        self.btn_m_rm.clicked.connect(self.ui_rm_masks)
        self.btn_m_rm.setToolTip("Delete")
        self.btn_m_clr = self.make_btn("\U0001f5d1️ 清空", "danger")
        self.btn_m_clr.clicked.connect(self.ui_clr_masks)

        m_header2.addWidget(self.btn_m_add)
        m_header2.addWidget(self.btn_m_add_dir)
        m_header2.addWidget(self.btn_m_rm)
        m_header2.addWidget(self.btn_m_clr)
        mask_layout.addLayout(m_header2)

        self.mask_list = CustomDropList("\U0001f5bc️ 拖拽面具文件/文件夹至此", "mask", self)
        mask_layout.addWidget(self.mask_list)
        file_row.addWidget(mask_card)

        dashboard_layout.addLayout(file_row, 1)

        # ==================== 底行：日志 + 操作 ====================
        bot_row = QHBoxLayout()
        bot_row.setSpacing(16)

        log_card = QFrame()
        log_card.setObjectName("card")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(20, 16, 20, 20)

        log_header = QHBoxLayout()
        log_header.addWidget(self.make_label("\U0001f4dd 运行日志", "cardTitle"))
        log_header.addStretch()
        log_layout.addLayout(log_header)

        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("terminal")
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)
        bot_row.addWidget(log_card, 2)

        act_card = QFrame()
        act_card.setObjectName("card")
        act_layout = QVBoxLayout(act_card)
        act_layout.setContentsMargins(20, 16, 20, 20)

        act_layout.addWidget(self.make_label("⚙️ 控制面板", "cardTitle"))

        prog_layout = QVBoxLayout()
        prog_layout.setSpacing(8)
        self.progress_label = self.make_label("等待任务指令...", "subText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("neonProgress")
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        prog_layout.addWidget(self.progress_label)
        prog_layout.addWidget(self.progress_bar)
        act_layout.addLayout(prog_layout)

        act_layout.addStretch()

        tools_layout = QGridLayout()
        tools_layout.setSpacing(12)

        self.btn_detect = self.make_btn("\U0001f50d 扫描分析队列", "secondary")
        self.btn_detect.clicked.connect(self.ui_detect)
        self.btn_detect.setToolTip("Ctrl+D")
        tools_layout.addWidget(self.btn_detect, 0, 0)

        self.btn_gen = self.make_btn("\U0001f4e6 恢复程序", "secondary")
        gen_menu = QMenu(self)
        gen_menu.addAction("\U0001fa99 Windows 恢复程序 (.exe)").triggered.connect(self.ui_gen_exe)
        gen_menu.addAction("\U0001f4f1 Android 恢复包 (.apk)").triggered.connect(self.ui_gen_apk)
        self.btn_gen.setMenu(gen_menu)
        tools_layout.addWidget(self.btn_gen, 0, 1)

        act_layout.addLayout(tools_layout)
        act_layout.addSpacing(12)

        mapping_layout = QHBoxLayout()
        mapping_layout.setSpacing(10)
        self.chk_rename_seq = QCheckBox("序号重命名 (1.mp4, 2.mp4 ...)")
        self.chk_rename_seq.setToolTip("伪装时把输出文件重命名为顺序序号")
        self.chk_disguise_mapping = QCheckBox("映射清单也伪装")
        self.chk_disguise_mapping.setToolTip("把原始名->伪装名 的映射文件一起伪装")
        mapping_layout.addWidget(self.chk_rename_seq)
        mapping_layout.addWidget(self.chk_disguise_mapping)
        mapping_layout.addStretch()
        act_layout.addLayout(mapping_layout)
        act_layout.addSpacing(8)

        self.btn_toggle = self.make_btn("⚡ 启动引擎", "primary")
        self.btn_toggle.setFixedHeight(50)
        self.btn_toggle.clicked.connect(self.ui_toggle)
        self.btn_toggle.setToolTip("Ctrl+Enter")
        font = self.btn_toggle.font()
        font.setBold(True)
        font.setPointSize(11)
        self.btn_toggle.setFont(font)

        act_layout.addWidget(self.btn_toggle)

        bot_row.addWidget(act_card, 1)
        dashboard_layout.addLayout(bot_row)

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
        item = QListWidgetItem(f"{filepath}    [{size_str}]")
        item.setData(Qt.UserRole, filepath)
        return item

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.ui_select_targets)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self).activated.connect(self.ui_select_masks)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._on_delete_key)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self.ui_detect)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.ui_toggle)

    def _on_delete_key(self):
        focused = self.focusWidget()
        if focused is self.target_list:
            self.ui_rm_targets()
        elif focused is self.mask_list:
            self.ui_rm_masks()

    # ── 日志与状态 ────────────────────────────────────────

    def cb_log(self, text):
        self.log_edit.append(f"> {text}")
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.main_window.log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {text}\n")
        except Exception:
            pass

    def cb_progress(self, curr, total, title, detail):
        self.progress_bar.setValue(0 if total <= 0 else int((curr / total) * 100))
        self.progress_label.setText(f"{title} | {detail}")

    def set_ui_busy(self, busy):
        controls = [
            self.btn_t_add, self.btn_t_add_dir, self.btn_t_rm, self.btn_t_clr,
            self.btn_detect, self.btn_m_add, self.btn_m_add_dir, self.btn_m_rm,
            self.btn_m_clr, self.btn_gen, self.magic_edit, self.btn_toggle,
        ]
        for c in controls:
            c.setEnabled(not busy)
        self.target_list.setEnabled(not busy)
        self.mask_list.setEnabled(not busy)
        self.btn_toggle.setText("⚡ 引擎高转速处理中..." if busy else "⚡ 启动引擎")

    # ── 密钥 ──────────────────────────────────────────────

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
        except Exception as e:
            QMessageBox.warning(self, "异常", str(e))

    def ui_reset_magic(self):
        self.engine.reset_magic()
        self.refresh_magic_ui()
        self.cb_log("已回退至出厂默认密钥")

    # ── 目标队列 ──────────────────────────────────────────

    def refresh_target_list(self):
        self.target_list.clear()
        for f in self.engine.target_files:
            self.target_list.addItem(self._make_file_item(f))
        t_count = len(self.engine.target_files)
        t_total = sum(Path(p).stat().st_size for p in self.engine.target_files if Path(p).is_file())
        ts = format_file_size(t_total) if t_total else ""
        self.t_count_label.setText(f"{t_count} 项" + (f"  {ts}" if ts else ""))

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
        if paths:
            self.ui_add_target_paths(paths)

    def ui_select_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择目标文件夹")
        if folder:
            self.ui_add_target_paths([folder])

    def ui_rm_targets(self):
        selected = self.target_list.selectedItems()
        if not selected:
            return
        sels = {i.data(Qt.UserRole) for i in selected}
        self.engine.target_files = [p for p in self.engine.target_files if p not in sels]
        self.refresh_target_list()
        self.cb_log(f"目标释放: -{len(sels)} 项")

    def ui_clr_targets(self):
        self.engine.target_files.clear()
        self.refresh_target_list()
        self.cb_log("目标队列已格式化")

    # ── 面具库 ────────────────────────────────────────────

    def refresh_mask_list(self):
        self.mask_list.clear()
        for f in self.engine.mask_library:
            self.mask_list.addItem(self._make_file_item(f))
        self.m_count_label.setText(f"{len(self.engine.mask_library)} 项")

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
        if paths:
            self.ui_add_mask_paths(paths)

    def ui_select_mask_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择面具文件夹")
        if folder:
            self.ui_add_mask_paths([folder])

    def ui_rm_masks(self):
        selected = self.mask_list.selectedItems()
        if not selected:
            return
        sels = {i.data(Qt.UserRole) for i in selected}
        self.engine.mask_library = [p for p in self.engine.mask_library if p not in sels]
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log(f"面具库清理: -{len(sels)} 项")

    def ui_clr_masks(self):
        self.engine.mask_library.clear()
        self.engine.save_config()
        self.refresh_mask_list()
        self.cb_log("外观面具库已格式化")

    # ── 异步任务 ──────────────────────────────────────────

    def _run_task(self, task_fn, done_cb):
        self.set_ui_busy(True)
        self.current_worker = EngineWorker(task_fn)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(done_cb)
        self.current_worker.err_sig.connect(self._on_err)
        self.current_worker.start()

    def _on_err(self, err_msg):
        self.set_ui_busy(False)
        self.cb_progress(0, 1, "系统崩溃", "ERR_FATAL")
        self.cb_log(f"[ERROR] 内核异常: {err_msg}")

    def ui_detect(self):
        if not self.engine.target_files:
            return self.cb_log("中断: 目标队列为空")

        def done(result):
            self.set_ui_busy(False)
            o, d, f = result
            self.cb_progress(1, 1, "分析完毕", f"原装:{o} | 伪装:{d} | 异常:{len(f)}")
            if f:
                for line in f:
                    self.cb_log(f"[WARN] {line}")

        self._run_task(self.engine.detect_status, done)

    def ui_toggle(self):
        if not self.engine.target_files:
            return self.cb_log("中断: 目标队列为空")
        count = len(self.engine.target_files)
        reply = QMessageBox.question(
            self, "确认执行",
            f"即将对 {count} 个文件执行自动伪装/还原操作。\n\n确定继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.engine.rename_mapping = self.chk_rename_seq.isChecked()
        self.engine.disguise_mapping_txt = self.chk_disguise_mapping.isChecked()
        if self.engine.rename_mapping:
            mapping_dir = self.engine.get_common_target_parent_dir()
            self.engine.mapping_output_path = str(mapping_dir / "mapping.txt")
        else:
            self.engine.mapping_output_path = None

        def done(result):
            self.set_ui_busy(False)
            s, f = result
            self.refresh_target_list()
            self.cb_progress(1, 1, "引擎挂起", f"成功:{s} | 失败:{len(f)}")
            self.cb_log(f"执行周期结束。成功:{s} 失败:{len(f)}")

        self._run_task(self.engine.handle_toggle, done)

    def ui_gen_exe(self):
        try:
            out_dir = self.engine.get_common_target_parent_dir()
        except Exception as e:
            return self.cb_log(f"中断: {e}")

        def done(p):
            self.set_ui_busy(False)
            self.cb_progress(1, 1, "编译完成", str(Path(p).parent))
            self.cb_log(f"脱壳包导出成功: {p}")

        self._run_task(lambda pcb, lcb: self.engine.generate_restore_exe(out_dir, lcb), done)

    def ui_gen_apk(self):
        try:
            out_dir = self.engine.get_common_target_parent_dir()
        except Exception as e:
            return self.cb_log(f"中断: {e}")

        def done(r):
            self.set_ui_busy(False)
            self.cb_progress(1, 1, "安卓恢复包", str(r))
            if Path(r).is_file():
                self.cb_log(f"安卓恢复包已生成: {r}")
            else:
                self.cb_log(f"Android 项目已生成，请用 Android Studio 打开编译: {r}")

        self._run_task(lambda pcb, lcb: self.engine.generate_restore_apk(out_dir, lcb), done)
