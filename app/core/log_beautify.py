from __future__ import annotations

import json
import re

# Trailing request metadata: X-Correlation-Id = … X-Request-Id = …
# Only inserts a newline before each header — never deletes the header/value text.
_X_HEADER = re.compile(r"(?<!\n)[ \t]+(X-[A-Za-z0-9-]+)[ \t]*=[ \t]*")


def beautify_log_message(message: str) -> str:
    """Reformat for readability without dropping payload.

    Guarantees:
    - Never strips awslogs/Spring prefixes, logger names, or metadata.
    - Non-JSON text: only newline / spacing tweaks (all original characters kept,
      aside from \\r\\n → \\n normalization).
    - JSON spans: semantic round-trip via json.loads/dumps (indent only;
      values/keys preserved with ensure_ascii=False). If parse fails, raw kept.
    """
    if not message:
        return message

    ended_nl = message.endswith("\n") or message.endswith("\r\n")
    text = message.replace("\r\n", "\n").replace("\r", "\n")
    if ended_nl and text.endswith("\n"):
        core, suffix = text[:-1], "\n"
    else:
        core, suffix = text, ""

    # NOTE: do NOT strip path/pod/logger prefixes — that was data loss.
    core = _pretty_json_spans(core)
    core = _split_x_headers(core)
    core = _soft_break_java_response(core)
    return core + suffix


def _split_x_headers(text: str) -> str:
    if "X-" not in text:
        return text
    # Replace only the whitespace before "X-Foo =" with newline + indent.
    return _X_HEADER.sub(r"\n  \1 = ", text)


def _soft_break_java_response(text: str) -> str:
    """Break long RangerPaymentResponse(...)-style dumps; keep every character."""
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if (
            len(line) > 120
            and "(" in line
            and ")" in line
            and "=" in line
            and not stripped.startswith("{")
            and not stripped.startswith("[")
            and (
                re.search(r"(Response|Request|Exception)\s*\(", line)
                or re.search(r"\w+Response\s*\(", line)
            )
        ):
            open_i = line.find("(")
            close_i = line.rfind(")")
            if open_i != -1 and close_i > open_i:
                head = line[: open_i + 1]
                mid = line[open_i + 1 : close_i]
                tail = line[close_i:]
                # Insert newlines after commas; do not strip mid (keeps spaces)
                mid = re.sub(r",[ \t]*", ",\n    ", mid)
                line = f"{head}\n    {mid}\n{tail}"
        out.append(line)
    return "\n".join(out)


def _pretty_json_spans(text: str) -> str:
    spans = _find_json_spans(text)
    if not spans:
        return text

    parts: list[str] = []
    last = 0
    for start, end in spans:
        parts.append(text[last:start])
        raw = text[start:end]
        try:
            parsed = json.loads(raw)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            line_start = text.rfind("\n", 0, start) + 1
            indent = re.match(r"[ \t]*", text[line_start:start])
            pad = indent.group(0) if indent else ""
            if pad and "\n" in pretty:
                pretty = pretty.replace("\n", "\n" + pad)
            parts.append(pretty)
        except (json.JSONDecodeError, TypeError, ValueError):
            parts.append(raw)
        last = end
    parts.append(text[last:])
    return "".join(parts)


def _find_json_spans(text: str) -> list[tuple[int, int]]:
    """Return non-overlapping spans of top-level JSON objects/arrays that parse."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch not in "{[":
            i += 1
            continue
        end = _match_balanced(text, i)
        if end is None:
            i += 1
            continue
        candidate = text[i:end]
        if len(candidate) < 2:
            i += 1
            continue
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            i += 1
            continue
        if not _worth_pretty(parsed, candidate):
            i += 1
            continue
        spans.append((i, end))
        i = end
    return spans


def _worth_pretty(parsed: object, raw: str) -> bool:
    if len(raw) < 28:
        return False
    if isinstance(parsed, dict):
        return bool(parsed)
    if isinstance(parsed, list):
        if not parsed:
            return False
        if any(isinstance(x, (dict, list)) for x in parsed):
            return True
        return len(raw) >= 80
    return False


def _match_balanced(text: str, start: int) -> int | None:
    """Return index past matching } or ], respecting JSON strings. None if unbalanced."""
    stack: list[str] = []
    in_string = False
    escape = False
    pairs = {"{": "}", "[": "]"}
    openers = "{["
    closers = "}]"

    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if c in openers:
            stack.append(c)
        elif c in closers:
            if not stack:
                return None
            op = stack.pop()
            if pairs[op] != c:
                return None
            if not stack:
                return i + 1
    return None
