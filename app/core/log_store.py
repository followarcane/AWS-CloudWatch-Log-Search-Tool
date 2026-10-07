from __future__ import annotations

import threading
from typing import Callable, Optional

from .filter_engine import FilterEngine
from .models import LogEntry, LogLevel
from .time_parser import parse_timestamp


Listener = Callable[[], None]
_UNSET = object()


class LogStore:
    """In-memory append-oriented store with filter/sort indexes for the UI.

    Mutations may happen from worker threads; all public methods are lock-guarded.
    Listeners are invoked outside the lock and must marshal to the UI thread themselves.
    """

    def __init__(self, filter_engine: FilterEngine | None = None) -> None:
        self._entries: list[LogEntry] = []
        self._filter_engine = filter_engine or FilterEngine()
        self._filter_text = ""
        self._filter_groups: list[str] | None = None  # None = all
        self._filter_level: LogLevel | None = None
        # Preference from config; actual time-sort only after sort_now()
        self._sort_by_time = True
        self._time_sorted = False
        self._filtered_indices: list[int] = []
        self._listeners: list[Listener] = []
        self._lock = threading.RLock()
        self._rebuild_index()

    def add_listener(self, callback: Listener) -> None:
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Listener) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb()
            except Exception:
                pass

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._time_sorted = False  # back to discovery order for the next search
            self._rebuild_index()
        self._notify()

    def append(self, entry: LogEntry) -> None:
        self.append_many([entry])

    def append_many(self, entries: list[LogEntry]) -> None:
        """Append in discovery order (first found stays at top). Time-sort only via sort_now()."""
        if not entries:
            return
        with self._lock:
            start = len(self._entries)
            self._entries.extend(entries)
            new_indices: list[int] = []
            for offset, entry in enumerate(entries):
                if self._entry_matches(entry):
                    new_indices.append(start + offset)
            # Always append — do not prepend (that put latest finds on top)
            if new_indices:
                self._filtered_indices.extend(new_indices)
        self._notify()

    def set_filters(
        self,
        *,
        text: object = _UNSET,
        log_group: object = _UNSET,
        log_groups: object = _UNSET,
        level: object = _UNSET,
    ) -> None:
        with self._lock:
            if text is not _UNSET:
                self._filter_text = text or ""
            if log_groups is not _UNSET:
                # None → all groups; [] → match nothing; [paths…] → those only
                self._filter_groups = None if log_groups is None else list(log_groups)  # type: ignore[arg-type]
            elif log_group is not _UNSET:
                lg = log_group
                self._filter_groups = None if lg in (None, "", "All") else [str(lg)]
            if level is not _UNSET:
                self._filter_level = level  # type: ignore[assignment]
            self._rebuild_index()
        self._notify()

    def set_sort_by_time(self, enabled: bool) -> None:
        """Set preference only. Does not reshuffle until sort_now() / disable."""
        with self._lock:
            self._sort_by_time = enabled
            if not enabled and self._time_sorted:
                self._time_sorted = False
                self._rebuild_index()
                should_notify = True
            else:
                should_notify = False
        if should_notify:
            self._notify()

    def sort_now(self) -> None:
        """Apply newest-first time sort once (e.g. when search completes)."""
        with self._lock:
            if not self._sort_by_time:
                return
            self._time_sorted = True
            self._rebuild_index()
        self._notify()

    def _entry_matches(self, entry: LogEntry) -> bool:
        filtered = self._filter_engine.filter_entries(
            [entry],
            text=self._filter_text,
            log_groups=self._filter_groups,
            level=self._filter_level,
        )
        return bool(filtered)

    def _rebuild_index(self) -> None:
        filtered = self._filter_engine.filter_entries(
            self._entries,
            text=self._filter_text,
            log_groups=self._filter_groups,
            level=self._filter_level,
        )
        id_to_index = {id(e): i for i, e in enumerate(self._entries)}
        indices = [id_to_index[id(e)] for e in filtered if id(e) in id_to_index]

        # Only reshuffle when explicitly time-sorted — path/text filter must
        # preserve discovery order (first found at top).
        if self._time_sorted:
            def sort_key(i: int):
                ts = parse_timestamp(self._entries[i].timestamp)
                return ts or parse_timestamp("1970-01-01 00:00:00")

            indices.sort(key=sort_key, reverse=True)

        self._filtered_indices = indices

    @property
    def all_entries(self) -> list[LogEntry]:
        with self._lock:
            return list(self._entries)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def filtered_count(self) -> int:
        with self._lock:
            return len(self._filtered_indices)

    def entry_at(self, filtered_row: int) -> LogEntry | None:
        with self._lock:
            if filtered_row < 0 or filtered_row >= len(self._filtered_indices):
                return None
            return self._entries[self._filtered_indices[filtered_row]]

    def filtered_entries(self) -> list[LogEntry]:
        with self._lock:
            return [self._entries[i] for i in self._filtered_indices]

    def groups(self) -> list[str]:
        with self._lock:
            return self._filter_engine.unique_groups(self._entries)
