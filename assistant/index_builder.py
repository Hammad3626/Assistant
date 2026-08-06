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
