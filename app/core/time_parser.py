from __future__ import annotations

import datetime
import re


# Absolute datetime formats we accept (order matters: more specific first)
_ABS_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d.%m.%y %H:%M:%S",
    "%d.%m.%y %H:%M",
    "%d/%m/%y %H:%M:%S",
    "%d/%m/%y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
)

_DATE_ONLY = {
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
}

_RELATIVE_RE = re.compile(
    r"^(?P<n>\d+)\s*(?P<u>h|m|s|d|hours?|mins?|minutes?|secs?|seconds?|days?)$",
    re.IGNORECASE,
)


def parse_start_time(time_input: str) -> str:
    """Convert messy UI time input into an awslogs --start value."""
    raw = (time_input or "").strip()
    if not raw:
        return "1h ago"

    # Bare hour count: "3" → "3h ago"
    if raw.isdigit():
        return f"{raw}h ago"

    lower = raw.lower().strip()

    # Already awslogs-style relative
    if "ago" in lower:
        return raw

    # "2h", "30m", "1d", "2 hours"
    m = _RELATIVE_RE.match(lower.replace(" ", ""))
    if not m:
        m = _RELATIVE_RE.match(lower)
    if m:
        n = m.group("n")
        u = m.group("u")[0].lower()  # h/m/s/d
        return f"{n}{u} ago"

    # Absolute datetime — try many formats + light normalization
    candidates = _normalize_candidates(raw)
    for candidate in candidates:
        for fmt in _ABS_FORMATS:
            try:
                dt = datetime.datetime.strptime(candidate, fmt)
                if fmt in _DATE_ONLY:
                    dt = dt.replace(hour=0, minute=0, second=0)
                # Inclusive start: nudge 1 minute back (legacy behavior)
                dt = dt - datetime.timedelta(minutes=1)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

    # Last resort: keep as-is if it looks like awslogs might accept it
    if re.search(r"\d", raw):
        return raw

    return "1h ago"


def _normalize_candidates(raw: str) -> list[str]:
    """Produce variant spellings of the same user input."""
    s = raw.strip()
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    variants = [s]

    # "26.09.2026, 16:00" / "26.09.2026T16:00"
    s2 = s.replace(",", " ").replace("T", " ")
    s2 = re.sub(r"\s+", " ", s2).strip()
    if s2 not in variants:
        variants.append(s2)

    # Swap / and - toward dotted form for EU dates
    for v in list(variants):
        dotted = v.replace("/", ".").replace("-", ".")
        # But ISO dates use - : only rewrite if it looks like DD.MM.YYYY (day first)
        if re.match(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", v):
            # Rebuild with dots for date part, keep time
            parts = v.split(" ", 1)
            date_part = parts[0].replace("/", ".").replace("-", ".")
            rebuilt = date_part if len(parts) == 1 else f"{date_part} {parts[1]}"
            if rebuilt not in variants:
                variants.append(rebuilt)

    # Zero-pad day/month: 7.10.2025 → 07.10.2025
    padded: list[str] = []
    for v in variants:
        padded.append(v)
        padded_v = _zero_pad_eu_date(v)
        if padded_v and padded_v not in padded:
            padded.append(padded_v)
    return padded


def _zero_pad_eu_date(text: str) -> str | None:
    m = re.match(
        r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$",
        text.strip(),
    )
    if not m:
        return None
    d, mo, y = m.group(1), m.group(2), m.group(3)
    if len(y) == 2:
        y = ("20" + y) if int(y) < 70 else ("19" + y)
    out = f"{int(d):02d}.{int(mo):02d}.{y}"
    if m.group(4) is not None:
        hh, mm = int(m.group(4)), int(m.group(5))
        ss = int(m.group(6) or 0)
        out += f" {hh:02d}:{mm:02d}:{ss:02d}"
    return out


def parse_timestamp(text: str) -> datetime.datetime | None:
    """Best-effort extract sortable timestamp from a log line / timestamp field."""
    if not text:
        return None
    parts = text.strip().split()
    for i in range(len(parts) - 1):
        candidate = f"{parts[i]} {parts[i + 1]}"
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
            try:
                return datetime.datetime.strptime(candidate.split("+")[0], fmt)
            except ValueError:
                continue
    return None
