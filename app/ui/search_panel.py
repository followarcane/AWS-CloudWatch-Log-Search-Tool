from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QGroupBox,
    QSizePolicy,
)


class SearchPanel(QWidget):
    search_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    env_changed = pyqtSignal(str)
    filter_changed = pyqtSignal(str)
    path_filter_changed = pyqtSignal()

    TIME_PRESETS = [
        ("1 hour", "1"),
        ("3 hours", "3"),
        ("6 hours", "6"),
        ("12 hours", "12"),
        ("24 hours", "24"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # Env
        env_row = QHBoxLayout()
        env_row.addWidget(QLabel("Env"))
        self.env_combo = QComboBox()
        self.env_combo.currentTextChanged.connect(self.env_changed.emit)
        env_row.addWidget(self.env_combo, 1)
        root.addLayout(env_row)

        # Query
        root.addWidget(QLabel("Search"))
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("CloudWatch filter text…")
        self.query_edit.returnPressed.connect(self.search_requested.emit)
        root.addWidget(self.query_edit)

        # Time
        root.addWidget(QLabel("Start time"))
        self.time_combo = QComboBox()
        self.time_combo.setEditable(True)
        for label, value in self.TIME_PRESETS:
            self.time_combo.addItem(label, value)
        self.time_combo.setCurrentIndex(0)
        self.time_combo.lineEdit().setPlaceholderText("26.09.2026 16:00  |  1  |  3h")
        self.time_combo.lineEdit().returnPressed.connect(self.search_requested.emit)
        root.addWidget(self.time_combo)
        hint = QLabel("Hours ago, or any date/time (26.09.2026, 26/09/2026 16:00, …)")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#888;font-size:11px;")
        root.addWidget(hint)

        # Buttons
        btn_row = QHBoxLayout()
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.search_requested.emit)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        btn_row.addWidget(self.search_btn)
        btn_row.addWidget(self.stop_btn)
        root.addLayout(btn_row)

        # Client text filter
        root.addWidget(QLabel("Filter results"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Client-side filter…")
        self.filter_edit.textChanged.connect(self.filter_changed.emit)
        root.addWidget(self.filter_edit)

        # Path filter (multi) — results-side filter
        path_filter_box = QGroupBox("Path filter")
        pf_layout = QVBoxLayout(path_filter_box)
        pf_btns = QHBoxLayout()
        self.path_filter_all_btn = QPushButton("Select all")
        self.path_filter_all_btn.setObjectName("ghostButton")
        self.path_filter_none_btn = QPushButton("Select none")
        self.path_filter_none_btn.setObjectName("ghostButton")
        pf_btns.addWidget(self.path_filter_all_btn)
        pf_btns.addWidget(self.path_filter_none_btn)
        pf_layout.addLayout(pf_btns)
        self.path_filter_tree = QTreeWidget()
        self.path_filter_tree.setHeaderHidden(True)
        self.path_filter_tree.setRootIsDecorated(False)
        self.path_filter_tree.setMaximumHeight(140)
        pf_layout.addWidget(self.path_filter_tree)
        root.addWidget(path_filter_box)

        self.path_filter_all_btn.clicked.connect(lambda: self._set_all_path_filters(True))
        self.path_filter_none_btn.clicked.connect(lambda: self._set_all_path_filters(False))
        self.path_filter_tree.itemChanged.connect(lambda *_: self.path_filter_changed.emit())

        # Log groups at bottom (search target selection)
        paths_box = QGroupBox("Log groups")
        paths_layout = QVBoxLayout(paths_box)
        sel_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.setObjectName("ghostButton")
        self.select_none_btn = QPushButton("Select none")
        self.select_none_btn.setObjectName("ghostButton")
        sel_row.addWidget(self.select_all_btn)
        sel_row.addWidget(self.select_none_btn)
        paths_layout.addLayout(sel_row)

        self.path_tree = QTreeWidget()
        self.path_tree.setHeaderHidden(True)
        self.path_tree.setRootIsDecorated(False)
        paths_layout.addWidget(self.path_tree)
        root.addWidget(paths_box, 1)

        self.select_all_btn.clicked.connect(lambda: self._set_all_paths(True))
        self.select_none_btn.clicked.connect(lambda: self._set_all_paths(False))

    def set_environments(self, envs: list[str], current: str | None = None) -> None:
        self.env_combo.blockSignals(True)
        self.env_combo.clear()
        self.env_combo.addItems(envs)
        if current and current in envs:
            self.env_combo.setCurrentText(current)
        self.env_combo.blockSignals(False)

    def set_paths(self, paths: list[str], selected: set[str] | None = None) -> None:
        self.path_tree.clear()
        selected = selected if selected is not None else set(paths)
        for path in paths:
            item = QTreeWidgetItem([path.rsplit("/", 1)[-1]])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            item.setToolTip(0, path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0,
                Qt.CheckState.Checked if path in selected else Qt.CheckState.Unchecked,
            )
            self.path_tree.addTopLevelItem(item)

    def selected_paths(self) -> list[str]:
        result = []
        for i in range(self.path_tree.topLevelItemCount()):
            item = self.path_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                result.append(item.data(0, Qt.ItemDataRole.UserRole))
        return result

    def _set_all_paths(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.path_tree.topLevelItemCount()):
            self.path_tree.topLevelItem(i).setCheckState(0, state)

    def _set_all_path_filters(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.path_filter_tree.blockSignals(True)
        for i in range(self.path_filter_tree.topLevelItemCount()):
            self.path_filter_tree.topLevelItem(i).setCheckState(0, state)
        self.path_filter_tree.blockSignals(False)
        self.path_filter_changed.emit()

    def query(self) -> str:
        return self.query_edit.text().strip()

    def set_query(self, text: str) -> None:
        self.query_edit.setText(text)

    def env(self) -> str:
        return self.env_combo.currentText()

    def start_time(self) -> str:
        text = self.time_combo.currentText().strip()
        for label, value in self.TIME_PRESETS:
            if text == label:
                return value
        return text or "1"

    def set_start_time(self, value: str) -> None:
        """Set start time from raw value (e.g. '1', '3', or a datetime string)."""
        raw = (value or "").strip()
        if not raw:
            return
        for i, (label, preset) in enumerate(self.TIME_PRESETS):
            if raw == preset or raw == label:
                self.time_combo.setCurrentIndex(i)
                return
        # Custom absolute/relative text — put it in the editable field
        self.time_combo.setEditText(raw)

    def set_searching(self, searching: bool) -> None:
        self.search_btn.setEnabled(not searching)
        self.stop_btn.setEnabled(searching)
        self.env_combo.setEnabled(not searching)
        self.path_tree.setEnabled(not searching)

    def update_path_filter_options(self, groups: list[str]) -> None:
        previous_checked = set(self.selected_path_filters())
        previous_known = getattr(self, "_path_filter_known", set())
        first_time = not previous_known

        self.path_filter_tree.blockSignals(True)
        self.path_filter_tree.clear()
        for g in groups:
            item = QTreeWidgetItem([g.rsplit("/", 1)[-1]])
            item.setData(0, Qt.ItemDataRole.UserRole, g)
            item.setToolTip(0, g)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if first_time:
                checked = True
            elif g in previous_checked:
                checked = True
            elif g not in previous_known:
                checked = True  # newly appeared group
            else:
                checked = False  # user had unchecked it
            item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.path_filter_tree.addTopLevelItem(item)
        self._path_filter_known = set(groups)
        self.path_filter_tree.blockSignals(False)

    def selected_path_filters(self) -> list[str]:
        """Full log-group paths checked in path filter. Empty → treat as all."""
        result = []
        for i in range(self.path_filter_tree.topLevelItemCount()):
            item = self.path_filter_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                result.append(item.data(0, Qt.ItemDataRole.UserRole))
        return result

    def filter_text(self) -> str:
        return self.filter_edit.text()
