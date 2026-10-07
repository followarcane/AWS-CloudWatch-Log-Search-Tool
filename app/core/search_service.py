from __future__ import annotations

import threading
from typing import Callable, Optional

# UI is the bottleneck (not awslogs). Flush on a timer; first log immediate.
FLUSH_INTERVAL_SEC = 0.35
FLUSH_IMMEDIATE_BATCH = 10_000  # effectively timer-only after first log

from .awslogs_command import build_awslogs_command
from .awslogs_runner import AwsLogsRunner
from .logging_setup import setup_logging
from .log_store import LogStore
from .models import LogEntry, SearchError, SearchProgress, SearchRequest
from .time_parser import parse_start_time

logger = setup_logging("logsearcher.search")

ProgressCallback = Callable[[SearchProgress], None]
ErrorCallback = Callable[[SearchError], None]
FinishedCallback = Callable[[SearchProgress], None]


class SearchService:
    """Coordinates parallel awslogs searches across log groups."""

    def __init__(self, store: LogStore) -> None:
        self.store = store
        self._lock = threading.Lock()
        self._runners: list[AwsLogsRunner] = []
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._progress = SearchProgress()
        self._on_progress: Optional[ProgressCallback] = None
        self._on_error: Optional[ErrorCallback] = None
        self._on_finished: Optional[FinishedCallback] = None
        self._batch: list[LogEntry] = []
        self._batch_lock = threading.Lock()
        self._flush_timer: threading.Timer | None = None
        self._flush_timer_lock = threading.Lock()
        self._flush_timer_armed = False
        self._finish_lock = threading.Lock()
        self._finish_emitted = False
        self._generation = 0
        self._force_finish_timer: threading.Timer | None = None
        self._active_paths: set[str] = set()
        self._path_counts: dict[str, int] = {}
        self._primed_ui = False

    @property
    def is_searching(self) -> bool:
        if self._progress.completed or self._progress.stopped:
            return False
        return any(t.is_alive() for t in self._threads)

    @property
    def log_count(self) -> int:
        return self._progress.log_count

    def set_callbacks(
        self,
        *,
        on_progress: ProgressCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_finished: FinishedCallback | None = None,
    ) -> None:
        self._on_progress = on_progress
        self._on_error = on_error
        self._on_finished = on_finished

    def start(self, request: SearchRequest) -> None:
        if self.is_searching:
            return

        query = (request.query or "").strip()
        if not query:
            if self._on_error:
                self._on_error(SearchError(path="", message="Please enter a search value.", kind="error"))
            return
        if not request.paths_and_profiles:
            if self._on_error:
                self._on_error(SearchError(path="", message="No log groups selected for this environment.", kind="error"))
            return

        # Kill any leftover runners from a previous search (no forced-finish callback)
        self._kill_runners()
        self._cancel_flush_timer()
        self._cancel_force_finish_timer()
        self.store.clear()
        self._stop_event.clear()
        self._runners.clear()
        self._threads.clear()
        with self._batch_lock:
            self._batch.clear()
        self._generation += 1
        with self._finish_lock:
            self._finish_emitted = False
        with self._lock:
            self._active_paths.clear()
            self._path_counts.clear()
        self._primed_ui = False

        filter_pattern = f'"{query}"'
        total = len(request.paths_and_profiles)
        self._progress = SearchProgress(done_paths=0, total_paths=total, log_count=0)
        self._emit_progress()
        gen = self._generation

        start_resolved = parse_start_time(request.start)
        logger.info(
            "Search start · env=%s · query=%r · start=%r → %s · %s groups",
            request.env,
            query,
            request.start,
            start_resolved,
            total,
        )
        for path, profile in request.paths_and_profiles:
            short = path.rsplit("/", 1)[-1]
            logger.info(
                "  → %s  profile=%s  %s",
                short,
                profile,
                build_awslogs_command(path, profile, request.start, query),
            )

        for path, profile in request.paths_and_profiles:
            runner = AwsLogsRunner()
            self._runners.append(runner)
            thread = threading.Thread(
                target=self._worker,
                args=(runner, path, profile, filter_pattern, request.start),
                name=f"awslogs:{path.rsplit('/', 1)[-1]}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

        watcher = threading.Thread(
            target=self._watch_completion,
            args=(request.sort_by_time, gen),
            daemon=True,
        )
        watcher.start()

    def _kill_runners(self) -> None:
        self._stop_event.set()
        for runner in list(self._runners):
            runner.stop()

    def stop(self, wait: bool = False) -> None:
        gen = self._generation
        if not self._progress.stopped and not self._progress.completed:
            logger.info(
                "Search stop requested · %s logs so far · %s/%s groups",
                self._progress.log_count,
                self._progress.done_paths,
                self._progress.total_paths,
            )
        self._kill_runners()
        self._progress.stopped = True
        self._cancel_flush_timer()
        self._flush_batch()
        self._emit_progress()
        # Don't leave UI waiting on stuck workers — finalize soon.
        self._schedule_forced_finish(gen)
        if wait:
            for thread in list(self._threads):
                if thread.is_alive():
                    thread.join(timeout=0.8)
            self._emit_finished(gen)

    def _worker(
        self,
        runner: AwsLogsRunner,
        path: str,
        profile: str,
        filter_pattern: str,
        start_input: str,
    ) -> None:
        short = path.rsplit("/", 1)[-1]
        if self._stop_event.is_set():
            self._mark_path_done(path)
            return

        with self._lock:
            self._active_paths.add(short)
            self._path_counts.setdefault(short, 0)
            self._progress.current_path = short
        self._emit_progress()

        def on_log(entry: LogEntry) -> None:
            if self._stop_event.is_set():
                return
            with self._batch_lock:
                self._batch.append(entry)
                self._progress.log_count += 1
            with self._lock:
                self._path_counts[short] = self._path_counts.get(short, 0) + 1
                self._progress.current_path = short
            self._schedule_flush()

        def on_error(err: SearchError) -> None:
            logger.warning("Search error on %s: %s", path, err.message)
            if self._on_error:
                self._on_error(err)

        try:
            count = runner.run(
                path=path,
                profile=profile,
                filter_pattern=filter_pattern,
                start_input=start_input,
                on_log=on_log,
                on_error=on_error,
            )
            if self._stop_event.is_set():
                logger.info("  ✕ %s stopped · %s logs", short, count)
            else:
                logger.info("  ✓ %s done · %s logs", short, count)
        finally:
            self._mark_path_done(path)

    def _schedule_flush(self) -> None:
        with self._batch_lock:
            if not self._batch:
                return
            # Always flush the very first log(s) immediately so the UI proves search works
            first_paint = not self._primed_ui
            if first_paint or len(self._batch) >= FLUSH_IMMEDIATE_BATCH:
                batch = self._batch
                self._batch = []
                if first_paint:
                    self._primed_ui = True
            else:
                batch = []
                first_paint = False
        if batch:
            first_entry = batch[0]
            self.store.append_many(batch)
            self._emit_progress()
            if first_paint:
                logger.info(
                    "First log on screen · %s · %s",
                    first_entry.short_group,
                    (first_entry.timestamp or "")[:23],
                )
            return
        self._arm_flush_timer()

    def _arm_flush_timer(self) -> None:
        with self._flush_timer_lock:
            if self._flush_timer_armed:
                return
            self._flush_timer_armed = True
            timer = threading.Timer(FLUSH_INTERVAL_SEC, self._timed_flush)
            timer.daemon = True
            self._flush_timer = timer
            timer.start()

    def _cancel_flush_timer(self) -> None:
        with self._flush_timer_lock:
            self._flush_timer_armed = False
            timer = self._flush_timer
            self._flush_timer = None
        if timer:
            timer.cancel()

    def _timed_flush(self) -> None:
        with self._flush_timer_lock:
            self._flush_timer_armed = False
            self._flush_timer = None
        self._flush_batch()
        self._emit_progress()

    def _flush_batch(self) -> None:
        with self._batch_lock:
            batch = self._batch
            self._batch = []
        if batch:
            self.store.append_many(batch)

    def _mark_path_done(self, path: str) -> None:
        self._flush_batch()
        short = path.rsplit("/", 1)[-1]
        with self._lock:
            self._active_paths.discard(short)
            self._progress.done_paths = min(
                self._progress.total_paths, self._progress.done_paths + 1
            )
            if self._progress.current_path in (path, short):
                # Prefer another still-active path for the status line
                self._progress.current_path = next(iter(self._active_paths), "")
        self._emit_progress()

    def _cancel_force_finish_timer(self) -> None:
        timer = self._force_finish_timer
        self._force_finish_timer = None
        if timer:
            timer.cancel()

    def _schedule_forced_finish(self, generation: int) -> None:
        self._cancel_force_finish_timer()
        timer = threading.Timer(0.5, lambda: self._emit_finished(generation))
        timer.daemon = True
        self._force_finish_timer = timer
        timer.start()

    def _emit_finished(self, generation: int) -> None:
        if generation != self._generation:
            return
        with self._finish_lock:
            if self._finish_emitted:
                return
            self._finish_emitted = True
        self._cancel_force_finish_timer()
        self._cancel_flush_timer()
        self._flush_batch()
        self._progress.completed = True
        self._progress.current_path = ""
        with self._lock:
            self._active_paths.clear()
        self._emit_progress()
        if self._on_finished:
            try:
                self._on_finished(self._progress)
            except Exception:
                logger.exception("finished callback failed")
        status = "stopped" if self._progress.stopped else "completed"
        logger.info(
            "Search %s · %s logs · %s/%s groups",
            status,
            self._progress.log_count,
            self._progress.done_paths,
            self._progress.total_paths,
        )

    def _watch_completion(self, sort_by_time: bool, generation: int) -> None:
        for thread in list(self._threads):
            # When stopping, don't hang forever on a stuck readline
            timeout = 0.4 if self._stop_event.is_set() else None
            thread.join(timeout=timeout)
            if generation != self._generation:
                return
        # Re-kill any lingering runners, then one more short wait
        if self._stop_event.is_set():
            self._kill_runners()
            for thread in list(self._threads):
                if thread.is_alive():
                    thread.join(timeout=0.25)
        if generation != self._generation:
            return
        self._cancel_flush_timer()
        self._flush_batch()
        if sort_by_time and not self._stop_event.is_set():
            self.store.set_sort_by_time(True)
            self.store.sort_now()
        self._emit_finished(generation)

    def _emit_progress(self) -> None:
        if not self._on_progress:
            return
        with self._lock:
            active = sorted(self._active_paths)
            counts = dict(self._path_counts)
            current = self._progress.current_path
        p = SearchProgress(
            done_paths=self._progress.done_paths,
            total_paths=self._progress.total_paths,
            log_count=self._progress.log_count,
            current_path=current,
            active_paths=active,
            path_counts=counts,
            stopped=self._progress.stopped,
            completed=self._progress.completed,
        )
        try:
            self._on_progress(p)
        except Exception:
            logger.exception("progress callback failed")
