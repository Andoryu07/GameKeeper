"""Colours and the application stylesheet."""

BG = "#0f1218"
PANEL = "#161b24"
PANEL_2 = "#1d2430"
BORDER = "#2a3342"
TEXT = "#e6e9ef"
MUTED = "#8a94a6"
ACCENT = "#4f8cff"
ACCENT_2 = "#3a73e0"
GOLD = "#f2c14e"
GREEN = "#3fbf7f"
DANGER = "#e05a5a"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}

#Sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
#Sidebar QLabel#Brand {{ font-size: 18px; font-weight: 700; padding: 18px 16px 10px 16px; background: transparent; }}
#SectionLabel {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; padding: 12px 16px 4px 16px; background: transparent; }}

QListWidget#Categories {{ background: transparent; border: none; outline: none; }}
QListWidget#Categories::item {{ padding: 7px 14px; border-radius: 6px; margin: 1px 8px; }}
QListWidget#Categories::item:hover {{ background: {PANEL_2}; }}
QListWidget#Categories::item:selected {{ background: {ACCENT}; color: white; }}

QLineEdit, QSpinBox, QPlainTextEdit, QComboBox {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL_2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; }}

QPushButton {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 7px 14px;
}}
QPushButton:hover {{ background: #263041; }}
QPushButton:pressed {{ background: #1a212c; }}
QPushButton:disabled {{ color: #59627a; }}
QPushButton#Primary {{ background: {ACCENT}; border: none; color: white; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_2}; }}
QPushButton#Play {{
    background: {GREEN}; border: none; color: white; font-size: 16px; font-weight: 700;
    padding: 10px 34px; border-radius: 8px;
}}
QPushButton#Play:hover {{ background: #35a96f; }}
QPushButton#Play:disabled {{ background: #2b5d46; color: #cfe; }}
QPushButton#Flat {{ background: transparent; border: none; color: {MUTED}; text-align: left; padding: 8px 16px; }}
QPushButton#Flat:hover {{ color: {TEXT}; }}

QListView#Grid {{ background: {BG}; border: none; outline: none; }}
QListWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; outline: none; }}
QListWidget::item {{ padding: 6px; }}
QListWidget::item:selected {{ background: {ACCENT}; color: white; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a465a; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; }}

QProgressBar {{ background: {PANEL_2}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {GOLD}; border-radius: 4px; }}

QMenu {{ background: {PANEL_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 14px; border: none; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

#Segmented {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 8px; }}
#Segmented QPushButton {{ background: transparent; border: none; border-radius: 6px; padding: 5px 12px; color: {MUTED}; }}
#Segmented QPushButton:hover {{ color: {TEXT}; }}
#Segmented QPushButton:checked {{ background: {ACCENT}; color: white; font-weight: 600; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: white; }}
QSlider {{ background: transparent; }}

QCheckBox::indicator, QListWidget::indicator {{
    width: 15px; height: 15px; border: 1px solid #4a5568; border-radius: 4px; background: {PANEL_2};
}}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:hover, QListWidget::indicator:hover {{ border-color: {ACCENT}; }}
QDialog {{ background: {BG}; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED}; }}
"""
