from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QKeyEvent
from PyQt6.QtWidgets import QLineEdit


class ShortcutCaptureEdit(QLineEdit):
    """Click, then press a key combo — auto-fills a portable Ctrl+… sequence."""

    def __init__(self, sequence: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setClearButtonEnabled(False)
        self._portable = ""
        self.set_sequence(sequence)
        self.setPlaceholderText("Click, then press keys…")

    def sequence(self) -> str:
        """Portable form for config (Ctrl+T, Ctrl+Shift+A, …)."""
        return self._portable

    def set_sequence(self, seq: str) -> None:
        s = (seq or "").strip()
        s = (
            s.replace("Meta+", "Ctrl+")
            .replace("meta+", "Ctrl+")
            .replace("Command+", "Ctrl+")
            .replace("Cmd+", "Ctrl+")
        )
        self._portable = s
        if not s:
            self.setText("")
            return
        qs = QKeySequence(s)
        # Show native glyphs on macOS (⌘T) while keeping portable value
        self.setText(qs.toString(QKeySequence.SequenceFormat.NativeText) or s)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self.setPlaceholderText("Press shortcut…  (Esc cancel · ⌫ clear)")
        self.selectAll()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.setPlaceholderText("Click, then press keys…")
        # Refresh display
        self.set_sequence(self._portable)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()

        if key in (Qt.Key.Key_Escape,):
            self.clearFocus()
            event.accept()
            return

        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.set_sequence("")
            event.accept()
            return

        # Ignore modifier-only presses
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
            Qt.Key.Key_CapsLock,
            Qt.Key.Key_NumLock,
            Qt.Key.Key_ScrollLock,
        ):
            event.accept()
            return

        # Build a clean modifier set. On macOS Meta is ⌘ — store as Ctrl for Qt.
        parts: list[str] = []
        if mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")

        key_name = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)
        if not key_name:
            event.accept()
            return

        # Avoid lone letters without modifier (accidental typing)
        if not parts and key_name.upper() in {chr(c) for c in range(ord("A"), ord("Z") + 1)}:
            event.accept()
            return

        parts.append(key_name)
        portable = "+".join(parts)
        self.set_sequence(portable)
        self.clearFocus()
        event.accept()
