from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QGuiApplication, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QMessageBox,
    QApplication,
)

from app import __version__
from app.config.manager import ConfigManager
from app.ui.keep_awake import KeepAwakeController
from app.ui.preferences import PreferencesDialog
from app.ui.search_workspace import SearchWorkspace
from app.ui.styles import APP_STYLESHEET


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle(f"AWS Log Searcher {__version__}")
        self.resize(1400, 900)
        self.setStyleSheet(APP_STYLESHEET)

        self.keep_awake = KeepAwakeController(
            enabled=config.keep_awake_enabled, pid_dir=config.base_dir
        )

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)

        self._build_menu()
        self._bind_shortcuts()
        self.add_tab()

        self.statusBar().showMessage("Ready")

    def show_zoomed(self) -> None:
        """Fill the current screen's available area (title-bar zoom), not exclusive fullscreen."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.availableGeometry())
        self.show()
        # Maximized = dock/menu bar stay visible (unlike green-button fullscreen Space)
        self.showMaximized()

    def _build_menu(self) -> None:
        # macOS: menu lives in the system menu bar (top of screen), not inside the window.
        file_menu = self.menuBar().addMenu("&File")

        new_tab = QAction("New Tab", self)
        new_tab.triggered.connect(self.add_tab)
        file_menu.addAction(new_tab)
        self._action_new_tab = new_tab

        close_tab = QAction("Close Tab", self)
        close_tab.triggered.connect(self.close_current_tab)
        file_menu.addAction(close_tab)
        self._action_close_tab = close_tab

        file_menu.addSeparator()

        export_act = QAction("Export Results…", self)
        export_act.triggered.connect(self._export_current)
        file_menu.addAction(export_act)

        clear_act = QAction("Clear Results", self)
        clear_act.triggered.connect(self._clear_current)
        file_menu.addAction(clear_act)

        file_menu.addSeparator()

        # Also under File so it's easy to spot
        prefs_file = QAction("Preferences…", self)
        prefs_file.setShortcut(QKeySequence.StandardKey.Preferences)
        prefs_file.setMenuRole(QAction.MenuRole.PreferencesRole)
        prefs_file.triggered.connect(self.show_preferences)
        file_menu.addAction(prefs_file)
        self._action_preferences = prefs_file

        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setMenuRole(QAction.MenuRole.QuitRole)
        quit_act.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(quit_act)

        edit_menu = self.menuBar().addMenu("&Edit")
        find_act = QAction("Find in Results…", self)
        find_act.triggered.connect(self._find_in_results)
        edit_menu.addAction(find_act)
        self._action_find = find_act

        settings_menu = self.menuBar().addMenu("&Settings")
        prefs = QAction("Preferences…", self)
        prefs.setMenuRole(QAction.MenuRole.NoRole)  # keep a visible in-app Settings entry
        prefs.triggered.connect(self.show_preferences)
        settings_menu.addAction(prefs)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About AWS Log Searcher", self)
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    @staticmethod
    def _qt_shortcut(seq: str) -> QKeySequence:
        """Normalize config shortcuts for Qt (on macOS Ctrl == ⌘ in QKeySequence)."""
        s = (seq or "").strip()
        if not s:
            return QKeySequence()
        # Config historically used Meta+ for ⌘; Qt prefers Ctrl+ on macOS menus/shortcuts
        s = s.replace("Meta+", "Ctrl+").replace("meta+", "Ctrl+")
        s = s.replace("Command+", "Ctrl+").replace("Cmd+", "Ctrl+")
        return QKeySequence(s)

    def _bind_shortcuts(self) -> None:
        # Clear previous dynamic shortcut actions (avoid ambiguous duplicate shortcuts)
        for act in getattr(self, "_shortcut_actions", []):
            self.removeAction(act)
        self._shortcut_actions: list[QAction] = []

        # Menu actions own new_tab / close_tab / find shortcuts (single binding only)
        self._action_new_tab.setShortcut(
            self._qt_shortcut(self.config.get_shortcut("new_tab") or "Ctrl+T")
        )
        self._action_new_tab.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._action_close_tab.setShortcut(
            self._qt_shortcut(self.config.get_shortcut("close_tab") or "Ctrl+W")
        )
        self._action_close_tab.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._action_find.setShortcut(
            self._qt_shortcut(self.config.get_shortcut("find_in_results") or "Ctrl+F")
        )
        self._action_find.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)

        mapping = {
            "search_selected": self._search_selected,
            "stop_search": self._stop_current,
            "copy_full_log": self._copy_current,
            "copy_awslogs_command": self._copy_awslogs_command,
        }
        for action_name, callback in mapping.items():
            seq = self.config.get_shortcut(action_name)
            if not seq:
                continue
            act = QAction(self)
            act.setShortcut(self._qt_shortcut(seq))
            act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            act.triggered.connect(callback)
            self.addAction(act)
            self._shortcut_actions.append(act)

    def add_tab(
        self, query: str = "", env: str = "", start: str = ""
    ) -> SearchWorkspace:
        # QAction.triggered may pass a checked:bool — ignore it
        if isinstance(query, bool):
            query = ""
        if isinstance(env, bool):
            env = ""
        if isinstance(start, bool):
            start = ""

        workspace = SearchWorkspace(self.config)
        workspace.title_changed.connect(lambda title, ws=workspace: self._update_tab_title(ws, title))
        workspace.open_query_in_new_tab.connect(self._open_query_tab)
        if query or env or start:
            workspace.prefill(query, env or None, start or None)
        idx = self.tabs.addTab(workspace, workspace.tab_title())
        self.tabs.setCurrentIndex(idx)
        return workspace

    def _open_query_tab(self, query: str, env: str, start: str = "") -> None:
        ws = self.add_tab(query=query, env=env, start=start)
        ws.start_search()

    def _update_tab_title(self, workspace: SearchWorkspace, title: str) -> None:
        idx = self.tabs.indexOf(workspace)
        if idx >= 0:
            self.tabs.setTabText(idx, title)

    def current_workspace(self) -> SearchWorkspace | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, SearchWorkspace) else None

    def close_current_tab(self) -> None:
        self._close_tab(self.tabs.currentIndex())

    def _close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.tabs.widget(index)
        if isinstance(widget, SearchWorkspace):
            widget.shutdown()
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.add_tab()

    def show_preferences(self) -> None:
        dlg = PreferencesDialog(self.config, self)
        if dlg.exec():
            self.keep_awake.set_enabled(self.config.keep_awake_enabled)
            if self.config.keep_awake_enabled and self.isActiveWindow():
                self.keep_awake.start()
            # Refresh path lists in open tabs
            for i in range(self.tabs.count()):
                ws = self.tabs.widget(i)
                if isinstance(ws, SearchWorkspace):
                    ws.panel.set_environments(self.config.environments(), ws.panel.env())
                    ws._reload_paths()
                    ws.terminal.set_highlight_options(
                        self.config.search_highlight_enabled,
                        self.config.filter_highlight_enabled,
                    )
                    ws.terminal.set_max_collapsed_lines(self.config.max_collapsed_lines)
                    ws.terminal.set_beautify_enabled(self.config.beautify_logs_enabled)
                    ws.store.set_sort_by_time(self.config.sort_by_time_enabled)
            self._bind_shortcuts()
            self.statusBar().showMessage("Preferences saved", 3000)

    def _export_current(self) -> None:
        ws = self.current_workspace()
        if ws:
            ws.export_results()

    def _clear_current(self) -> None:
        ws = self.current_workspace()
        if ws:
            ws.clear_results()

    def _stop_current(self) -> None:
        ws = self.current_workspace()
        if ws:
            ws.stop_search()

    def _copy_current(self) -> None:
        ws = self.current_workspace()
        if ws:
            ws.copy_selected()

    def _copy_awslogs_command(self) -> None:
        ws = self.current_workspace()
        if ws:
            ws.copy_awslogs_command()

    def _search_selected(self) -> None:
        ws = self.current_workspace()
        if ws:
            ws.search_selected_in_new_tab()

    def _find_in_results(self) -> None:
        ws = self.current_workspace()
        if ws:
            ws.show_find()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About AWS Log Searcher",
            f"<b>AWS Log Searcher</b> {__version__}<br><br>"
            "Company desktop CloudWatch log search tool.<br>"
            "Uses the <code>awslogs</code> CLI with your local AWS profiles.",
        )

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == event.Type.WindowActivate:
            self.keep_awake.start()
        elif event.type() == event.Type.WindowDeactivate:
            # Only stop when the whole app loses focus
            app = QApplication.instance()
            if app and not app.activeWindow():
                self.keep_awake.stop()

    def closeEvent(self, event) -> None:  # noqa: N802
        # Kill searches without joining — joining while pipes are open hangs macOS quit
        for i in range(self.tabs.count()):
            ws = self.tabs.widget(i)
            if isinstance(ws, SearchWorkspace):
                ws.shutdown()
        try:
            self.keep_awake.stop()
        except Exception:
            pass
        try:
            self.config.save_local()
        except Exception:
            pass
        event.accept()
