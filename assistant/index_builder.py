"""System index building and management."""

from __future__ import annotations

from pathlib import Path

from assistant.index_store import IndexStore
from assistant.settings import AssistantSettings, load_settings
from assistant.system_scanner import ScannerConfig, SystemScanner


class IndexBuildError(RuntimeError):
    """Raised when index building fails."""


class IndexBuilder:
    """Builds and maintains the system index."""

    def __init__(self, settings: AssistantSettings | None = None) -> None:
        if settings is None:
            try:
                settings = load_settings()
            except Exception as exc:
                raise IndexBuildError(f"Failed to load settings: {exc}")

        if not settings.system_indexing_enabled:
            raise IndexBuildError("System indexing is disabled in settings")

        self.settings = settings
        self.store = IndexStore(Path(settings.system_index_path))
        self.scanner = SystemScanner(ScannerConfig())

    def build_index_interactive(self) -> str:
        """Build index by scanning common Windows locations."""
        try:
            # Start with an empty index
            from assistant.system_index import SystemIndex
            index = SystemIndex()

            # Scan common user folders first
            common_folders = self.scanner.get_common_user_folders()
            total_items_before = index.total_items

            for folder in common_folders:
                print(f"Scanning {folder.name}...")
                try:
                    items = self.scanner.scan_folder(folder, include_subfolders=True)
                    for item in items:
                        index.add_item(item)
                except Exception as e:
                    print(f"  Warning: Error scanning {folder}: {e}")
                    continue

            # Scan Program Files for applications
            print("Scanning Program Files...")
            try:
                pf_32 = Path("C:/Program Files (x86)")
                pf_64 = Path("C:/Program Files")

                if pf_32.exists():
                    items = self.scanner.scan_folder(pf_32, include_subfolders=True)
                    for item in items:
                        index.add_item(item)

                if pf_64.exists():
                    items = self.scanner.scan_folder(pf_64, include_subfolders=True)
                    for item in items:
                        index.add_item(item)
            except Exception as e:
                print(f"  Warning: Error scanning Program Files: {e}")

            # Detect applications (shortcuts, apps)
            print("Detecting applications...")
            try:
                apps = self.scanner.detect_applications()
                for app in apps:
                    index.add_item(app)

                shortcuts = self.scanner.detect_shortcuts()
                for shortcut in shortcuts:
                    index.add_item(shortcut)
            except Exception as e:
                print(f"  Warning: Error detecting applications: {e}")

            # Save index
            self.store.save_index(index)

            new_items = index.total_items - total_items_before
            return (
                f"Index build complete!\n"
                f"Total items: {index.total_items}\n"
                f"New items: {new_items}\n"
                f"Saved to: {self.settings.system_index_path}"
            )
        except Exception as exc:
            raise IndexBuildError(f"Index build failed: {exc}")

    def rebuild_index(self) -> str:
        """Rebuild entire index from scratch."""
        return self.build_index_interactive()

    def build_full_system_index(self) -> str:
        """Build comprehensive index by scanning all available local drives."""
        try:
            from assistant.system_index import SystemIndex
            index = SystemIndex()

            # Get all available drives
            available_drives = self.scanner.scan_drives()
            print(f"Found {len(available_drives)} drive(s): {', '.join([f'{d}:' for d in available_drives])}")

            # Scan each drive
            for drive_letter in available_drives:
                print(f"Scanning drive {drive_letter}:/...")
                try:
                    items = self.scanner.scan_drive(drive_letter)
                    for item in items:
                        index.add_item(item)
                    print(f"  ✓ Drive {drive_letter}:/ complete ({len(items)} items)")
                except Exception as e:
                    print(f"  ✗ Error scanning drive {drive_letter}:/: {e}")
                    continue

            # Ensure applications are indexed
            print("Detecting applications...")
            try:
                apps = self.scanner.detect_applications()
                for app in apps:
                    # Only add if not already present (avoid duplicates from drive scan)
                    if index.get_item(app.id) is None:
                        index.add_item(app)

                shortcuts = self.scanner.detect_shortcuts()
                for shortcut in shortcuts:
                    if index.get_item(shortcut.id) is None:
                        index.add_item(shortcut)
            except Exception as e:
                print(f"  Warning: Error detecting applications: {e}")

            # Save index
            self.store.save_index(index)

            return (
                f"Full system scan complete!\n"
                f"Total items indexed: {index.total_items}\n"
                f"Drives scanned: {', '.join([f'{d}:' for d in available_drives])}\n"
                f"Saved to: {self.settings.system_index_path}"
            )
        except Exception as exc:
            raise IndexBuildError(f"Full system scan failed: {exc}")

    def build_drive_index(self, drive_letter: str) -> str:
        """Build index for a specific drive."""
        try:
            from assistant.system_index import SystemIndex
            
            # Validate drive letter
            if len(drive_letter) != 1 or not drive_letter.isalpha():
                raise IndexBuildError(f"Invalid drive letter: {drive_letter}")
            
            drive_letter = drive_letter.upper()
            drive_path = Path(f"{drive_letter}:\\")
            
            if not drive_path.exists():
                raise IndexBuildError(f"Drive {drive_letter}:/ does not exist or is not accessible")

            index = SystemIndex()
            print(f"Scanning drive {drive_letter}:/...")

            try:
                items = self.scanner.scan_drive(drive_letter)
                for item in items:
                    index.add_item(item)
            except Exception as e:
                raise IndexBuildError(f"Error scanning drive {drive_letter}:/: {e}")

            # Save index
            self.store.save_index(index)

            return (
                f"Drive scan complete!\n"
                f"Total items on {drive_letter}:/: {index.total_items}\n"
                f"Saved to: {self.settings.system_index_path}"
            )
        except IndexBuildError:
            raise
        except Exception as exc:
            raise IndexBuildError(f"Drive scan failed: {exc}")

    def get_index_stats(self) -> str:
        """Get statistics about current index."""
        try:
            index = self.store.load_index()

            file_count = len(index.get_items_by_type("file"))
            folder_count = len(index.get_items_by_type("folder"))
            app_count = len(index.get_items_by_type("app"))
            shortcut_count = len(index.get_items_by_type("shortcut"))

            return (
                f"Index Statistics:\n"
                f"  Total items: {index.total_items}\n"
                f"  Files: {file_count}\n"
                f"  Folders: {folder_count}\n"
                f"  Applications: {app_count}\n"
                f"  Shortcuts: {shortcut_count}\n"
                f"  Last scan: {index.last_scan}"
            )
        except Exception as exc:
            raise IndexBuildError(f"Failed to get index stats: {exc}")
