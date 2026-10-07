from __future__ import annotations

import random
import subprocess
import sys
import threading
from pathlib import Path

from app.core.logging_setup import setup_logging

logger = setup_logging("logsearcher.keepawake")

# Inert key (F15) — resets idle timer without typing into the focused app.
_NUDGE_KEY_CODE = 113
_NUDGE_MIN_SEC = 180  # 3 minutes
_NUDGE_MAX_SEC = 300  # 5 minutes


class KeepAwakeController:
    """Optional macOS keep-awake: caffeinate + periodic idle key nudge.

    Default off. When enabled (Preferences), starts caffeinate and every 3–5
    minutes sends an F15 keypress via System Events so MDM/idle locks stay reset.
    """

    def __init__(self, enabled: bool = False, pid_dir: Path | None = None) -> None:
        self.enabled = enabled
        self._process: subprocess.Popen | None = None
        self._pid_file = (pid_dir or Path.cwd()) / ".caffeinate.pid"
        self._nudge_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.stop()

    def start(self) -> None:
        if not self.enabled or sys.platform != "darwin":
            return
        self._start_caffeinate()
        self._arm_nudge(initial=True)

    def stop(self) -> None:
        self._cancel_nudge()
        self._stop_caffeinate()

    def _start_caffeinate(self) -> None:
        if self._process and self._process.poll() is None:
            return
        try:
            self._process = subprocess.Popen(
                ["caffeinate", "-d", "-i", "-u"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                self._pid_file.write_text(str(self._process.pid), encoding="utf-8")
            except Exception:
                pass
            logger.info("caffeinate started pid=%s", self._process.pid)
        except Exception as exc:
            logger.warning("Failed to start caffeinate: %s", exc)

    def _stop_caffeinate(self) -> None:
        if self._process:
            try:
                self._process.kill()
            except Exception:
                try:
                    self._process.terminate()
                except Exception:
                    pass
            try:
                self._process.wait(timeout=0.2)
            except Exception:
                pass
            self._process = None
        try:
            if self._pid_file.exists():
                self._pid_file.unlink()
        except Exception:
            pass

    def _cancel_nudge(self) -> None:
        with self._lock:
            timer = self._nudge_timer
            self._nudge_timer = None
        if timer:
            timer.cancel()

    def _arm_nudge(self, *, initial: bool = False) -> None:
        if not self.enabled or sys.platform != "darwin":
            return
        self._cancel_nudge()
        # First nudge soon so idle doesn't win before the first 3–5 min window
        delay = 30.0 if initial else random.uniform(_NUDGE_MIN_SEC, _NUDGE_MAX_SEC)
        timer = threading.Timer(delay, self._nudge_tick)
        timer.daemon = True
        with self._lock:
            self._nudge_timer = timer
        timer.start()
        logger.debug("idle nudge armed in %.0fs", delay)

    def _nudge_tick(self) -> None:
        if not self.enabled:
            return
        self._send_idle_key()
        self._arm_nudge(initial=False)

    @staticmethod
    def _send_idle_key() -> None:
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to key code {_NUDGE_KEY_CODE}',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            logger.debug("idle nudge sent (F15)")
        except Exception as exc:
            logger.warning("idle nudge failed: %s", exc)
