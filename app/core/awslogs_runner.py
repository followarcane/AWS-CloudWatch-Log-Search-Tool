from __future__ import annotations

import datetime
import os
import select
import signal
import subprocess
import threading
from typing import Callable, Optional

from .logging_setup import setup_logging
from .models import LogEntry, LogLevel, SearchError
from .time_parser import parse_start_time

logger = setup_logging("logsearcher.awslogs")

OnLog = Callable[[LogEntry], None]
OnError = Callable[[SearchError], None]
READ_TIMEOUT_SEC = 0.2
READ_CHUNK = 65536


class AwsLogsRunner:
    """Runs `awslogs get` for a single log group with safe process handling."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def stop(self) -> None:
        """Signal stop and kill the process group. Never close pipes here
        (closing from another thread while the worker reads → deadlock)."""
        self._stop_event.set()
        with self._lock:
            proc = self._process
        if proc:
            self._kill_process_tree(proc)

    def reset(self) -> None:
        self._stop_event.clear()
        with self._lock:
            self._process = None

    def run(
        self,
        path: str,
        profile: str,
        filter_pattern: str | None,
        start_input: str,
        on_log: OnLog,
        on_error: Optional[OnError] = None,
    ) -> int:
        """Execute search; return number of log entries emitted."""
        self.reset()
        start_value = parse_start_time(start_input)

        cmd = [
            "awslogs",
            "get",
            path,
            "--profile",
            profile,
            "--start",
            start_value,
            "--query=log",
        ]
        if filter_pattern:
            cmd.extend(["--filter-pattern", filter_pattern])

        short = path.rsplit("/", 1)[-1]
        logger.debug("exec [%s]: %s", short, " ".join(cmd))

        try:
            # Binary pipes + os.read avoid TextIOWrapper locks across threads
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                close_fds=True,
                start_new_session=True,
            )
        except FileNotFoundError:
            if on_error:
                on_error(
                    SearchError(
                        path=path,
                        message="`awslogs` CLI not found. Install with: pip install awslogs",
                        kind="error",
                    )
                )
            return 0
        except Exception as exc:
            if on_error:
                on_error(SearchError.classify(str(exc), path))
            return 0

        with self._lock:
            self._process = process

        log_count = 0
        current_log: str | None = None
        current_timestamp: str | None = None
        current_level = LogLevel.INFO
        error_buffer: list[str] = []
        pending = ""

        try:
            assert process.stdout is not None
            fd = process.stdout.fileno()

            while True:
                if self._stop_event.is_set():
                    logger.debug("[%s] stopped by user", path)
                    break

                ready, _, _ = select.select([fd], [], [], READ_TIMEOUT_SEC)
                if not ready:
                    if process.poll() is not None:
                        # Drain remaining bytes
                        pending, log_count, current_log, current_timestamp, current_level = (
                            self._drain_fd(
                                fd,
                                pending,
                                path,
                                on_log,
                                error_buffer,
                                log_count,
                                current_log,
                                current_timestamp,
                                current_level,
                            )
                        )
                        break
                    continue

                try:
                    chunk = os.read(fd, READ_CHUNK)
                except OSError:
                    break
                if not chunk:
                    break

                pending += chunk.decode("utf-8", errors="replace")
                pending, log_count, current_log, current_timestamp, current_level = (
                    self._consume_lines(
                        pending,
                        path,
                        on_log,
                        error_buffer,
                        log_count,
                        current_log,
                        current_timestamp,
                        current_level,
                        final=False,
                    )
                )

            # Flush last partial line / open log block
            if pending.strip():
                pending, log_count, current_log, current_timestamp, current_level = (
                    self._consume_lines(
                        pending + "\n",
                        path,
                        on_log,
                        error_buffer,
                        log_count,
                        current_log,
                        current_timestamp,
                        current_level,
                        final=False,
                    )
                )

            if current_log:
                on_log(
                    self._build_entry(current_timestamp, current_level, current_log, path)
                )

            if self._stop_event.is_set():
                return log_count

            return_code = process.poll()
            if return_code is None:
                try:
                    process.wait(timeout=0.2)
                    return_code = process.returncode
                except Exception:
                    return_code = 0

            if log_count == 0 and error_buffer and on_error:
                on_error(SearchError.classify("\n".join(error_buffer[-8:]), path))
            elif return_code not in (0, None) and log_count == 0 and on_error:
                combined = "\n".join(error_buffer[-8:]) or f"awslogs exited with code {return_code}"
                on_error(SearchError.classify(combined, path))

        except Exception as exc:
            logger.exception("[%s] runner failed", path)
            if on_error and not self._stop_event.is_set():
                on_error(SearchError.classify(str(exc), path))
        finally:
            self._cleanup_process(process)

        logger.debug("[%s] emitted %s logs", path, log_count)
        return log_count

    def _drain_fd(
        self,
        fd: int,
        pending: str,
        path: str,
        on_log: OnLog,
        error_buffer: list[str],
        log_count: int,
        current_log: str | None,
        current_timestamp: str | None,
        current_level: LogLevel,
    ):
        while True:
            try:
                ready, _, _ = select.select([fd], [], [], 0)
                if not ready:
                    break
                chunk = os.read(fd, READ_CHUNK)
            except OSError:
                break
            if not chunk:
                break
            pending += chunk.decode("utf-8", errors="replace")
        return self._consume_lines(
            pending,
            path,
            on_log,
            error_buffer,
            log_count,
            current_log,
            current_timestamp,
            current_level,
            final=True,
        )

    def _consume_lines(
        self,
        pending: str,
        path: str,
        on_log: OnLog,
        error_buffer: list[str],
        log_count: int,
        current_log: str | None,
        current_timestamp: str | None,
        current_level: LogLevel,
        *,
        final: bool,
    ):
        while True:
            if "\n" in pending:
                line, pending = pending.split("\n", 1)
            elif final and pending:
                line, pending = pending, ""
            else:
                break

            log_count, current_log, current_timestamp, current_level = self._handle_line(
                line,
                path,
                on_log,
                error_buffer,
                log_count,
                current_log,
                current_timestamp,
                current_level,
            )
            if not final and "\n" not in pending and not pending:
                break
        return pending, log_count, current_log, current_timestamp, current_level

    def _handle_line(
        self,
        line: str,
        path: str,
        on_log: OnLog,
        error_buffer: list[str],
        log_count: int,
        current_log: str | None,
        current_timestamp: str | None,
        current_level: LogLevel,
    ) -> tuple[int, str | None, str | None, LogLevel]:
        if self._stop_event.is_set():
            return log_count, current_log, current_timestamp, current_level

        stripped = line.strip()
        if not stripped:
            return log_count, current_log, current_timestamp, current_level

        if self._looks_like_error(stripped) and path not in stripped:
            error_buffer.append(stripped)
            return log_count, current_log, current_timestamp, current_level

        is_main = path in stripped
        if is_main:
            if current_log:
                on_log(
                    self._build_entry(current_timestamp, current_level, current_log, path)
                )
            log_count += 1
            return (
                log_count,
                stripped,
                self._extract_timestamp(stripped),
                LogLevel.from_text(stripped),
            )

        if current_log:
            return log_count, current_log + "\n" + stripped, current_timestamp, current_level

        error_buffer.append(stripped)
        return log_count, current_log, current_timestamp, current_level

    def _cleanup_process(self, process: subprocess.Popen) -> None:
        # Only called from the worker thread that owns the pipe
        self._kill_process_tree(process)
        try:
            if process.stdout is not None:
                process.stdout.close()
        except Exception:
            pass
        with self._lock:
            if self._process is process:
                self._process = None

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except Exception:
                try:
                    process.terminate()
                except Exception:
                    pass
        try:
            process.wait(timeout=0.2)
        except Exception:
            pass

    @staticmethod
    def _looks_like_error(line: str) -> bool:
        lower = line.lower()
        keywords = (
            "traceback",
            "error:",
            "exception",
            "accessdenied",
            "expiredtoken",
            "unable to locate credentials",
            "an error occurred",
            "botocore",
            "invalidclienttokenid",
            "resourcenotfoundexception",
            "throttling",
        )
        return any(k in lower for k in keywords)

    @staticmethod
    def _extract_timestamp(line: str) -> str:
        parts = line.strip().split()
        for i in range(len(parts) - 1):
            if parts[i].count("-") == 2 and parts[i + 1].count(":") >= 2:
                return f"{parts[i]} {parts[i + 1]}"
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @staticmethod
    def _build_entry(
        timestamp: str | None,
        level: LogLevel,
        message: str,
        path: str,
    ) -> LogEntry:
        return LogEntry(
            timestamp=timestamp or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            level=level,
            message=message,
            log_group=path,
            raw=message,
        )
