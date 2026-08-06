"""Core indexing system for files, folders, and applications."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


class SystemIndexError(RuntimeError):
    """Raised when system indexing operations fail."""


@dataclass(frozen=True)
class IndexedItem:
    """Represents a single indexed file, folder, shortcut, or application."""

    id: str  # Unique hash-based identifier
    name: str  # Display name (filename or app name)
    full_path: str  # Complete path as string for JSON serialization
    item_type: Literal["file", "folder", "app", "shortcut"]
    file_extension: str  # ".pdf", ".exe", "" for folders
    size_bytes: int  # File size (0 for folders/apps)
    created_date: str  # ISO format datetime
    modified_date: str  # ISO format datetime
    accessed_date: str  # ISO format datetime
    drive: str  # "C", "D", etc.
    is_hidden: bool
    is_system: bool  # Whether it's a system file
    priority_score: float = 0.5  # Base relevance (0.0-1.0)
    access_count: int = 0  # Number of times accessed by user
    last_accessed: str = ""  # ISO format datetime

    @property
    def path(self) -> Path:
        """Return path as Path object."""
        return Path(self.full_path)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "full_path": self.full_path,
            "item_type": self.item_type,
            "file_extension": self.file_extension,
            "size_bytes": self.size_bytes,
            "created_date": self.created_date,
            "modified_date": self.modified_date,
            "accessed_date": self.accessed_date,
            "drive": self.drive,
            "is_hidden": self.is_hidden,
            "is_system": self.is_system,
            "priority_score": self.priority_score,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> IndexedItem:
        """Create from dictionary (reverse of to_dict)."""
        return cls(
            id=data["id"],
            name=data["name"],
            full_path=data["full_path"],
            item_type=data["item_type"],
            file_extension=data["file_extension"],
            size_bytes=data["size_bytes"],
            created_date=data["created_date"],
            modified_date=data["modified_date"],
            accessed_date=data["accessed_date"],
            drive=data["drive"],
            is_hidden=data["is_hidden"],
            is_system=data["is_system"],
            priority_score=data.get("priority_score", 0.5),
            access_count=data.get("access_count", 0),
            last_accessed=data.get("last_accessed", ""),
        )


@dataclass
class SystemIndex:
    """Main index for managing indexed items."""

    items: dict[str, IndexedItem] = field(default_factory=dict)  # id -> IndexedItem
    last_scan: str = ""  # ISO format datetime
    total_items: int = 0

    def add_item(self, item: IndexedItem) -> None:
        """Add an item to the index."""
        if not item.id:
            raise SystemIndexError("Item must have an id")
        self.items[item.id] = item
        self.total_items = len(self.items)

    def remove_item(self, item_id: str) -> None:
        """Remove an item from the index."""
        if item_id in self.items:
            del self.items[item_id]
            self.total_items = len(self.items)

    def update_item(self, item: IndexedItem) -> None:
        """Update an existing item in the index."""
        if item.id not in self.items:
            raise SystemIndexError(f"Item {item.id} not found in index")
        self.items[item.id] = item

    def get_item(self, item_id: str) -> IndexedItem | None:
        """Get an item by ID."""
        return self.items.get(item_id)

    def get_all_items(self) -> list[IndexedItem]:
        """Get all items in the index."""
        return list(self.items.values())

    def get_items_by_type(self, item_type: Literal["file", "folder", "app", "shortcut"]) -> list[IndexedItem]:
        """Get all items of a specific type."""
        return [item for item in self.items.values() if item.item_type == item_type]

    def get_items_by_drive(self, drive: str) -> list[IndexedItem]:
        """Get all items on a specific drive."""
        return [item for item in self.items.values() if item.drive == drive]

    def get_items_by_extension(self, extension: str) -> list[IndexedItem]:
        """Get all items with a specific extension."""
        return [item for item in self.items.values() if item.file_extension.lower() == extension.lower()]

    def clear(self) -> None:
        """Clear all items from the index."""
        self.items.clear()
        self.total_items = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "items": {item_id: item.to_dict() for item_id, item in self.items.items()},
            "last_scan": self.last_scan,
            "total_items": self.total_items,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SystemIndex:
        """Create from dictionary (reverse of to_dict)."""
        index = cls()
        index.last_scan = data.get("last_scan", "")
        index.total_items = data.get("total_items", 0)
        for item_id, item_data in data.get("items", {}).items():
            item = IndexedItem.from_dict(item_data)
            index.items[item_id] = item
        return index


def generate_item_id(path: Path | str) -> str:
    """Generate a unique ID for an item based on its path."""
    path_str = str(path).lower()
    return hashlib.sha256(path_str.encode()).hexdigest()[:16]


def create_indexed_item(
    path: Path,
    item_type: Literal["file", "folder", "app", "shortcut"],
    name: str | None = None,
    priority_score: float = 0.5,
) -> IndexedItem:
    """Create an IndexedItem from a file system path."""
    if item_type == "folder" and not path.is_dir():
        raise SystemIndexError(f"Path is not a directory: {path}")
    if item_type == "file" and not path.is_file():
        raise SystemIndexError(f"Path is not a file: {path}")

    # Get file stats
    try:
        stat = path.stat()
        created_date = datetime.fromtimestamp(stat.st_ctime).isoformat()
        modified_date = datetime.fromtimestamp(stat.st_mtime).isoformat()
        accessed_date = datetime.fromtimestamp(stat.st_atime).isoformat()
        size_bytes = stat.st_size if item_type == "file" else 0
    except OSError as exc:
        raise SystemIndexError(f"Cannot access path: {path}") from exc

    # Extract drive letter (Windows)
    drive = path.drive[0].upper() if path.drive else "C"

    # Use provided name or extract from path
    display_name = name or path.name

    return IndexedItem(
        id=generate_item_id(path),
        name=display_name,
        full_path=str(path.resolve()),
        item_type=item_type,
        file_extension=path.suffix.lower(),
        size_bytes=size_bytes,
        created_date=created_date,
        modified_date=modified_date,
        accessed_date=accessed_date,
        drive=drive,
        is_hidden=path.name.startswith("."),
        is_system=False,
        priority_score=priority_score,
    )
