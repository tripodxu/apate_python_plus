from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QFileDialog, QShortcut,
    QTextEdit, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit,
    QFrame, QProgressBar, QGraphicsDropShadowEffect, QCheckBox,
)

from core import (
    DisguiseEngine, DisguiseError, collect_files_from_paths,
    PathManager, magic_to_display_text, format_file_size,
)
from themes import PALETTES, THEME_NAMES, build_qss, parse_shadow_color
from ui import EngineWorker, CustomTitleBar, CustomDropList


class AdminWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = DisguiseEngine()
        self.current_worker = None

        self.log_file_path = PathManager.get_persist_dir() / "apluse.log"

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1280, 860)

        self._init_ui()
        self._setup_shortcuts()

        saved_theme = self.engine.config.get("theme_index", 0)
        self.title_bar.theme_combo.setCurrentIndex(saved_theme)
        self.change_theme(saved_theme)

        self.cb_log("伪装管理员模式已启动")

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        self.container = QFrame()
        self.container.setObjectName("mainContainer")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self, title="🔒 APLUSE ADMIN - 伪装模式", show_dev_btn=False)
        container_layout.addWidget(self.title_bar)

        dashboard = QVBoxLayout()
        dashboard.setContentsMargins(24, 20, 24, 24)
        dashboard.setSpacing(16)

        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(self._build_magic_card(), 2)
        top.addWidget(self._build_status_card(), 1)
        dashboard.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(16)
        mid.addWidget(self._build_target_card())
        mid.addWidget(self._build_mask_card())
        dashboard.addLayout(mid, 1)

        bot = QHBoxLayout()
        bot.setSpacing(16)
        bot.addWidget(self._build_log_card(), 2)
        bot.addWidget(self._build_action_card(), 1)
        dashboard.addLayout(bot)

        container_layout.addLayout(dashboard)
        root.addWidget(self.container)

    def _build_magic_card(self):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 16, 20, 16)
        h = QHBoxLayout(); h.addWidget(self._label("🔑 核心钥匙", "cardTitle")); h.addStretch(); v.addLayout(h)

        row = QHBoxLayout()
        self.magic_edit = QLineEdit(); self.magic_edit.setObjectName("neonInput"); self.magic_edit.setPlaceholderText("输入 ASCII 或 HEX 密钥...")
        row.addWidget(self.magic_edit, 1)
        for text, slot, role in [("应用", self.ui_apply_magic, "accent"), ("随机", self.ui_rand_magic, "secondary"), ("默认", self.ui_reset_magic, "danger")]:
            b = self._btn(text, role); b.clicked.connect(slot); row.addWidget(b)
        v.addLayout(row)
        return card

    def _build_status_card(self):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 16, 20, 16)
        v.addWidget(self._label("📡 系统状态", "cardTitle"))
        self.status_label = self._label(f"持久化目录：\n{PathManager.get_persist_dir()}", "subText"); self.status_label.setWordWrap(True)
        v.addWidget(self.status_label); v.addStretch()
        return card

    def _build_target_card(self):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 16, 20, 16)
        h = QHBoxLayout(); h.addWidget(self._label("🎯 目标执行队列", "cardTitle")); h.addStretch()
        for text, slot, tip in [("➕ 文件", self.ui_select_targets, "Ctrl+O"), ("📁 目录", self.ui_select_target_folder, ""), ("🗑️ 清空", self.ui_clear_targets, "")]:
            b = self._btn(text, "secondary"); b.clicked.connect(slot); b.setToolTip(tip); h.addWidget(b)
        v.addLayout(h)
        self.target_list = CustomDropList("📥 拖入待处理目标文件", "target", self)
        v.addWidget(self.target_list)
        return card

    def _build_mask_card(self):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 16, 20, 16)
        h = QHBoxLayout(); h.addWidget(self._label("🎭 面具文件库", "cardTitle")); h.addStretch()
        for text, slot, tip in [("➕ 文件", self.ui_select_masks, "Ctrl+Shift+O"), ("📁 目录", self.ui_select_mask_folder, ""), ("🗑️ 清空", self.ui_clear_masks, "")]:
            b = self._btn(text, "secondary"); b.clicked.connect(slot); b.setToolTip(tip); h.addWidget(b)
        v.addLayout(h)
        self.mask_list = CustomDropList("🖼️ 拖入伪装载体文件", "mask", self)
        v.addWidget(self.mask_list)
        return card

    def _build_log_card(self):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 16, 20, 16)
        v.addWidget(self._label("📝 运行日志", "cardTitle"))
        self.log_edit = QTextEdit(); self.log_edit.setObjectName("terminal"); self.log_edit.setReadOnly(True)
        v.addWidget(self.log_edit)
        return card

    def _build_action_card(self):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 16, 20, 16)
        v.addWidget(self._label("🚨 控制面板", "cardTitle"))

        self.progress_label = self._label("等待任务指令...", "subText")
        self.progress_bar = QProgressBar(); self.progress_bar.setObjectName("neonProgress"); self.progress_bar.setFixedHeight(6); self.progress_bar.setTextVisible(False); self.progress_bar.setRange(0, 100)
        v.addWidget(self.progress_label); v.addWidget(self.progress_bar)

        self.chk_rename = QCheckBox("序号重命名 (1.mp4, 2.mp4 ...)")
        self.chk_rename.setToolTip("伪装后按队列顺序重新编号输出文件")
        self.chk_mapping = QCheckBox("同时伪装映射清单")
        self.chk_mapping.setToolTip("把 原始名->伪装名 的 mapping 文件也进行伪装")
        v.addWidget(self.chk_rename)
        v.addWidget(self.chk_mapping)

        self.btn_detect = self._btn("🔍 扫描分析队列", "secondary"); self.btn_detect.clicked.connect(self.ui_detect); self.btn_detect.setToolTip("Ctrl+D"); v.addWidget(self.btn_detect)

        self.btn_start = self._btn("🚀 启动引擎", "primary"); self.btn_start.setFixedHeight(50); self.btn_start.clicked.connect(self.ui_toggle); self.btn_start.setToolTip("Ctrl+Enter"); v.addWidget(self.btn_start)
        return card

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self, self.ui_select_targets)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, self.ui_select_masks)
        QShortcut(QKeySequence("Delete"), self, self._delete_selected)
        QShortcut(QKeySequence("Ctrl+D"), self, self.ui_detect)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.ui_toggle)

    def change_theme(self, idx):
        if 0 <= idx < len(PALETTES):
            p = PALETTES[idx]
            self.setStyleSheet(build_qss(p))
            eff = self.container.graphicsEffect()
            rgba = parse_shadow_color(p.get("SHADOW", "rgba(0,0,0,80)"))
            if eff and rgba:
                eff.setColor(QColor(*rgba))
            self.engine.config["theme_index"] = idx
            self.engine.save_config()

    def cb_log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_edit.append(line)
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def cb_progress(self, cur, total, title, detail):
        self.progress_label.setText(f"{title} {detail}")
        self.progress_bar.setValue(int(cur / total * 100) if total else 0)

    def ui_apply_magic(self):
        raw = self.magic_edit.text().strip()
        if not raw:
            return QMessageBox.warning(self, "提示", "请输入钥匙内容")
        try:
            magic = self.engine.parse_and_set_magic(raw)
            self.cb_log(f"钥匙已应用: {magic_to_display_text(magic)}")
        except DisguiseError as e:
            QMessageBox.warning(self, "铸造失败", str(e))

    def ui_rand_magic(self):
        magic = self.engine.generate_random_magic()
        self.magic_edit.setText(magic.hex())
        self.cb_log(f"已生成随机钥匙: {magic_to_display_text(magic)}")

    def ui_reset_magic(self):
        magic = self.engine.reset_magic()
        self.magic_edit.setText(magic.hex())
        self.cb_log(f"已恢复默认钥匙: {magic_to_display_text(magic)}")

    def ui_add_target_paths(self, paths):
        before = len(self.engine.target_files)
        self.engine.target_files.extend(collect_files_from_paths(paths))
        self.engine.target_files = list(dict.fromkeys(self.engine.target_files))
        added = len(self.engine.target_files) - before
        self.cb_log(f"目标队列新增 {added} 个文件")
        self._refresh_targets()

    def ui_add_mask_paths(self, paths):
        before = set(self.engine.mask_library)
        for p in collect_files_from_paths(paths):
            if p not in self.engine.mask_library:
                self.engine.mask_library.append(p)
        added = len(set(self.engine.mask_library) - before)
        self.engine.save_config()
        self.cb_log(f"面具库新增 {added} 个文件")
        self._refresh_masks()

    def ui_select_targets(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择目标文件", "", "所有文件 (*)")
        if paths:
            self.ui_add_target_paths(paths)

    def ui_select_target_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if d:
            self.ui_add_target_paths([d])

    def ui_clear_targets(self):
        self.engine.target_files.clear()
        self._refresh_targets()

    def ui_select_masks(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择面具文件", "", "视频/图片 (*.mp4 *.jpg *.png *.bmp *.mkv *.avi *.mov);;所有文件 (*)")
        if paths:
            self.ui_add_mask_paths(paths)

    def ui_select_mask_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择面具目录")
        if d:
            self.ui_add_mask_paths([d])

    def ui_clear_masks(self):
        self.engine.mask_library.clear()
        self.engine.save_config()
        self._refresh_masks()

    def _refresh_targets(self):
        self.target_list.clear()
        for p in self.engine.target_files:
            self.target_list.addItem(f"{Path(p).name}  ({format_file_size(Path(p).stat().st_size)})")

    def _refresh_masks(self):
        self.mask_list.clear()
        for p in self.engine.mask_library:
            self.mask_list.addItem(f"{Path(p).name}  ({format_file_size(Path(p).stat().st_size)})")

    def _delete_selected(self):
        sel = [self.target_list.item(i).text().split("  (")[0] for i in range(self.target_list.count()) if self.target_list.item(i).isSelected()]
        if sel:
            self.engine.target_files = [p for p in self.engine.target_files if Path(p).name not in sel]
            self._refresh_targets()
            return
        sel = [self.mask_list.item(i).text().split("  (")[0] for i in range(self.mask_list.count()) if self.mask_list.item(i).isSelected()]
        if sel:
            keep = []
            for p in self.engine.mask_library:
                if Path(p).name not in sel:
                    keep.append(p)
            self.engine.mask_library = keep
            self.engine.save_config()
            self._refresh_masks()

    def ui_detect(self):
        if not self.engine.target_files:
            return self.cb_log("中断：目标队列为空")
        try:
            def done(res):
                self.set_ui_busy(False)
                o, d, f = res
                self.cb_progress(1, 1, "扫描完成", f"原始:{o} 已伪装:{d} 失败:{len(f)}")
                self.cb_log(f"检测完成 原始:{o} 已伪装:{d} 失败:{len(f)}")
            self._run_task(self.engine.detect_status, done)
        except Exception as e:
            self.cb_log(f"检测失败: {e}")

    def ui_toggle(self):
        if not self.engine.target_files:
            return self.cb_log("中断：目标队列为空")
        reply = QMessageBox.question(
            self, "确认执行",
            f"即将对 {len(self.engine.target_files)} 个文件执行自动伪装/还原。\n\n确定继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.engine.rename_mapping = self.chk_rename.isChecked()
        self.engine.disguise_mapping_txt = self.chk_mapping.isChecked()
        if self.engine.rename_mapping:
            mapping_dir = self.engine.get_common_target_parent_dir()
            self.engine.mapping_output_path = str(mapping_dir / "mapping.txt")
        else:
            self.engine.mapping_output_path = None

        def done(res):
            self.set_ui_busy(False)
            s, f = res
            self._refresh_targets()
            self.cb_progress(1, 1, "引擎挂起", f"成功:{s} | 失败:{len(f)}")
            self.cb_log(f"执行周期结束。成功 {s} 失败 {len(f)}")

        self._run_task(self.engine.handle_toggle, done)

    def _run_task(self, task_fn, done_cb):
        self.set_ui_busy(True)
        self.current_worker = EngineWorker(task_fn)
        self.current_worker.log_sig.connect(self.cb_log)
        self.current_worker.prog_sig.connect(self.cb_progress)
        self.current_worker.done_sig.connect(done_cb)
        self.current_worker.err_sig.connect(lambda e: (self.set_ui_busy(False), self.cb_log(f"任务异常: {e}")))
        self.current_worker.start()

    def set_ui_busy(self, busy):
        for w in [
            self.btn_detect, self.btn_start,
            self.chk_rename, self.chk_mapping,
        ]:
            w.setEnabled(not busy)
        self.btn_start.setText("🚀 引擎高速处理中..." if busy else "🚀 启动引擎")

    def _label(self, text, obj_name="subText"):
        lb = QLabel(text); lb.setObjectName(obj_name); return lb

    def _btn(self, text, role="secondary"):
        b = QPushButton(text); b.setProperty("role", role); return b
