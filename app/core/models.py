from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class LogLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_text(cls, text: str) -> "LogLevel":
        upper = text.upper()
        if "ERROR" in upper or "FATAL" in upper or "EXCEPTION" in upper:
            return cls.ERROR
        if "WARN" in upper:
            return cls.WARN
        if "DEBUG" in upper:
            return cls.DEBUG
        if "INFO" in upper:
            return cls.INFO
        return cls.UNKNOWN


@dataclass
class LogEntry:
    timestamp: str
    level: LogLevel
    message: str
    log_group: str
    raw: str = ""

    def __post_init__(self) -> None:
        if not self.raw:
            self.raw = self.message
        if isinstance(self.level, str):
            self.level = LogLevel(self.level) if self.level in LogLevel._value2member_map_ else LogLevel.from_text(self.level)

    @property
    def preview(self) -> str:
        first = self.message.split("\n", 1)[0].strip()
        if len(first) > 160:
            return first[:157] + "..."
        return first

    @property
    def short_group(self) -> str:
        return self.log_group.rsplit("/", 1)[-1] if self.log_group else ""

    def pretty_message(self) -> str:
        cached = getattr(self, "_pretty_cached", None)
        if cached is not None:
            return cached
        from .log_beautify import beautify_log_message

        result = beautify_log_message(self.message or "")
        object.__setattr__(self, "_pretty_cached", result)
        return result

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        n = needle.lower()
        return (
            n in self.message.lower()
            or n in self.timestamp.lower()
            or n in self.log_group.lower()
            or n in self.level.value.lower()
        )


@dataclass
class SearchProgress:
    done_paths: int = 0
    total_paths: int = 0
    log_count: int = 0
    current_path: str = ""  # last path that emitted a log (short or full)
    active_paths: list[str] = field(default_factory=list)  # short names still running
    path_counts: dict[str, int] = field(default_factory=dict)  # short → logs so far
    stopped: bool = False
    completed: bool = False

    @property
    def fraction(self) -> float:
        if self.total_paths <= 0:
            return 0.0
        return min(1.0, self.done_paths / self.total_paths)


@dataclass
class SearchError:
    path: str
    message: str
    kind: str = "error"  # error | auth | rate_limit | not_found

    @staticmethod
    def classify(text: str, path: str = "") -> "SearchError":
        lower = text.lower()
        if any(k in lower for k in ("expiredtoken", "unable to locate credentials", "invalidclienttokenid", "unauthorized", "accessdenied", "the security token")):
            return SearchError(path=path, message=_friendly_auth(text), kind="auth")
        if "throttl" in lower or "rate exceeded" in lower or "too many requests" in lower:
            return SearchError(path=path, message="AWS rate limit hit. Wait a moment and retry.", kind="rate_limit")
        if "resourcenotfound" in lower or "does not exist" in lower:
            return SearchError(path=path, message=f"Log group not found: {path or 'unknown'}", kind="not_found")
        return SearchError(path=path, message=_trim(text), kind="error")


def _friendly_auth(text: str) -> str:
    return (
        "AWS credentials problem. Check your profile (aws sso login / aws configure) "
        f"and try again.\n\nDetails: {_trim(text)}"
    )


def _trim(text: str, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


@dataclass
class SearchRequest:
    query: str
    env: str
    start: str
    paths_and_profiles: list[tuple[str, str]] = field(default_factory=list)
    sort_by_time: bool = True
