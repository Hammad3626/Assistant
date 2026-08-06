"""Persistent storage for system index and access preferences."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from assistant.system_index import IndexedItem, SystemIndex, SystemIndexError


class IndexStoreError(RuntimeError):
    """Raised when index store operations fail."""


class IndexStore:
    """Persistent storage for the system index (JSONL format)."""

    def __init__(self, index_path: Path | str) -> None:
        self.index_path = Path(index_path)
        self.metadata_path = self.index_path.parent / (self.index_path.stem + "_metadata.json")

    def save_index(self, index: SystemIndex) -> None:
        """Save index to disk in JSONL format."""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            # Write items as JSONL
            with open(self.index_path, "w", encoding="utf-8") as f:
                for item in index.get_all_items():
                    f.write(json.dumps(item.to_dict()) + "\n")

            # Write metadata
            metadata = {
                "total_items": index.total_items,
                "last_scan": index.last_scan,
                "saved_at": datetime.now().isoformat(),
                "version": "1.0",
            }
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

        except Exception as exc:
            raise IndexStoreError(f"Failed to save index: {exc}") from exc

    def load_index(self) -> SystemIndex:
        """Load index from disk."""
        index = SystemIndex()

        if not self.index_path.exists():
            return index

        try:
            # Load metadata if available
            if self.metadata_path.exists():
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    index.last_scan = metadata.get("last_scan", "")

            # Load items from JSONL
            with open(self.index_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item_data = json.loads(line)
                        item = IndexedItem.from_dict(item_data)
                        index.add_item(item)

        except Exception as exc:
            raise IndexStoreError(f"Failed to load index: {exc}") from exc

        return index

    def add_item(self, item: IndexedItem) -> None:
        """Add a single item to the store (append to JSONL)."""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.index_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(item.to_dict()) + "\n")
        except Exception as exc:
            raise IndexStoreError(f"Failed to add item: {exc}") from exc

    def remove_item(self, item_id: str) -> None:
        """Remove an item from the store by rewriting the JSONL file."""
        try:
            index = self.load_index()
            index.remove_item(item_id)
            self.save_index(index)
        except Exception as exc:
            raise IndexStoreError(f"Failed to remove item: {exc}") from exc

    def update_item(self, item: IndexedItem) -> None:
        """Update an item by rewriting the JSONL file."""
        try:
            index = self.load_index()
            index.update_item(item)
            self.save_index(index)
        except Exception as exc:
            raise IndexStoreError(f"Failed to update item: {exc}") from exc

    def get_item_count(self) -> int:
        """Get total number of items in the store."""
        if not self.index_path.exists():
            return 0

        try:
            count = 0
            with open(self.index_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
            return count
        except Exception:
            return 0

    def clear(self) -> None:
        """Clear all items from the store."""
        try:
            if self.index_path.exists():
                self.index_path.unlink()
            if self.metadata_path.exists():
                self.metadata_path.unlink()
        except Exception as exc:
            raise IndexStoreError(f"Failed to clear store: {exc}") from exc


class PreferencesStore:
    """Persistent storage for user access preferences and aliases."""

    def __init__(self, prefs_path: Path | str) -> None:
        self.prefs_path = Path(prefs_path)
        # Initialize data structures
        self._access_history: dict[str, int] = {}  # item_id -> access_count
        self._aliases: dict[str, str] = {}  # alias -> item_id
        self._load()

    def _load(self) -> None:
        """Load preferences from disk."""
        if self.prefs_path.exists():
            try:
                with open(self.prefs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._access_history = data.get("access_history", {})
                    self._aliases = data.get("aliases", {})
            except Exception:
                self._access_history = {}
                self._aliases = {}
        else:
            self._access_history = {}
            self._aliases = {}

    def _save(self) -> None:
        """Save preferences to disk."""
        try:
            self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "access_history": self._access_history,
                "aliases": self._aliases,
                "saved_at": datetime.now().isoformat(),
            }
            with open(self.prefs_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            raise IndexStoreError(f"Failed to save preferences: {exc}") from exc

    def record_access(self, item_id: str) -> None:
        """Record that an item was accessed by the user."""
        if not item_id:
            return
        self._access_history[item_id] = self._access_history.get(item_id, 0) + 1
        self._save()

    def get_access_count(self, item_id: str) -> int:
        """Get how many times an item was accessed."""
        return self._access_history.get(item_id, 0)

    def get_frequently_accessed(self, limit: int = 20) -> list[tuple[str, int]]:
        """Get the most frequently accessed items."""
        sorted_items = sorted(self._access_history.items(), key=lambda x: x[1], reverse=True)
        return sorted_items[:limit]

    def set_alias(self, alias: str, item_id: str) -> None:
        """Set a user-defined alias for an item."""
        if not alias or not item_id:
            raise IndexStoreError("Alias and item_id cannot be empty")
        self._aliases[alias.lower()] = item_id
        self._save()

    def get_alias(self, alias: str) -> str | None:
        """Get the item ID for an alias."""
        return self._aliases.get(alias.lower())

    def list_aliases(self) -> dict[str, str]:
        """Get all aliases."""
        return self._aliases.copy()

    def remove_alias(self, alias: str) -> None:
        """Remove an alias."""
        if alias.lower() in self._aliases:
            del self._aliases[alias.lower()]
            self._save()
