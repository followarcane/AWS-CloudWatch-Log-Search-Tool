from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QCheckBox,
    QPushButton,
    QLabel,
    QComboBox,
    QPlainTextEdit,
    QMessageBox,
    QSpinBox,
    QGroupBox,
    QScrollArea,
    QFrame,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
)

from app.config.manager import ConfigManager
from app.ui.shortcut_capture import ShortcutCaptureEdit
from app.ui.styles import APP_STYLESHEET

SHORTCUT_LABELS = {
    "new_tab": "New tab",
    "close_tab": "Close tab",
    "search_selected": "Search selection in new tab",
    "stop_search": "Stop search",
    "copy_full_log": "Copy full log block",
    "copy_awslogs_command": "Copy awslogs command",
    "find_in_results": "Find in results",
}


class PreferencesDialog(QDialog):
    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Preferences")
        self.setMinimumSize(560, 420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(APP_STYLESHEET + self._extra_styles())

        # Open relative to parent / screen so it feels scaled
        self._apply_initial_size(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("prefsHeader")
        header_l = QVBoxLayout(header)
        header_l.setContentsMargins(20, 16, 20, 12)
        title = QLabel("Preferences")
        title.setObjectName("prefsTitle")
        subtitle = QLabel("Saved to config.local.json — company catalog stays in config.company.json")
        subtitle.setObjectName("prefsSubtitle")
        subtitle.setWordWrap(True)
        header_l.addWidget(title)
        header_l.addWidget(subtitle)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        self.nav = QListWidget()
        self.nav.setObjectName("prefsNav")
        self.nav.setMinimumWidth(140)
        self.nav.setMaximumWidth(260)
        self.nav.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        for label in ("General", "Paths & Profiles", "Shortcuts"):
            QListWidgetItem(label, self.nav)
        self.nav.setCurrentRow(0)
        splitter.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.stack.addWidget(self._wrap_scroll(self._build_general_page()))
        self.stack.addWidget(self._wrap_scroll(self._build_paths_page()))
        self.stack.addWidget(self._wrap_scroll(self._build_shortcuts_page()))
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([180, 700])

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        root.addWidget(splitter, 1)

        footer = QFrame()
        footer.setObjectName("prefsFooter")
        footer_l = QHBoxLayout(footer)
        footer_l.setContentsMargins(20, 12, 20, 14)
        footer_l.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ghostButton")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setMinimumWidth(100)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        footer_l.addWidget(cancel_btn)
        footer_l.addWidget(save_btn)
        root.addWidget(footer)

    def _apply_initial_size(self, parent) -> None:
        if parent is not None and parent.isVisible():
            geo = parent.geometry()
            w = max(640, int(geo.width() * 0.55))
            h = max(480, int(geo.height() * 0.65))
            self.resize(w, h)
            return
        self.resize(820, 580)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Soft-scale content paddings with window width
        width = max(self.width(), 1)
        pad = max(16, min(36, width // 40))
        for i in range(self.stack.count()):
            scroll = self.stack.widget(i)
            if not isinstance(scroll, QScrollArea):
                continue
            page = scroll.widget()
            if page is None:
                continue
            layout = page.layout()
            if layout is not None:
                layout.setContentsMargins(pad, pad, pad, pad)

    @staticmethod
    def _extra_styles() -> str:
        return """
        QFrame#prefsHeader {
            background: #16171a;
            border-bottom: 1px solid #3f4147;
        }
        QLabel#prefsTitle {
            font-size: 20px;
            font-weight: 700;
            color: #ffffff;
            background: transparent;
        }
        QLabel#prefsSubtitle {
            font-size: 12px;
            color: #8b8f97;
            background: transparent;
        }
        QFrame#prefsFooter {
            background: #16171a;
            border-top: 1px solid #3f4147;
        }
        QListWidget#prefsNav {
            background: #18191c;
            border: none;
            border-right: 1px solid #3f4147;
            padding: 10px 8px;
            outline: none;
        }
        QListWidget#prefsNav::item {
            color: #a0a4ab;
            padding: 10px 12px;
            margin: 2px 0;
            border-radius: 6px;
        }
        QListWidget#prefsNav::item:selected {
            background: #3d5a80;
            color: #ffffff;
        }
        QListWidget#prefsNav::item:hover:!selected {
            background: #2b2d31;
            color: #e8e8e8;
        }
        QLabel#sectionTitle {
            font-size: 15px;
            font-weight: 600;
            color: #ffffff;
            background: transparent;
            padding-bottom: 2px;
        }
        QLabel#sectionHint {
            font-size: 12px;
            color: #8b8f97;
            background: transparent;
        }
        QLabel#fieldLabel {
            color: #c5c8ce;
            background: transparent;
            font-weight: 500;
        }
        QGroupBox {
            margin-top: 14px;
            padding: 14px 12px 12px 12px;
        }
        QSpinBox#collapseSpin {
            min-height: 36px;
            min-width: 160px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QSpinBox#collapseSpin::up-button,
        QSpinBox#collapseSpin::down-button {
            width: 22px;
            background: #3a3d44;
            border: none;
        }
        QCheckBox {
            spacing: 8px;
            padding: 4px 0;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid #4a4d55;
            background: #2b2d31;
        }
        QCheckBox::indicator:checked {
            background: #5b8def;
            border-color: #5b8def;
        }
        QSplitter::handle {
            background: #3f4147;
        }
        """

    def _wrap_scroll(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setWidget(page)
        return scroll

    def _page_shell(self, title: str, hint: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setMinimumWidth(320)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)
        t = QLabel(title)
        t.setObjectName("sectionTitle")
        h = QLabel(hint)
        h.setObjectName("sectionHint")
        h.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(h)
        return page, layout

    def _build_general_page(self) -> QWidget:
        page, layout = self._page_shell(
            "General",
            "Display and behaviour options for the log stream.",
        )

        display = QGroupBox("Log stream")
        display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        display_l = QVBoxLayout(display)
        self.search_hl = QCheckBox("Highlight search terms")
        self.search_hl.setChecked(self.config.search_highlight_enabled)
        self.filter_hl = QCheckBox("Highlight filter terms")
        self.filter_hl.setChecked(self.config.filter_highlight_enabled)
        self.sort_time = QCheckBox("Sort by time when search completes (newest first)")
        self.sort_time.setChecked(self.config.sort_by_time_enabled)
        self.beautify = QCheckBox(
            "Beautify logs (JSON indent + wrap X- headers — never drops content)"
        )
        self.beautify.setChecked(self.config.beautify_logs_enabled)
        display_l.addWidget(self.search_hl)
        display_l.addWidget(self.filter_hl)
        display_l.addWidget(self.sort_time)
        display_l.addWidget(self.beautify)

        collapse_label = QLabel("Collapse logs longer than")
        collapse_label.setObjectName("fieldLabel")
        collapse_label.setWordWrap(True)
        display_l.addWidget(collapse_label)
        self.collapse_spin = QSpinBox()
        self.collapse_spin.setObjectName("collapseSpin")
        self.collapse_spin.setRange(3, 200)
        self.collapse_spin.setValue(self.config.max_collapsed_lines)
        self.collapse_spin.setSuffix(" lines")
        self.collapse_spin.setMinimumHeight(36)
        self.collapse_spin.setMinimumWidth(160)
        self.collapse_spin.setMaximumWidth(220)
        self.collapse_spin.setAlignment(Qt.AlignmentFlag.AlignLeft)
        display_l.addWidget(self.collapse_spin)
        layout.addWidget(display)

        system = QGroupBox("System")
        system.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        system_l = QVBoxLayout(system)
        self.keep_awake = QCheckBox(
            "Keep Mac awake while focused (caffeinate + F15 idle nudge every 3–5 min)"
        )
        self.keep_awake.setChecked(self.config.keep_awake_enabled)
        keep_hint = QLabel(
            "Off by default. Needs Accessibility for Terminal/Python if the key nudge is blocked."
        )
        keep_hint.setWordWrap(True)
        keep_hint.setStyleSheet("color:#888;font-size:11px;")
        system_l.addWidget(self.keep_awake)
        system_l.addWidget(keep_hint)
        layout.addWidget(system)

        layout.addStretch(1)
        return page

    def _build_paths_page(self) -> QWidget:
        page, layout = self._page_shell(
            "Paths & Profiles",
            "Per-environment CloudWatch log groups and AWS profile keys. "
            "Profile keys are matched as substrings of each path (longest match wins).",
        )

        env_row = QHBoxLayout()
        env_label = QLabel("Environment")
        env_label.setObjectName("fieldLabel")
        self.env_combo = QComboBox()
        self.env_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.env_combo.addItems(self.config.environments())
        if "PROD" in self.config.environments():
            self.env_combo.setCurrentText("PROD")
        env_row.addWidget(env_label)
        env_row.addWidget(self.env_combo, 1)
        layout.addLayout(env_row)

        paths_box = QGroupBox("Log groups")
        paths_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        paths_l = QVBoxLayout(paths_box)
        paths_hint = QLabel("One CloudWatch log group path per line")
        paths_hint.setObjectName("sectionHint")
        self.paths_edit = QPlainTextEdit()
        self.paths_edit.setPlaceholderText("/aws/eks/.../service-name")
        self.paths_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.paths_edit.setMinimumHeight(120)
        paths_l.addWidget(paths_hint)
        paths_l.addWidget(self.paths_edit, 1)
        layout.addWidget(paths_box, 3)

        profiles_box = QGroupBox("AWS profiles")
        profiles_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        profiles_l = QVBoxLayout(profiles_box)
        profiles_hint = QLabel(
            "One mapping per line: key=aws-profile-name  (e.g. steller=steller-developer)"
        )
        profiles_hint.setObjectName("sectionHint")
        profiles_hint.setWordWrap(True)
        self.profiles_edit = QPlainTextEdit()
        self.profiles_edit.setPlaceholderText("steller=steller-developer\nbahama=bahama-developer")
        self.profiles_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.profiles_edit.setMinimumHeight(80)
        profiles_l.addWidget(profiles_hint)
        profiles_l.addWidget(self.profiles_edit, 1)
        layout.addWidget(profiles_box, 2)

        self._paths_env = self.env_combo.currentText()
        self.env_combo.currentTextChanged.connect(self._on_env_changed)
        if self.env_combo.count():
            self._load_env_into_editors(self.env_combo.currentText())
        return page

    def _on_env_changed(self, env: str) -> None:
        if getattr(self, "_paths_env", None):
            prev = self._paths_env
            self._paths_env = None
            paths = [p.strip() for p in self.paths_edit.toPlainText().splitlines() if p.strip()]
            profiles: dict[str, str] = {}
            for line in self.profiles_edit.toPlainText().splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                profiles[key.strip()] = value.strip()
            self.config.set_env_paths(prev, paths)
            self.config.set_env_profiles(prev, profiles)
        self._paths_env = env
        self._load_env_into_editors(env)

    def _load_env_into_editors(self, env: str) -> None:
        paths = self.config.paths_for_env(env)
        profiles = self.config.profiles_for_env(env)
        self.paths_edit.setPlainText("\n".join(paths))
        self.profiles_edit.setPlainText("\n".join(f"{k}={v}" for k, v in profiles.items()))

    def _build_shortcuts_page(self) -> QWidget:
        page, layout = self._page_shell(
            "Shortcuts",
            "Click a field, then press the keys (e.g. ⌘T). Esc cancels, ⌫ clears.",
        )

        box = QGroupBox("Keyboard")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        box_l = QVBoxLayout(box)
        self.shortcut_edits: dict[str, ShortcutCaptureEdit] = {}
        platform = self.config.platform_key()

        for action, mapping in self.config.shortcuts.items():
            row = QHBoxLayout()
            label = QLabel(SHORTCUT_LABELS.get(action, action.replace("_", " ").title()))
            label.setObjectName("fieldLabel")
            label.setWordWrap(True)
            label.setMinimumWidth(160)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            edit = ShortcutCaptureEdit(mapping.get(platform, ""))
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            edit.setMinimumWidth(140)
            self.shortcut_edits[action] = edit
            row.addWidget(label, 2)
            row.addWidget(edit, 3)
            box_l.addLayout(row)

        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _save(self) -> None:
        self._persist_current_env_editors()

        self.config.search_highlight_enabled = self.search_hl.isChecked()
        self.config.filter_highlight_enabled = self.filter_hl.isChecked()
        self.config.sort_by_time_enabled = self.sort_time.isChecked()
        self.config.beautify_logs_enabled = self.beautify.isChecked()
        self.config.keep_awake_enabled = self.keep_awake.isChecked()
        self.config.max_collapsed_lines = self.collapse_spin.value()

        for action, edit in self.shortcut_edits.items():
            self.config.update_shortcut(action, edit.sequence())

        try:
            self.config.save_local()
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.accept()

    def _persist_current_env_editors(self) -> None:
        env = self.env_combo.currentText()
        if not env:
            return
        paths = [p.strip() for p in self.paths_edit.toPlainText().splitlines() if p.strip()]
        profiles: dict[str, str] = {}
        for line in self.profiles_edit.toPlainText().splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            profiles[key.strip()] = value.strip()
        self.config.set_env_paths(env, paths)
        self.config.set_env_profiles(env, profiles)
