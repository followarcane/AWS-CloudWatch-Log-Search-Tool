from __future__ import annotations

import html
import re

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QFont,
    QColor,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QGuiApplication,
    QWheelEvent,
    QMouseEvent,
)
from PyQt6.QtWidgets import QTextEdit, QMenu, QWidget

from app.core.log_store import LogStore
from app.core.models import LogEntry
from app.ui.styles import LEVEL_COLORS

SEPARATOR = "─" * 100
EXPAND_PREFIX = "▶ expand · "
COLLAPSE_PREFIX = "▲ collapse"
MAX_HIGHLIGHT_MATCHES = 200
# Hard caps — QTextEdit cannot keep up with terminal-speed awslogs output.
MAX_LIVE_RENDER = 80  # while searching: first N found on screen
MAX_FINISH_RENDER = 250  # after search: hard cap for display
_UI_CHROME_RE = re.compile(
    rf"^(?:{re.escape(EXPAND_PREFIX)}|{re.escape(COLLAPSE_PREFIX)}|… showing first ).*"
)


class TerminalLogView(QTextEdit):
    """Selectable terminal-style log stream (first-found at top while searching)."""

    search_selected_requested = pyqtSignal(str)
    copy_awslogs_command_requested = pyqtSignal()
    _store_changed = pyqtSignal()

    def __init__(self, store: LogStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        mono = QFont("Menlo", 12)
        if not mono.exactMatch():
            mono = QFont("Courier New", 12)
        self.setFont(mono)
        self.setStyleSheet(
            "QTextEdit {"
            " background:#121316; color:#e8e8e8;"
            " border:1px solid #3f4147; border-radius:8px; padding:8px;"
            " selection-background-color:#3d5a80;"
            "}"
        )

        self._search_term = ""
        self._filter_term = ""
        self._highlight_search = True
        self._highlight_filter = True
        self._max_collapsed_lines = 15
        self._beautify = True
        self._expanded_ids: set[int] = set()
        self._stick_top = True
        self._suppress_scroll_tracking = False
        self._busy = False
        self._streaming = False
        self._live_updates = True
        self._pending_refresh = False
        self._rendered_count = 0
        self._entry_spans: list[tuple[int, int, int]] = []
        self._toggle_spans: list[tuple[int, int, int]] = []

        # Coalesce store updates — avoid beachball during heavy searches
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(250)
        self._refresh_timer.timeout.connect(self._refresh_from_store)

        self._store_changed.connect(self._schedule_refresh, Qt.ConnectionType.QueuedConnection)
        self.store.add_listener(lambda: self._store_changed.emit())
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def set_streaming(self, streaming: bool) -> None:
        """While True, cheap bulk refreshes; finish_search() for final paint."""
        if streaming:
            self._streaming = True
            self._live_updates = True
            # 0ms until first log is painted, then we slow down in _schedule_refresh
            self._refresh_timer.setInterval(0)
            return
        self.finish_search()

    def halt_streaming(self) -> None:
        """Stop live updates without rebuilding (e.g. Stop pressed)."""
        self._streaming = False
        self._live_updates = False
        self._pending_refresh = False
        self._refresh_timer.stop()

    def finish_search(self) -> None:
        """End streaming; colored bulk HTML rebuild on next tick (keeps Stop responsive)."""
        self.halt_streaming()
        self._refresh_timer.setInterval(50)
        QTimer.singleShot(0, self._deferred_finish_render)

    def _deferred_finish_render(self) -> None:
        if self._streaming:
            return
        try:
            # Preserve viewport (Stop/finish must not jump to top)
            self._render_all(polish=True, cap=MAX_FINISH_RENDER)
        except Exception:
            try:
                self._render_all(polish=False, cap=MAX_FINISH_RENDER)
            except Exception:
                pass

    def set_max_collapsed_lines(self, n: int) -> None:
        self._max_collapsed_lines = max(3, int(n))
        self.rebuild(polish=not self._streaming)

    def set_beautify_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._beautify:
            return
        self._beautify = enabled
        if self.store.count:
            self.rebuild(polish=not self._streaming)

    def _display_message(self, entry: LogEntry) -> str:
        if self._beautify:
            try:
                return entry.pretty_message()
            except Exception:
                return entry.message or ""
        return entry.message or ""

    def set_highlight_options(self, search: bool, filter_: bool) -> None:
        self._highlight_search = search
        self._highlight_filter = filter_

    def set_terms(self, search_term: str = "", filter_term: str = "") -> None:
        self._search_term = search_term or ""
        self._filter_term = filter_term or ""

    def clear_view(self) -> None:
        self._busy = True
        self._expanded_ids.clear()
        self._entry_spans.clear()
        self._toggle_spans.clear()
        self._rendered_count = 0
        self.clear()
        self._busy = False
        self._stick_top = True
        self.verticalScrollBar().setValue(0)

    def rebuild(self, polish: bool = True, *, anchor_eid: int | None = None) -> None:
        """Re-render. If anchor_eid is set, keep that log in view (expand/collapse)."""
        if self._streaming:
            self._render_all(
                polish=False, cap=MAX_LIVE_RENDER, anchor_eid=anchor_eid
            )
        elif polish:
            # Sync render — do not go through deferred finish_search (scroll jumps)
            self._render_all(
                polish=True, cap=MAX_FINISH_RENDER, anchor_eid=anchor_eid
            )
        else:
            self._render_all(
                polish=False, cap=MAX_FINISH_RENDER, anchor_eid=anchor_eid
            )

    def find_text(self, needle: str, *, forward: bool = True) -> bool:
        """Find next/previous occurrence in the log view (wraps around)."""
        needle = (needle or "").strip()
        if not needle:
            return False
        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.find(needle, flags):
            return True
        # Wrap
        cursor = self.textCursor()
        if forward:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        return bool(self.find(needle, flags))

    def selected_text(self) -> str:
        raw = self.textCursor().selectedText().replace("\u2029", "\n")
        return self._strip_ui_chrome(raw)

    def copy_selection_or_all(self) -> None:
        text = self.selected_text()
        if text:
            QGuiApplication.clipboard().setText(text)
            return
        self.copy_log_block_at_cursor()

    def copy_log_block_at_cursor(self) -> None:
        block = self.log_block_at_cursor()
        if block:
            QGuiApplication.clipboard().setText(block)

    @staticmethod
    def _strip_ui_chrome(text: str) -> str:
        lines: list[str] = []
        for line in text.splitlines():
            if _UI_CHROME_RE.match(line):
                continue
            if line.startswith(SEPARATOR) or (line and set(line) <= {"─", " "}):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def log_block_at_cursor(self) -> str:
        """Full beautified log (no collapse chrome) for the entry under the cursor."""
        entry = self.entry_at_cursor()
        if entry is not None:
            body = self._display_message(entry)
            return (
                f"{entry.timestamp} [{entry.level.value}] {entry.short_group}\n"
                f"{body}"
            ).strip()

        plain = self.toPlainText()
        if not plain.strip():
            return ""
        pos = self.textCursor().position()
        for _eid, start, end in self._entry_spans:
            if start <= pos <= end:
                return self._strip_ui_chrome(plain[start:end])
        parts = plain.split(SEPARATOR)
        offset = 0
        for i, part in enumerate(parts):
            chunk_start = offset
            chunk_end = offset + len(part)
            if chunk_start <= pos <= chunk_end + (len(SEPARATOR) if i < len(parts) - 1 else 0):
                return self._strip_ui_chrome(part)
            offset = chunk_end + len(SEPARATOR) + 1
        return self._strip_ui_chrome(plain)

    def entry_at_cursor(self) -> LogEntry | None:
        pos = self.textCursor().position()
        for eid, start, end in self._entry_spans:
            if start <= pos <= end:
                for entry in self.store.filtered_entries():
                    if id(entry) == eid:
                        return entry
                break
        entries = self.store.filtered_entries()
        return entries[0] if entries else None

    def _schedule_refresh(self) -> None:
        if not self._live_updates:
            return
        self._pending_refresh = True
        if self._streaming and self._rendered_count == 0:
            # First log must appear immediately
            self._refresh_timer.setInterval(0)
        elif self._streaming:
            self._refresh_timer.setInterval(350)
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _refresh_from_store(self) -> None:
        if self._busy:
            self._schedule_refresh()
            return
        if not self._pending_refresh:
            return
        self._pending_refresh = False
        if self._streaming:
            # Bulk setPlainText of first N found — never QTextCursor prepend
            self._render_all(polish=False, cap=MAX_LIVE_RENDER)
            if self._rendered_count > 0:
                self._refresh_timer.setInterval(350)
        else:
            self._render_all(polish=False, cap=MAX_FINISH_RENDER)

    def _render_all(
        self,
        polish: bool = True,
        *,
        lite: bool = False,
        apply_highlights: bool = True,
        cap: int | None = None,
        total: int | None = None,
        anchor_eid: int | None = None,
    ) -> None:
        self._busy = True
        self._suppress_scroll_tracking = True
        try:
            scroll = self.verticalScrollBar().value()
            stick = self._stick_top and anchor_eid is None
            entries = self.store.filtered_entries()
            full_n = len(entries)
            shown = entries
            if cap is not None and full_n > cap:
                shown = entries[:cap]
            note_total = total if total is not None else full_n

            if polish:
                self._render_html_colored(
                    shown,
                    truncated_from=note_total if note_total > len(shown) else None,
                )
                if apply_highlights:
                    self._apply_highlights_full()
            else:
                self._render_fast(
                    shown,
                    truncated_from=note_total if note_total > len(shown) else None,
                )

            bar = self.verticalScrollBar()
            if anchor_eid is not None:
                # Keep the same viewport offset (don't jump to top on collapse)
                bar.setValue(min(scroll, bar.maximum()))
            elif stick:
                bar.setValue(0)
            else:
                bar.setValue(min(scroll, bar.maximum()))
            self._stick_top = bar.value() <= 8
        except Exception:
            # Never let a paint glitch kill the process
            pass
        finally:
            self._suppress_scroll_tracking = False
            self._busy = False

    def _render_fast(
        self, entries: list[LogEntry], *, truncated_from: int | None = None
    ) -> None:
        """Plain bulk setPlainText — same class of work as a terminal dump."""
        chunks: list[str] = []
        spans: list[tuple[int, int, int]] = []
        toggles: list[tuple[int, int, int]] = []
        pos = 0

        if truncated_from is not None and truncated_from > len(entries):
            note = (
                f"… showing first {len(entries)} of {truncated_from} logs "
                f"(UI cap — full set stays in memory; Stop anytime)\n\n"
            )
            chunks.append(note)
            pos = len(note)

        for i, entry in enumerate(entries):
            start = pos
            block, toggle_rel = self._format_entry_plain(entry)
            chunks.append(block)
            end = start + len(block)
            spans.append((id(entry), start, end))
            if toggle_rel is not None:
                t0, t1 = toggle_rel
                toggles.append((start + t0, start + t1, id(entry)))
            if i < len(entries) - 1:
                sep = SEPARATOR + "\n"
                chunks.append(sep)
                pos = end + len(sep)
            else:
                pos = end

        self.setPlainText("".join(chunks))
        self._entry_spans = spans
        self._toggle_spans = toggles
        self._rendered_count = truncated_from if truncated_from is not None else len(entries)

    def _render_html_colored(
        self, entries: list[LogEntry], *, truncated_from: int | None = None
    ) -> None:
        """Bulk setHtml with colored headers — safe after Stop / search end."""
        html_parts: list[str] = []
        spans: list[tuple[int, int, int]] = []
        toggles: list[tuple[int, int, int]] = []
        pos = 0

        if truncated_from is not None and truncated_from > len(entries):
            note = (
                f"… showing first {len(entries)} of {truncated_from} logs "
                f"(UI cap — full set stays in memory)\n\n"
            )
            html_parts.append(
                f'<span style="color:#888888">{html.escape(note).replace(chr(10), "<br>")}</span>'
            )
            pos = len(note)

        for i, entry in enumerate(entries):
            start = pos
            plain, toggle_rel, block_html = self._format_entry_html(entry)
            html_parts.append(block_html)
            end = start + len(plain)
            spans.append((id(entry), start, end))
            if toggle_rel is not None:
                t0, t1 = toggle_rel
                toggles.append((start + t0, start + t1, id(entry)))
            if i < len(entries) - 1:
                sep = SEPARATOR + "\n"
                html_parts.append(
                    f'<span style="color:#6272a4">{html.escape(sep).replace(chr(10), "<br>")}</span>'
                )
                pos = end + len(sep)
            else:
                pos = end

        body = (
            '<div style="background:#121316;color:#e8e8e8;'
            'font-family:Menlo,Consolas,monospace;font-size:12px;white-space:pre-wrap;">'
            + "".join(html_parts)
            + "</div>"
        )
        self.setHtml(body)
        self._entry_spans = spans
        self._toggle_spans = toggles
        self._rendered_count = (
            truncated_from if truncated_from is not None else len(entries)
        )

    def _format_entry_html(
        self, entry: LogEntry
    ) -> tuple[str, tuple[int, int] | None, str]:
        plain, toggle_rel = self._format_entry_plain(entry)
        level = entry.level.value
        lvl_color = LEVEL_COLORS.get(level, LEVEL_COLORS["UNKNOWN"])
        header_plain = f"{entry.timestamp} [{level}] {entry.short_group}\n"
        body_plain = plain[len(header_plain) :] if plain.startswith(header_plain) else plain

        header_html = (
            f'<span style="color:#8be9fd">{html.escape(entry.timestamp)}</span> '
            f'<span style="color:{lvl_color};font-weight:700">[{html.escape(level)}]</span> '
            f'<span style="color:#9a9a9a">{html.escape(entry.short_group)}</span><br>'
        )

        # Color expand/collapse line blue; rest body default
        body_lines = body_plain.splitlines(keepends=True)
        body_html_parts: list[str] = []
        for line in body_lines:
            esc = html.escape(line).replace("\n", "<br>")
            if line.startswith(EXPAND_PREFIX) or line.startswith(COLLAPSE_PREFIX):
                body_html_parts.append(f'<span style="color:#5b8def">{esc}</span>')
            else:
                body_html_parts.append(f'<span style="color:#e8e8e8">{esc}</span>')

        return plain, toggle_rel, header_html + "".join(body_html_parts)

    def _format_entry_plain(self, entry: LogEntry) -> tuple[str, tuple[int, int] | None]:
        message = self._display_message(entry)
        lines = message.splitlines() or [""]
        total = len(lines)
        expanded = id(entry) in self._expanded_ids
        collapsed = total > self._max_collapsed_lines and not expanded
        visible = lines[: self._max_collapsed_lines] if collapsed else lines

        header = f"{entry.timestamp} [{entry.level.value}] {entry.short_group}\n"
        body = "\n".join(visible).rstrip() + "\n"
        text = header + body
        toggle_rel = None
        if total > self._max_collapsed_lines:
            toggle_start = len(text)
            if collapsed:
                hidden = total - self._max_collapsed_lines
                toggle = f"{EXPAND_PREFIX}{hidden} more lines\n"
            else:
                toggle = f"{COLLAPSE_PREFIX}\n"
            text += toggle
            toggle_rel = (toggle_start, toggle_start + len(toggle))
        text += "\n"
        return text, toggle_rel

    def _render_polished(
        self,
        entries: list[LogEntry],
        *,
        lite: bool = False,
        apply_highlights: bool = True,
    ) -> None:
        self.clear()
        self._entry_spans.clear()
        self._toggle_spans.clear()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        for i, entry in enumerate(entries):
            start = cursor.position()
            toggle = self._insert_entry_polished(cursor, entry, lite=lite)
            self._entry_spans.append((id(entry), start, cursor.position()))
            if toggle:
                self._toggle_spans.append(toggle)
            if i < len(entries) - 1:
                sep_fmt = QTextCharFormat()
                sep_fmt.setForeground(QColor("#6272a4"))
                cursor.insertText(SEPARATOR + "\n", sep_fmt)

        if apply_highlights:
            self._apply_highlights_full()
        self._rendered_count = len(entries)

    def _insert_entry_polished(
        self, cursor: QTextCursor, entry: LogEntry, *, lite: bool = False
    ) -> tuple[int, int, int] | None:
        ts_fmt = QTextCharFormat()
        ts_fmt.setForeground(QColor("#8be9fd"))
        cursor.insertText(f"{entry.timestamp} ", ts_fmt)

        level = entry.level.value
        lvl_fmt = QTextCharFormat()
        lvl_fmt.setForeground(QColor(LEVEL_COLORS.get(level, LEVEL_COLORS["UNKNOWN"])))
        lvl_fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"[{level}] ", lvl_fmt)

        group_fmt = QTextCharFormat()
        group_fmt.setForeground(QColor("#9a9a9a"))
        cursor.insertText(f"{entry.short_group}\n", group_fmt)

        msg_fmt = QTextCharFormat()
        msg_fmt.setForeground(QColor("#e8e8e8"))
        message = self._display_message(entry)
        lines = message.splitlines() or [""]
        total = len(lines)
        expanded = id(entry) in self._expanded_ids
        collapsed = total > self._max_collapsed_lines and not expanded
        visible = lines[: self._max_collapsed_lines] if collapsed else lines
        cursor.insertText("\n".join(visible).rstrip() + "\n", msg_fmt)

        toggle_span = None
        if total > self._max_collapsed_lines:
            toggle_fmt = QTextCharFormat()
            toggle_fmt.setForeground(QColor("#5b8def"))
            toggle_start = cursor.position()
            if collapsed:
                hidden = total - self._max_collapsed_lines
                cursor.insertText(f"{EXPAND_PREFIX}{hidden} more lines\n", toggle_fmt)
            else:
                cursor.insertText(f"{COLLAPSE_PREFIX}\n", toggle_fmt)
            toggle_span = (toggle_start, cursor.position(), id(entry))

        cursor.insertText("\n")
        return toggle_span

    def _apply_highlights_full(self) -> None:
        if self._highlight_search and self._search_term:
            self._highlight_all(self._search_term, QColor("#aa0000"), QColor("#ffffff"))
        if self._highlight_filter and self._filter_term:
            self._highlight_all(self._filter_term, QColor("#aaaa00"), QColor("#000000"))

    def _highlight_all(self, needle: str, bg: QColor, fg: QColor) -> None:
        if not needle or len(needle) < 2:
            return
        fmt = QTextCharFormat()
        fmt.setBackground(bg)
        fmt.setForeground(fg)
        doc = self.document()
        cursor = QTextCursor(doc)
        matches = 0
        while matches < MAX_HIGHLIGHT_MATCHES:
            cursor = doc.find(needle, cursor)
            if cursor.isNull():
                break
            cursor.mergeCharFormat(fmt)
            matches += 1

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            cursor = self.cursorForPosition(event.position().toPoint())
            pos = cursor.position()
            for start, end, eid in self._toggle_spans:
                if start <= pos <= end:
                    if eid in self._expanded_ids:
                        self._expanded_ids.discard(eid)
                    else:
                        self._expanded_ids.add(eid)
                    self.rebuild(polish=not self._streaming, anchor_eid=eid)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        # Don't rebuild QWheelEvent (API differs across Qt builds). Scroll manually, damped.
        angle = event.angleDelta()
        pixel = event.pixelDelta()
        dy = pixel.y() if not pixel.isNull() else angle.y()
        if dy == 0:
            super().wheelEvent(event)
            return
        # angleDelta is typically ±120 per notch; pixelDelta is trackpad pixels
        step = dy // 3 if abs(dy) >= 3 else (1 if dy > 0 else -1)
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - step)
        event.accept()

    def _on_scroll(self, value: int) -> None:
        if self._suppress_scroll_tracking:
            return
        self._stick_top = value <= 8

    def _context_menu(self, pos) -> None:
        if not self.textCursor().hasSelection():
            self.setTextCursor(self.cursorForPosition(pos))

        menu = QMenu(self)
        copy_sel = menu.addAction("Copy selection")
        copy_block = menu.addAction("Copy full log block")
        copy_cmd = menu.addAction("Copy awslogs command")
        search_act = menu.addAction("Search selection in new tab")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == copy_sel:
            text = self.selected_text()
            if text:
                QGuiApplication.clipboard().setText(text)
        elif chosen == copy_block:
            self.copy_log_block_at_cursor()
        elif chosen == copy_cmd:
            self.copy_awslogs_command_requested.emit()
        elif chosen == search_act:
            text = self.selected_text()
            if text:
                self.search_selected_requested.emit(text[:200])
