from __future__ import annotations

import shlex

from .time_parser import parse_start_time


def build_awslogs_command(
    path: str,
    profile: str,
    start_input: str,
    query: str,
) -> str:
    """Build the exact shell-ready awslogs CLI string used for a search."""
    start_value = parse_start_time(start_input)
    filter_pattern = f'"{(query or "").strip()}"'
    parts = [
        "awslogs",
        "get",
        path,
        "--profile",
        profile,
        "--start",
        start_value,
        "--query=log",
        "--filter-pattern",
        filter_pattern,
    ]
    return " ".join(shlex.quote(p) for p in parts)
