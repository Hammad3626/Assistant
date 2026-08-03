"""Read-only Windows folder and drive detection."""

from __future__ import annotations

import os
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


COMMON_FOLDER_NAMES = (
    "Desktop",
    "Documents",
    "Downloads",
    "Pictures",
    "Music",
    "Videos",
)


@dataclass(frozen=True)
class DetectedFolder:
    name: str
    path: str


@dataclass(frozen=True)
class DetectedDrive:
    name: str
    path: str


def detect_common_folders(
    home: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[DetectedFolder]:
    """Return existing common Windows user folders without modifying settings."""
    env = os.environ if environ is None else environ
    home_path = Path(home or env.get("USERPROFILE") or Path.home()).expanduser()
    candidates: dict[str, Path] = {
        name: home_path / name for name in COMMON_FOLDER_NAMES
    }

    one_drive = env.get("OneDrive") or env.get("ONEDRIVE")
    if one_drive:
        candidates["OneDrive"] = Path(one_drive).expanduser()

    detected: list[DetectedFolder] = []
    for name, path in candidates.items():
        if path.exists() and path.is_dir():
            detected.append(DetectedFolder(name=name, path=str(path)))
    return detected


def detect_drives() -> list[DetectedDrive]:
    """Return mounted Windows drive roots such as C:\\ and D:\\."""
    detected: list[DetectedDrive] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            detected.append(DetectedDrive(name=f"{letter} drive", path=str(root)))
    return detected


def detected_folders_summary() -> str:
    folders = detect_common_folders()
    if not folders:
        return "Detected Windows folders: none found. This command is read-only."

    lines = ["Detected Windows folders (read-only):"]
    lines.extend(f"- {folder.name}: {folder.path}" for folder in folders)
    lines.append("Nothing was added to the folder allowlist.")
    return "\n".join(lines)


def detected_drives_summary() -> str:
    drives = detect_drives()
    if not drives:
        return "Detected Windows drives: none found. This command is read-only."

    lines = ["Detected Windows drives (read-only):"]
    lines.extend(f"- {drive.name}: {drive.path}" for drive in drives)
    lines.append("Nothing was added to the folder allowlist.")
    return "\n".join(lines)


def detected_locations_summary() -> str:
    return f"{detected_folders_summary()}\n\n{detected_drives_summary()}"
