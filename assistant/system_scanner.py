"""Filesystem scanner for building the system index."""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Literal

from assistant.system_index import IndexedItem, SystemIndex, SystemIndexError, create_indexed_item, generate_item_id


class ScannerConfig:
    """Configuration for the system scanner."""

    def __init__(
        self,
        max_depth: int = 10,
        skip_hidden: bool = True,
        skip_patterns: list[str] | None = None,
        max_workers: int = 4,
        include_system_folders: bool = False,
    ) -> None:
        self.max_depth = max_depth
        self.skip_hidden = skip_hidden
        self.skip_patterns = skip_patterns or [
            r"^\$RECYCLE\.BIN$",
            r"^\..*",  # Hidden files
            r".*AppData.*",
            r".*System32.*",
            r".*Windows.*",
            r".*Program Files.*\\.*",  # Exclude Program Files subdirs (scan only top level)
            r".*ProgramData.*",
            r".*node_modules.*",
            r".*\.git.*",
            r".*\.venv.*",
            r".*venv.*",
        ]
        self.max_workers = max_workers
        self.include_system_folders = include_system_folders

    def should_skip_pattern(self, path: Path) -> bool:
        """Check if path matches any skip patterns."""
        path_str = str(path)
        for pattern in self.skip_patterns:
            if re.search(pattern, path_str, re.IGNORECASE):
                return True
        return False

    def should_skip_hidden(self, path: Path) -> bool:
        """Check if path is hidden and should be skipped."""
        return self.skip_hidden and path.name.startswith(".")


class SystemScanner:
    """Scans the filesystem to build system index."""

    def __init__(self, config: ScannerConfig | None = None) -> None:
        self.config = config or ScannerConfig()
        self.index = SystemIndex()
        self.scanned_count = 0
        self.error_count = 0

    def scan_drives(self) -> list[str]:
        """Get list of available drive letters on Windows."""
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = Path(f"{letter}:\\")
            if drive_path.exists():
                drives.append(letter)
        return drives

    def scan_drive(self, drive: str, skip_protected: bool = True) -> list[IndexedItem]:
        """Scan entire drive starting from root."""
        drive_path = Path(f"{drive}:\\")
        if not drive_path.exists():
            return []

        items = []
        try:
            items = self._scan_folder_recursive(drive_path, depth=0)
        except Exception as exc:
            print(f"Error scanning drive {drive}:\\: {exc}")
            self.error_count += 1

        return items

    def scan_folder(self, folder: Path, include_subfolders: bool = True) -> list[IndexedItem]:
        """Scan a specific folder."""
        if not folder.exists() or not folder.is_dir():
            raise SystemIndexError(f"Folder does not exist: {folder}")

        if include_subfolders:
            return self._scan_folder_recursive(folder, depth=0)
        else:
            return self._scan_folder_flat(folder)

    def _scan_folder_flat(self, folder: Path) -> list[IndexedItem]:
        """Scan folder without recursion."""
        items = []
        try:
            for entry in folder.iterdir():
                if self.config.should_skip_hidden(entry) or self.config.should_skip_pattern(entry):
                    continue
                try:
                    if entry.is_file():
                        item = create_indexed_item(entry, "file")
                        items.append(item)
                        self.scanned_count += 1
                    elif entry.is_dir():
                        item = create_indexed_item(entry, "folder")
                        items.append(item)
                        self.scanned_count += 1
                except (OSError, PermissionError):
                    self.error_count += 1
        except (OSError, PermissionError):
            pass

        return items

    def _scan_folder_recursive(self, folder: Path, depth: int = 0) -> list[IndexedItem]:
        """Recursively scan folder up to max depth."""
        items = []

        # Stop if max depth exceeded
        if depth >= self.config.max_depth:
            return items

        try:
            for entry in folder.iterdir():
                # Skip patterns
                if self.config.should_skip_hidden(entry) or self.config.should_skip_pattern(entry):
                    continue

                try:
                    if entry.is_file():
                        item = create_indexed_item(entry, "file")
                        items.append(item)
                        self.scanned_count += 1
                    elif entry.is_dir():
                        item = create_indexed_item(entry, "folder")
                        items.append(item)
                        self.scanned_count += 1

                        # Recursively scan subdirectory
                        items.extend(self._scan_folder_recursive(entry, depth + 1))

                except (OSError, PermissionError):
                    self.error_count += 1
                    continue

        except (OSError, PermissionError):
            pass

        return items

    def detect_applications(self) -> list[IndexedItem]:
        """Detect installed applications from Program Files and Start Menu."""
        apps = []

        # Scan Program Files
        program_files = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        ]

        for pf in program_files:
            if pf.exists():
                # Only scan top-level apps, not subdirs
                try:
                    for entry in pf.iterdir():
                        if entry.is_dir():
                            item = create_indexed_item(entry, "app", priority_score=0.7)
                            apps.append(item)
                            self.scanned_count += 1
                except (OSError, PermissionError):
                    self.error_count += 1

        # Scan Start Menu
        appdata = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu"
        if appdata.exists():
            try:
                for entry in appdata.rglob("*.lnk"):
                    item = create_indexed_item(entry, "shortcut", priority_score=0.75)
                    apps.append(item)
                    self.scanned_count += 1
            except (OSError, PermissionError):
                self.error_count += 1

        # Scan common app locations
        common_app_dirs = [
            Path.home() / "AppData" / "Local" / "Programs",
            Path("C:\\Users") if Path("C:\\Users").exists() else None,
        ]

        for app_dir in common_app_dirs:
            if app_dir and app_dir.exists():
                try:
                    items = self._scan_folder_flat(app_dir)
                    apps.extend([item for item in items if item.file_extension.lower() in [".exe", ".lnk"]])
                except (OSError, PermissionError):
                    self.error_count += 1

        return apps

    def detect_shortcuts(self) -> list[IndexedItem]:
        """Detect shortcuts on Desktop and Start Menu."""
        shortcuts = []

        # Desktop shortcuts
        desktop = Path.home() / "Desktop"
        if desktop.exists():
            try:
                for entry in desktop.glob("*.lnk"):
                    item = create_indexed_item(entry, "shortcut", priority_score=0.8)
                    shortcuts.append(item)
                    self.scanned_count += 1
            except (OSError, PermissionError):
                self.error_count += 1

        # Start Menu shortcuts
        start_menu = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu"
        if start_menu.exists():
            try:
                for entry in start_menu.rglob("*.lnk"):
                    item = create_indexed_item(entry, "shortcut", priority_score=0.75)
                    shortcuts.append(item)
                    self.scanned_count += 1
            except (OSError, PermissionError):
                self.error_count += 1

        return shortcuts

    def get_common_user_folders(self) -> list[Path]:
        """Get common user-important folders."""
        folders = [
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
            Path.home() / "Music",
            Path.home() / "Pictures",
            Path.home() / "Videos",
            Path.home() / "AppData" / "Roaming",
        ]
        return [f for f in folders if f.exists()]
