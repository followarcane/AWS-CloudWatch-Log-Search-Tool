from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QMessageBox,
    QFileDialog,
    QSplitter,
    QLineEdit,
    QPushButton,
)

from app.config.manager import ConfigManager
from app.core.awslogs_command import build_awslogs_command
from app.core.log_store import LogStore
from app.core.models import SearchError, SearchProgress, SearchRequest
from app.core.search_service import SearchService
from app.ui.search_panel import SearchPanel
from app.ui.terminal_view import TerminalLogView


class _Bridge(QObject):
    """Marshal background-thread callbacks onto the Qt event loop."""

    progress = pyqtSignal(object)
    error = pyqtSignal(object)
    finished = pyqtSignal(object)


class SearchWorkspace(QWidget):
    title_changed = pyqtSignal(str)
    open_query_in_new_tab = pyqtSignal(str, str, str)  # query, env, start_time

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.store = LogStore()
        self.store.set_sort_by_time(config.sort_by_time_enabled)
        self.service = SearchService(self.store)
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_progress)
        self._bridge.error.connect(self._on_error)
        self._bridge.finished.connect(self._on_finished)

        self.service.set_callbacks(
            on_progress=lambda p: self._bridge.progress.emit(p),
            on_error=lambda e: self._bridge.error.emit(e),
            on_finished=lambda p: self._bridge.finished.emit(p),
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.panel = SearchPanel()
        splitter.addWidget(self.panel)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 8, 8)
        right.setSpacing(6)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color:#a0a0a0;")
        right.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        right.addWidget(self.progress)

        self.find_bar = self._build_find_bar()
        self.find_bar.hide()
        right.addWidget(self.find_bar)

        self.terminal = TerminalLogView(self.store)
        self.terminal.set_highlight_options(
            config.search_highlight_enabled, config.filter_highlight_enabled
        )
        self.terminal.set_max_collapsed_lines(config.max_collapsed_lines)
        self.terminal.set_beautify_enabled(config.beautify_logs_enabled)
        self.terminal.search_selected_requested.connect(self._search_in_new_tab)
        self.terminal.copy_awslogs_command_requested.connect(self.copy_awslogs_command)
        self._last_request: SearchRequest | None = None
        right.addWidget(self.terminal, 1)

        self.empty_label = QLabel("")
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color:#ff8e8e; padding:4px;")
        self.empty_label.hide()
        right.addWidget(self.empty_label)

        container = QWidget()
        container.setLayout(right)
        splitter.addWidget(container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 1000])
        layout.addWidget(splitter)

        envs = config.environments()
        default_env = "PROD" if "PROD" in envs else (envs[0] if envs else None)
        self.panel.set_environments(envs, default_env)
        self._reload_paths()
        self.panel.env_changed.connect(self._on_env_changed)
        self.panel.search_requested.connect(self.start_search)
        self.panel.stop_requested.connect(self.stop_search)
        self.panel.filter_changed.connect(self._on_filter_text)
        self.panel.path_filter_changed.connect(self._on_path_filter)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self._apply_filters)
        self._pending_filter = ""
        self._stop_thread: threading.Thread | None = None
        self._last_path_filter_done = -1
        self._last_path_filter_logs = -1

    def _build_find_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("findBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(QLabel("Find"))
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find in results…")
        self.find_edit.returnPressed.connect(lambda: self.find_next(forward=True))
        row.addWidget(self.find_edit, 1)
        prev_btn = QPushButton("Previous")
        prev_btn.setObjectName("ghostButton")
        prev_btn.clicked.connect(lambda: self.find_next(forward=False))
        next_btn = QPushButton("Next")
        next_btn.setObjectName("ghostButton")
        next_btn.clicked.connect(lambda: self.find_next(forward=True))
        close_btn = QPushButton("✕")
        close_btn.setObjectName("ghostButton")
        close_btn.setFixedWidth(32)
        close_btn.clicked.connect(self.hide_find)
        row.addWidget(prev_btn)
        row.addWidget(next_btn)
        row.addWidget(close_btn)
        self.find_status = QLabel("")
        self.find_status.setStyleSheet("color:#a0a0a0;")
        row.addWidget(self.find_status)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), bar)
        esc.activated.connect(self.hide_find)
        return bar

    def show_find(self) -> None:
        self.find_bar.show()
        sel = self.terminal.selected_text()
        if sel and "\n" not in sel and len(sel) < 120:
            self.find_edit.setText(sel)
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def hide_find(self) -> None:
        self.find_bar.hide()
        self.find_status.setText("")
        self.terminal.setFocus()

    def find_next(self, *, forward: bool = True) -> None:
        needle = self.find_edit.text().strip()
        if not needle:
            self.find_status.setText("")
            return
        if self.terminal.find_text(needle, forward=forward):
            self.find_status.setText("")
        else:
            self.find_status.setText("No matches")

    def _reload_paths(self) -> None:
        self.panel.set_paths(self.config.paths_for_env(self.panel.env()))

    def _on_env_changed(self, _env: str) -> None:
        self._reload_paths()

    def tab_title(self) -> str:
        q = self.panel.query() or "Search"
        env = self.panel.env() or ""
        return f"{env} · {q[:24]}"

    def start_search(self) -> None:
        query = self.panel.query()
        if not query:
            self._show_error("Please enter a search value.")
            return

        selected = self.panel.selected_paths()
        if not selected:
            self._show_error("Select at least one log group.")
            return

        try:
            paths_and_profiles = self.config.get_paths_and_profiles(self.panel.env(), selected)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.empty_label.hide()
        self.terminal.clear_view()
        self.terminal.set_terms(search_term=query, filter_term=self.panel.filter_text())
        self.terminal.set_streaming(True)
        self.store.set_sort_by_time(self.config.sort_by_time_enabled)

        request = SearchRequest(
            query=query,
            env=self.panel.env(),
            start=self.panel.start_time(),
            paths_and_profiles=paths_and_profiles,
            sort_by_time=self.config.sort_by_time_enabled,
        )
        self._last_request = request
        self.panel.set_searching(True)
        self.progress.show()
        self.progress.setValue(0)
        self.status_label.setText("Searching… waiting for first log")
        self.title_changed.emit(self.tab_title())
        self.service.start(request)

    def stop_search(self) -> None:
        # Flip UI immediately — don't wait for worker threads to exit
        if not self.panel.stop_btn.isEnabled() and not self.service.is_searching:
            return
        count = self.service.log_count
        self.panel.set_searching(False)
        self.status_label.setText(f"Stopped · {count} logs")
        self.progress.hide()
        # Colorize immediately — don't wait for worker cleanup / finished callback
        self.terminal.finish_search()
        if self._stop_thread and self._stop_thread.is_alive():
            return
        self._stop_thread = threading.Thread(
            target=self.service.stop,
            kwargs={"wait": False},
            name="search-stop",
            daemon=True,
        )
        self._stop_thread.start()

    def clear_results(self) -> None:
        if self.service.is_searching:
            self.service.stop(wait=False)
        self.terminal.set_streaming(False)
        self.store.clear()
        self.terminal.clear_view()
        self.progress.hide()
        self.empty_label.hide()
        self.status_label.setText("Cleared")
        self.panel.set_searching(False)

    def export_results(self) -> None:
        text = self.terminal.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Export", "No results to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export results", "logs.txt", "Text (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
        QMessageBox.information(self, "Export", "Results exported.")

    def copy_selected(self) -> None:
        """Shortcut: copy full log block under cursor (selection uses normal ⌘C)."""
        self.terminal.copy_log_block_at_cursor()

    def copy_awslogs_command(self) -> None:
        """Copy the full awslogs CLI used for the log block under the cursor."""
        cmd = self.awslogs_command_at_cursor()
        if not cmd:
            self._show_error("No search context to build awslogs command.")
            return
        QGuiApplication.clipboard().setText(cmd)
        self.status_label.setText("Copied awslogs command")
        self.empty_label.hide()

    def awslogs_command_at_cursor(self) -> str:
        if not self._last_request:
            return ""
        entry = self.terminal.entry_at_cursor()
        path = entry.log_group if entry else ""
        profile = ""
        for p, prof in self._last_request.paths_and_profiles:
            if p == path:
                profile = prof
                break
        if not path or not profile:
            # Fallback: first path from last search
            if not self._last_request.paths_and_profiles:
                return ""
            path, profile = self._last_request.paths_and_profiles[0]
        return build_awslogs_command(
            path=path,
            profile=profile,
            start_input=self._last_request.start,
            query=self._last_request.query,
        )

    def _search_in_new_tab(self, text: str) -> None:
        self.open_query_in_new_tab.emit(text, self.panel.env(), self.panel.start_time())

    def search_selected_in_new_tab(self) -> None:
        text = self.terminal.selected_text()
        if text:
            self.open_query_in_new_tab.emit(
                text[:200], self.panel.env(), self.panel.start_time()
            )

    def prefill(
        self,
        query: str,
        env: str | None = None,
        start: str | None = None,
    ) -> None:
        if env:
            self.panel.env_combo.setCurrentText(env)
        self.panel.set_query(query)
        if start:
            self.panel.set_start_time(start)

    def _on_filter_text(self, text: str) -> None:
        self._pending_filter = text
        self._filter_timer.start()

    def _on_path_filter(self) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        text = self._pending_filter if self._pending_filter is not None else self.panel.filter_text()
        if self.panel.path_filter_tree.topLevelItemCount() == 0:
            groups = None  # no filter options yet → show all
        else:
            groups = self.panel.selected_path_filters()  # may be empty → show none
        self.store.set_filters(text=text, log_groups=groups)
        self.terminal.set_terms(search_term=self.panel.query(), filter_term=text)
        self.terminal.rebuild(polish=not self.terminal._streaming)  # noqa: SLF001
        self._update_count_status()

    def _on_progress(self, progress: SearchProgress) -> None:
        if progress.stopped or progress.completed:
            return
        pct = int(progress.fraction * 100)
        self.progress.setValue(pct)

        if progress.log_count <= 0:
            self.status_label.setText(
                f"Searching… waiting for first log · "
                f"{progress.done_paths}/{progress.total_paths} groups checked"
            )
            return

        live = progress.total_paths - progress.done_paths
        parts = [
            f"{progress.log_count} logs",
            f"{progress.done_paths}/{progress.total_paths} done",
        ]
        if live > 0:
            parts.append(f"{live} live")

        # Path that just produced logs + per-path counts for top contributors
        hot = (progress.current_path or "").rsplit("/", 1)[-1]
        if hot:
            n = progress.path_counts.get(hot, 0)
            parts.append(f"← {hot}" + (f" ({n})" if n else ""))

        if progress.path_counts:
            top = sorted(progress.path_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
            bits = [f"{name}:{n}" for name, n in top if n > 0]
            if bits:
                parts.append(" · ".join(bits))

        self.status_label.setText(" · ".join(parts))

        # Refresh path filter when a group finishes, or every ~50 new logs
        if (
            progress.done_paths != self._last_path_filter_done
            or progress.log_count - self._last_path_filter_logs >= 50
        ):
            self._last_path_filter_done = progress.done_paths
            self._last_path_filter_logs = progress.log_count
            self.panel.update_path_filter_options(self.store.groups())

    def _on_error(self, error: SearchError) -> None:
        prefix = {
            "auth": "Credentials",
            "rate_limit": "Rate limit",
            "not_found": "Not found",
            "error": "Error",
        }.get(error.kind, "Error")
        path_bit = f" ({error.path.rsplit('/', 1)[-1]})" if error.path else ""
        self._show_error(f"{prefix}{path_bit}: {error.message}")

    def _on_finished(self, progress: SearchProgress) -> None:
        self.panel.set_searching(False)
        self.progress.setValue(100)
        self.panel.update_path_filter_options(self.store.groups())
        self.terminal.set_terms(
            search_term=self.panel.query(), filter_term=self.panel.filter_text()
        )
        self.terminal.finish_search()
        if progress.stopped:
            self.status_label.setText(f"Stopped · {progress.log_count} logs")
        elif progress.log_count == 0 and not self.empty_label.isVisible():
            self.status_label.setText("Search completed · 0 logs")
            self.empty_label.setText("No logs matched. Try a wider time range or different query.")
            self.empty_label.setStyleSheet("color:#a0a0a0; padding:4px;")
            self.empty_label.show()
        else:
            self.status_label.setText(f"Completed · {progress.log_count} logs")
        QTimer.singleShot(200, self.progress.hide)
        self.title_changed.emit(self.tab_title())

    def _show_error(self, message: str) -> None:
        self.empty_label.setStyleSheet("color:#ff8e8e; padding:4px;")
        self.empty_label.setText(message)
        self.empty_label.show()

    def _update_count_status(self) -> None:
        self.status_label.setText(
            f"Showing {self.store.filtered_count} / {self.store.count} logs"
        )

    def shutdown(self) -> None:
        # Never block the UI/quit path waiting on workers (pipe close deadlock).
        self.terminal.halt_streaming()
        self.service.stop(wait=False)
