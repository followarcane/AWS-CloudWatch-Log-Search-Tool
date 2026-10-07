from __future__ import annotations

from typing import Iterable, Sequence

from .models import LogEntry, LogLevel


class FilterEngine:
    """Client-side filtering over structured LogEntry lists."""

    SPECIAL_CHARS = set("\"'?!,.:;-_=+<>[]{}()|\\/@#$%^&*")

    @classmethod
    def is_valid_filter_text(cls, text: str) -> bool:
        if not text or len(text) < 2:
            return False
        if all(c in cls.SPECIAL_CHARS for c in text):
            return False
        consecutive = 0
        for c in text:
            if c in cls.SPECIAL_CHARS:
                consecutive += 1
                if consecutive > 2:
                    return False
            else:
                consecutive = 0
        return True

    def filter_entries(
        self,
        entries: Sequence[LogEntry],
        *,
        text: str = "",
        log_group: str | None = None,
        log_groups: Sequence[str] | None = None,
        level: LogLevel | None = None,
    ) -> list[LogEntry]:
        needle = (text or "").strip()
        use_text = bool(needle) and self.is_valid_filter_text(needle)

        allowed: set[str] | None = None
        if log_groups is not None:
            # Explicit list: empty → match nothing; non-empty → those groups only
            allowed = {g for g in log_groups if g and g != "All"}
        elif log_group and log_group != "All":
            allowed = {log_group}

        result: list[LogEntry] = []
        for entry in entries:
            if allowed is not None and entry.log_group not in allowed:
                continue
            if level and entry.level != level:
                continue
            if use_text and not entry.matches(needle):
                continue
            result.append(entry)
        return result

    @staticmethod
    def unique_groups(entries: Iterable[LogEntry]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for e in entries:
            if e.log_group and e.log_group not in seen:
                seen.add(e.log_group)
                ordered.append(e.log_group)
        return ordered
