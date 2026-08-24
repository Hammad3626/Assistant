"""Named backup and maintenance operations for allowlisted folders.

These are implemented as plain Python file operations rather than shell
commands, so there is no subprocess/argv involved at all:

- backup_folder() copies an allowlisted folder to a timestamped destination.
  It never modifies or removes anything in the source folder.
- find_temp_files() / clear_temp_files() identify common temp-file clutter
  (*.tmp, *.log, Thumbs.db, etc.) inside an allowlisted folder. Removal
  always goes through the existing reversible file-trash mechanism
  (AllowlistedFileTools.move_file_to_trash) -- never a permanent delete.
"""

from __future__ import annotations

import fnmatch
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from assistant.actions import DEFAULT_FOLDERS_PATH, load_allowed_folders


UTC = timezone.utc

DEFAULT_BACKUP_ROOT = Path("data/backups")
MAX_BACKUP_FILES = 20_000
TEMP_FILE_PATTERNS = ("*.tmp", "*.temp", "*.log", "*.bak", "~*", "Thumbs.db", ".DS_Store")


class BackupToolError(RuntimeError):
    """Raised when a backup or maintenance operation cannot proceed safely."""


@dataclass(frozen=True)
class BackupResult:
    folder_name: str
    source: str
    destination: str
    file_count: int
    created_at: str


@dataclass(frozen=True)
class TempFileMatch:
    folder_name: str
    relative_path: str
    size_bytes: int


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_allowed_folder(folder_name: str, folders_path: str | Path) -> tuple[str, Path]:
    """Resolve a folder name against the existing folders allowlist.

    Backups/maintenance may only ever operate on folders already present in
    the user's folder allowlist -- never an arbitrary path -- so this reuses
    the exact same allowlist the rest of the app already trusts.
    """
    folders = load_allowed_folders(folders_path)
    clean_name = " ".join(folder_name.strip().lower().split())
    if clean_name not in folders:
        available = ", ".join(sorted(folders)) or "(none configured)"
        raise BackupToolError(
            f"'{folder_name}' is not an allowlisted folder. Available folders: {available}"
        )
    root = Path(folders[clean_name])
    if not root.exists() or not root.is_dir():
        raise BackupToolError(f"Allowlisted folder no longer exists on disk: {root}")
    return clean_name, root


def backup_folder(
    folder_name: str,
    folders_path: str | Path = DEFAULT_FOLDERS_PATH,
    backup_root: str | Path = DEFAULT_BACKUP_ROOT,
) -> BackupResult:
    """Copy an allowlisted folder to a new timestamped backup destination.

    This never touches the source folder -- it is a pure, additive copy.
    """
    canonical_name, source_root = _resolve_allowed_folder(folder_name, folders_path)

    file_count = sum(1 for p in source_root.rglob("*") if p.is_file())
    if file_count > MAX_BACKUP_FILES:
        raise BackupToolError(
            f"'{canonical_name}' has {file_count} files, over the {MAX_BACKUP_FILES} "
            "safety limit for a single backup operation."
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = canonical_name.replace(" ", "_")
    destination = Path(backup_root) / safe_name / timestamp
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copytree(source_root, destination)
    except OSError as exc:
        raise BackupToolError(f"Backup failed: {exc}") from exc

    result = BackupResult(
        folder_name=canonical_name,
        source=str(source_root),
        destination=str(destination),
        file_count=file_count,
        created_at=_utc_now_iso(),
    )
    _record_backup(result, backup_root)
    return result


def _record_backup(result: BackupResult, backup_root: str | Path) -> None:
    manifest_path = Path(backup_root) / "backups_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict) and isinstance(raw.get("backups"), list):
                records = raw["backups"]
        except (json.JSONDecodeError, OSError):
            records = []
    records.append(
        {
            "id": uuid4().hex,
            "folder_name": result.folder_name,
            "source": result.source,
            "destination": result.destination,
            "file_count": result.file_count,
            "created_at": result.created_at,
        }
    )
    manifest_path.write_text(json.dumps({"backups": records}, indent=2) + "\n", encoding="utf-8")


def list_backups(
    folder_name: str | None = None,
    backup_root: str | Path = DEFAULT_BACKUP_ROOT,
) -> list[dict[str, object]]:
    manifest_path = Path(backup_root) / "backups_manifest.json"
    if not manifest_path.exists():
        return []
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    records = raw.get("backups", []) if isinstance(raw, dict) else []
    if folder_name is None:
        return records
    clean_name = " ".join(folder_name.strip().lower().split())
    return [r for r in records if r.get("folder_name") == clean_name]


def find_temp_files(
    folder_name: str,
    folders_path: str | Path = DEFAULT_FOLDERS_PATH,
    patterns: tuple[str, ...] = TEMP_FILE_PATTERNS,
    limit: int = 500,
) -> list[TempFileMatch]:
    """List files inside an allowlisted folder that match common temp-file
    patterns. Does not modify or move anything -- pure read-only scan.
    """
    canonical_name, root = _resolve_allowed_folder(folder_name, folders_path)

    matches: list[TempFileMatch] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            matches.append(
                TempFileMatch(
                    folder_name=canonical_name,
                    relative_path=str(path.relative_to(root)),
                    size_bytes=size,
                )
            )
            if len(matches) >= limit:
                break
    return matches
