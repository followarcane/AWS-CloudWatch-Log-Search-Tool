from __future__ import annotations

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QPen
from PyQt6.QtWidgets import QListView, QStyledItemDelegate, QStyle, QWidget

from app.core.log_store import LogStore
from app.core.models import LogEntry
from app.ui.styles import LEVEL_COLORS


class LogListModel(QAbstractListModel):
    def __init__(self, store: LogStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.store.add_listener(self._on_store_changed)

    def _on_store_changed(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return self.store.filtered_count

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self.store.entry_at(index.row())
        if entry is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return entry
        if role == Qt.ItemDataRole.UserRole:
            return entry
        return None

    def entry_at(self, row: int) -> LogEntry | None:
        return self.store.entry_at(row)


class LogItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):  # noqa: N802
        size = super().sizeHint(option, index)
        size.setHeight(52)
        return size

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        entry: LogEntry | None = index.data(Qt.ItemDataRole.UserRole)
        if entry is None:
            return

        painter.save()
        rect: QRect = option.rect

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor("#3d5a80"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor("#2f3136"))

        mono = QFont("SF Mono", 11)
        if not mono.exactMatch():
            mono = QFont("Menlo", 11)
        ui = QFont(option.font)
        ui.setPointSize(11)

        level = entry.level.value
        color = QColor(LEVEL_COLORS.get(level, LEVEL_COLORS["UNKNOWN"]))

        # Level badge
        badge = QRect(rect.left() + 8, rect.top() + 8, 58, 18)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge, 4, 4)
        painter.setPen(QColor("#111"))
        painter.setFont(ui)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, level)

        # Timestamp
        painter.setPen(QColor("#8be9fd"))
        painter.setFont(mono)
        painter.drawText(
            rect.left() + 76,
            rect.top() + 8,
            180,
            18,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            entry.timestamp,
        )

        # Group
        painter.setPen(QColor("#9a9a9a"))
        painter.setFont(ui)
        painter.drawText(
            rect.left() + 270,
            rect.top() + 8,
            rect.width() - 290,
            18,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            entry.short_group,
        )

        # Preview
        painter.setPen(QColor("#e8e8e8"))
        painter.drawText(
            rect.left() + 8,
            rect.top() + 28,
            rect.width() - 16,
            20,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            entry.preview,
        )

        # Separator
        painter.setPen(QPen(QColor("#2f3136")))
        painter.drawLine(rect.left(), rect.bottom() - 1, rect.right(), rect.bottom() - 1)
        painter.restore()


class ResultListView(QListView):
    entry_selected = pyqtSignal(object)  # LogEntry | None
    search_selected_requested = pyqtSignal(str)
    copy_requested = pyqtSignal(object)

    def __init__(self, model: LogListModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModel(model)
        self.setItemDelegate(LogItemDelegate(self))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.selectionModel().selectionChanged.connect(self._on_selection)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def _on_selection(self, *_args) -> None:
        indexes = self.selectedIndexes()
        if not indexes:
            self.entry_selected.emit(None)
            return
        entry = indexes[0].data(Qt.ItemDataRole.UserRole)
        self.entry_selected.emit(entry)

    def _context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu

        index = self.indexAt(pos)
        entry = index.data(Qt.ItemDataRole.UserRole) if index.isValid() else None
        menu = QMenu(self)
        if entry:
            act_copy = menu.addAction("Copy full log")
            act_search = menu.addAction("Search selection / preview in new tab")
            chosen = menu.exec(self.mapToGlobal(pos))
            if chosen == act_copy:
                self.copy_requested.emit(entry)
            elif chosen == act_search:
                self.search_selected_requested.emit(entry.preview[:120])
