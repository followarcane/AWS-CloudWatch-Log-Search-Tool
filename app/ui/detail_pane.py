from __future__ import annotations

from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QHBoxLayout

from app.core.models import LogEntry
from app.ui.styles import LEVEL_COLORS


class DetailPane(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.meta_label = QLabel("Select a log to inspect")
        self.meta_label.setWordWrap(True)
        header.addWidget(self.meta_label)
        layout.addLayout(header)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        mono = QFont("SF Mono", 12)
        if not mono.exactMatch():
            mono = QFont("Menlo", 12)
        self.text.setFont(mono)
        layout.addWidget(self.text)

        self._search_term = ""
        self._filter_term = ""
        self._highlight_search = True
        self._highlight_filter = True

    def set_highlight_options(self, search: bool, filter_: bool) -> None:
        self._highlight_search = search
        self._highlight_filter = filter_

    def set_terms(self, search_term: str = "", filter_term: str = "") -> None:
        self._search_term = search_term or ""
        self._filter_term = filter_term or ""

    def show_entry(self, entry: LogEntry | None) -> None:
        if entry is None:
            self.meta_label.setText("Select a log to inspect")
            self.text.setPlainText("")
            return

        color = LEVEL_COLORS.get(entry.level.value, LEVEL_COLORS["UNKNOWN"])
        self.meta_label.setText(
            f'<span style="color:{color};font-weight:600">[{entry.level.value}]</span> '
            f'<span style="color:#8be9fd">{entry.timestamp}</span><br>'
            f'<span style="color:#9a9a9a">{entry.log_group}</span>'
        )
        self.text.setPlainText(entry.pretty_message())
        self._apply_highlights()

    def show_message(self, title: str, body: str) -> None:
        self.meta_label.setText(title)
        self.text.setPlainText(body)

    def _apply_highlights(self) -> None:
        if self._highlight_search and self._search_term:
            self._highlight(self._search_term, QColor("#aa0000"), QColor("#ffffff"))
        if self._highlight_filter and self._filter_term:
            self._highlight(self._filter_term, QColor("#aaaa00"), QColor("#000000"))

    def _highlight(self, needle: str, bg: QColor, fg: QColor) -> None:
        if not needle:
            return
        fmt = QTextCharFormat()
        fmt.setBackground(bg)
        fmt.setForeground(fg)

        doc = self.text.document()
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(needle, cursor)
            if cursor.isNull():
                break
            cursor.mergeCharFormat(fmt)
