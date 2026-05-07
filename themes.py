"""
APLUSE ENGINE - 主题配置模块
将主题配色数据与 QSS 模板分离，便于维护和扩展。
"""

# 主题名称列表（与 palettes 列表索引一一对应）
THEME_NAMES = [
    "暗色极客",
    "亮色极简",
    "渐变幽蓝",
    "暗金奢华",
    "猛男猛粉",
    "辐射废土",
    "低调暗紫",
]

# 主题配色方案列表
PALETTES = [
    {  # 0: 暗色极客 (Zinc Theme)
        "BG_MAIN": "#09090B", "BG_CARD": "#121217", "BORDER": "#27272A",
        "TEXT_MAIN": "#F4F4F5", "TEXT_SUB": "#A1A1AA", "TEXT_TITLE": "#A1A1AA",
        "BTN_SEC": "#27272A", "BTN_SEC_HOVER": "#3F3F46", "BTN_SEC_TEXT": "#E4E4E7",
        "PRI_START": "#2563EB", "PRI_END": "#6D28D9", "PRI_H_START": "#3B82F6", "PRI_H_END": "#8B5CF6",
        "LIST_BG": "#09090B", "LIST_ITEM": "#18181B", "LIST_HOVER": "#27272A", "LIST_SEL": "#1D4ED8",
        "TERM_BG": "#000000", "TERM_TEXT": "#10B981", "SHADOW": "rgba(0,0,0,150)",
        "DIS_BG": "rgba(255, 255, 255, 0.06)", "DIS_TEXT": "rgba(255, 255, 255, 0.35)",
        "DIS_BORDER": "rgba(255, 255, 255, 0.15)", "DIS_PRI_BG": "rgba(255, 255, 255, 0.12)",
        "INPUT_DIS_BG": "rgba(255, 255, 255, 0.03)",
    },
    {  # 1: 亮色极简 (Light Theme)
        "BG_MAIN": "#F3F4F6", "BG_CARD": "#FFFFFF", "BORDER": "#D1D5DB",
        "TEXT_MAIN": "#111827", "TEXT_SUB": "#6B7280", "TEXT_TITLE": "#1F2937",
        "BTN_SEC": "#F3F4F6", "BTN_SEC_HOVER": "#E5E7EB", "BTN_SEC_TEXT": "#374151",
        "PRI_START": "#3B82F6", "PRI_END": "#8B5CF6", "PRI_H_START": "#60A5FA", "PRI_H_END": "#A78BFA",
        "LIST_BG": "#F9FAFB", "LIST_ITEM": "#FFFFFF", "LIST_HOVER": "#F3F4F6", "LIST_SEL": "#3B82F6",
        "TERM_BG": "#F8FAFC", "TERM_TEXT": "#0284C7", "SHADOW": "rgba(0,0,0,30)",
        "DIS_BG": "rgba(0, 0, 0, 0.04)", "DIS_TEXT": "rgba(0, 0, 0, 0.35)",
        "DIS_BORDER": "rgba(0, 0, 0, 0.15)", "DIS_PRI_BG": "rgba(0, 0, 0, 0.08)",
        "INPUT_DIS_BG": "rgba(0, 0, 0, 0.02)",
    },
    {  # 2: 渐变幽蓝 (Cyan/Blue Theme)
        "BG_MAIN": "#0B1120", "BG_CARD": "#1E293B", "BORDER": "#0EA5E9",
        "TEXT_MAIN": "#F0F9FF", "TEXT_SUB": "#94A3B8", "TEXT_TITLE": "#38BDF8",
        "BTN_SEC": "#0F172A", "BTN_SEC_HOVER": "#1E293B", "BTN_SEC_TEXT": "#BAE6FD",
        "PRI_START": "#0284C7", "PRI_END": "#2563EB", "PRI_H_START": "#0EA5E9", "PRI_H_END": "#3B82F6",
        "LIST_BG": "#0B1120", "LIST_ITEM": "#0F172A", "LIST_HOVER": "#1E293B", "LIST_SEL": "#0284C7",
        "TERM_BG": "#020617", "TERM_TEXT": "#38BDF8", "SHADOW": "rgba(2,132,199,80)",
        "DIS_BG": "rgba(255, 255, 255, 0.06)", "DIS_TEXT": "rgba(255, 255, 255, 0.4)",
        "DIS_BORDER": "rgba(255, 255, 255, 0.2)", "DIS_PRI_BG": "rgba(255, 255, 255, 0.15)",
        "INPUT_DIS_BG": "rgba(255, 255, 255, 0.05)",
    },
    {  # 3: 暗金奢华 (Dark Gold Theme)
        "BG_MAIN": "#18181B", "BG_CARD": "#27272A", "BORDER": "#B45309",
        "TEXT_MAIN": "#FEF08A", "TEXT_SUB": "#D4AF37", "TEXT_TITLE": "#FDE68A",
        "BTN_SEC": "#3F3F46", "BTN_SEC_HOVER": "#52525B", "BTN_SEC_TEXT": "#FEF08A",
        "PRI_START": "#B45309", "PRI_END": "#D97706", "PRI_H_START": "#D97706", "PRI_H_END": "#F59E0B",
        "LIST_BG": "#18181B", "LIST_ITEM": "#27272A", "LIST_HOVER": "#3F3F46", "LIST_SEL": "#B45309",
        "TERM_BG": "#09090B", "TERM_TEXT": "#FBBF24", "SHADOW": "rgba(180,83,9,80)",
        "DIS_BG": "rgba(255, 255, 255, 0.04)", "DIS_TEXT": "rgba(212, 175, 55, 0.4)",
        "DIS_BORDER": "rgba(180, 83, 9, 0.3)", "DIS_PRI_BG": "rgba(180, 83, 9, 0.15)",
        "INPUT_DIS_BG": "rgba(255, 255, 255, 0.02)",
    },
    {  # 4: 猛男猛粉 (Cyber Pink)
        "BG_MAIN": "#1A0B13", "BG_CARD": "#2A1220", "BORDER": "#DB2777",
        "TEXT_MAIN": "#FCE7F3", "TEXT_SUB": "#F472B6", "TEXT_TITLE": "#F9A8D4",
        "BTN_SEC": "#37172A", "BTN_SEC_HOVER": "#501E3C", "BTN_SEC_TEXT": "#FBCFE8",
        "PRI_START": "#DB2777", "PRI_END": "#9D174D", "PRI_H_START": "#F472B6", "PRI_H_END": "#BE185D",
        "LIST_BG": "#1A0B13", "LIST_ITEM": "#2A1220", "LIST_HOVER": "#37172A", "LIST_SEL": "#DB2777",
        "TERM_BG": "#0D0509", "TERM_TEXT": "#F9A8D4", "SHADOW": "rgba(219,39,119,80)",
        "DIS_BG": "rgba(255, 255, 255, 0.05)", "DIS_TEXT": "rgba(244, 114, 182, 0.5)",
        "DIS_BORDER": "rgba(219, 39, 119, 0.3)", "DIS_PRI_BG": "rgba(219, 39, 119, 0.15)",
        "INPUT_DIS_BG": "rgba(255, 255, 255, 0.03)",
    },
    {  # 5: 辐射废土 (Wasteland)
        "BG_MAIN": "#292524", "BG_CARD": "#44403C", "BORDER": "#84CC16",
        "TEXT_MAIN": "#D6D3D1", "TEXT_SUB": "#A8A29E", "TEXT_TITLE": "#BEF264",
        "BTN_SEC": "#57534E", "BTN_SEC_HOVER": "#78716C", "BTN_SEC_TEXT": "#E7E5E4",
        "PRI_START": "#65A30D", "PRI_END": "#4D7C0F", "PRI_H_START": "#84CC16", "PRI_H_END": "#65A30D",
        "LIST_BG": "#292524", "LIST_ITEM": "#44403C", "LIST_HOVER": "#57534E", "LIST_SEL": "#65A30D",
        "TERM_BG": "#1C1917", "TERM_TEXT": "#84CC16", "SHADOW": "rgba(101,163,13,60)",
        "DIS_BG": "rgba(0, 0, 0, 0.2)", "DIS_TEXT": "rgba(168, 162, 158, 0.5)",
        "DIS_BORDER": "rgba(101, 163, 13, 0.2)", "DIS_PRI_BG": "rgba(101, 163, 13, 0.1)",
        "INPUT_DIS_BG": "rgba(0, 0, 0, 0.3)",
    },
    {  # 6: 低调暗紫 (Dark Violet)
        "BG_MAIN": "#0F0B15", "BG_CARD": "#1B1429", "BORDER": "#7C3AED",
        "TEXT_MAIN": "#F5F3FF", "TEXT_SUB": "#A78BFA", "TEXT_TITLE": "#DDD6FE",
        "BTN_SEC": "#2E2244", "BTN_SEC_HOVER": "#3F2E5E", "BTN_SEC_TEXT": "#EDE9FE",
        "PRI_START": "#7C3AED", "PRI_END": "#5B21B6", "PRI_H_START": "#8B5CF6", "PRI_H_END": "#6D28D9",
        "LIST_BG": "#0F0B15", "LIST_ITEM": "#1B1429", "LIST_HOVER": "#2E2244", "LIST_SEL": "#7C3AED",
        "TERM_BG": "#09060D", "TERM_TEXT": "#C4B5FD", "SHADOW": "rgba(124,58,237,70)",
        "DIS_BG": "rgba(255, 255, 255, 0.04)", "DIS_TEXT": "rgba(167, 139, 250, 0.5)",
        "DIS_BORDER": "rgba(124, 58, 237, 0.3)", "DIS_PRI_BG": "rgba(124, 58, 237, 0.15)",
        "INPUT_DIS_BG": "rgba(255, 255, 255, 0.02)",
    },
]


