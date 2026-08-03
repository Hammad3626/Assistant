"""Read-only file location report for local assistant data."""

from __future__ import annotations

from pathlib import Path


def format_path_report(paths: dict[str, str | Path | None]) -> str:
    """Return a readable local path report."""
    lines = ["Local assistant paths"]
    for label, path in paths.items():
        value = "not configured" if path is None else str(path)
        lines.append(f"{label}: {value}")
    lines.append("This command is read-only and does not open or modify files.")
    return "\n".join(lines)
