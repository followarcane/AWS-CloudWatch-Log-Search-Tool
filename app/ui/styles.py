APP_STYLESHEET = """
QWidget {
    background-color: #1e1f22;
    color: #e8e8e8;
    font-family: "Helvetica Neue", "Segoe UI", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1e1f22;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QListView, QTreeWidget {
    background-color: #2b2d31;
    border: 1px solid #3f4147;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #3d5a80;
    min-height: 28px;
}
QSpinBox {
    padding-right: 4px;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {
    border: 1px solid #5b8def;
}
QPushButton {
    background-color: #3d5a80;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #4a6fa5;
}
QPushButton:disabled {
    background-color: #3a3a3a;
    color: #888888;
}
QPushButton#dangerButton {
    background-color: #8b3a3a;
}
QPushButton#dangerButton:hover {
    background-color: #a44848;
}
QPushButton#ghostButton {
    background-color: #2b2d31;
    border: 1px solid #3f4147;
    font-weight: 500;
}
QTabWidget::pane {
    border: 1px solid #3f4147;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background: #2b2d31;
    color: #9a9a9a;
    padding: 8px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #36393f;
    color: #ffffff;
}
QSplitter::handle {
    background: #3f4147;
}
QStatusBar {
    background: #16171a;
    color: #a0a0a0;
}
QProgressBar {
    border: 1px solid #3f4147;
    border-radius: 4px;
    background: #2b2d31;
    text-align: center;
    max-height: 12px;
}
QProgressBar::chunk {
    background: #5b8def;
    border-radius: 3px;
}
QCheckBox, QLabel {
    background: transparent;
}
QGroupBox {
    border: 1px solid #3f4147;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #b0b0b0;
}
QListView {
    outline: none;
}
QListView::item {
    padding: 4px;
    border-bottom: 1px solid #2f3136;
}
QListView::item:selected {
    background: #3d5a80;
}
QScrollBar:vertical {
    background: #1e1f22;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #4a4d55;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QMenuBar {
    background: #16171a;
}
QMenuBar::item:selected {
    background: #2b2d31;
}
QMenu {
    background: #2b2d31;
    border: 1px solid #3f4147;
}
QMenu::item:selected {
    background: #3d5a80;
}
"""

LEVEL_COLORS = {
    "ERROR": "#ff6b6b",
    "WARN": "#f0a500",
    "INFO": "#51cf66",
    "DEBUG": "#74c0fc",
    "UNKNOWN": "#adb5bd",
}