def build_qss(p: dict) -> str:
    """根据配色字典生成完整的 QSS 样式表。"""
    return f"""
        QWidget {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 13px; color: {p['TEXT_MAIN']}; }}

        ::selection {{ background-color: {p['PRI_H_START']}; color: white; }}

        QFrame#mainContainer {{ background-color: {p['BG_MAIN']}; border: 1px solid {p['BORDER']}; border-radius: 12px; }}
        QFrame#titleBar {{ background-color: {p['BG_MAIN']}; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: 1px solid {p['BORDER']}; }}
        QLabel#titleLabel {{ color: {p['TEXT_TITLE']}; font-size: 12px; font-weight: bold; letter-spacing: 1px; }}

        QPushButton#toolboxHeader {{
            background: {p['BG_CARD']}; color: {p['TEXT_SUB']}; border: 1px solid {p['BORDER']};
            border-radius: 8px; text-align: left; padding: 6px 14px; font-size: 13px; font-weight: 600;
        }}
        QPushButton#toolboxHeader:hover {{ background: {p['LIST_HOVER']}; color: {p['TEXT_MAIN']}; }}
        QFrame#toolboxContent {{ background: {p['BG_CARD']}; border: 1px solid {p['BORDER']}; border-top: none; border-radius: 0 0 8px 8px; }}

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

        QPushButton {{ border: none; border-radius: 6px; padding: 8px 14px; font-weight: 600; }}

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


def parse_shadow_color(shadow_str: str):
    """从 rgba 字符串中解析 QColor 参数，返回 (r, g, b, a) 或 None。"""
    rgb = shadow_str.replace("rgba(", "").replace(")", "").split(",")
    if len(rgb) == 4:
        return int(rgb[0]), int(rgb[1]), int(rgb[2]), int(rgb[3])
    return None
