"""Safe file listing, preview, search, and reversible trash for allowlisted folders."""

from __future__ import annotations

import json
import hashlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from assistant.actions import DEFAULT_FOLDERS_PATH, ActionError, load_allowed_folders, normalize_action_text


TEXT_EXTENSIONS = {
    ".bat",
    ".cfg",
    ".csv",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
SKIPPED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "exports",
    "node_modules",
    "venv",
}
MAX_LIST_ITEMS = 50
MAX_READ_BYTES = 256_000
MAX_READ_CHARS = 4_000
MAX_SEARCH_BYTES = 512_000
MAX_SEARCH_RESULTS = 20
MAX_BULK_PLAN_ITEMS = 30
DEFAULT_FILE_TRASH_DIR = Path("data/file_trash")
DEFAULT_FILE_TRASH_MANIFEST = Path("data/file_trash/manifest.json")
DEFAULT_BULK_BACKUP_DIR = Path("exports/bulk-file-backups")
DEFAULT_BULK_APPROVAL_DIR = Path("exports/bulk-file-approvals")
DEFAULT_BULK_REVIEW_DIR = Path("exports/bulk-apply-reviews")
DEFAULT_BULK_ROLLBACK_DIR = Path("exports/bulk-rollback-plans")
DEFAULT_BULK_PREFLIGHT_DIR = Path("exports/bulk-write-preflights")
DEFAULT_BULK_CHECKLIST_DIR = Path("exports/bulk-review-checklists")
BULK_PREFLIGHT_REVIEW_SCHEMA = "bulk_write_preflight_review_v1"
BULK_OPERATOR_CHECKLIST_SCHEMA = "bulk_operator_checklist_v1"


class FileToolError(RuntimeError):
    """Raised when a read-only file tool request is unsafe or cannot run."""


@dataclass(frozen=True)
class FileSearchResult:
    folder_name: str
    relative_path: str
    line_number: int
    line_text: str


@dataclass(frozen=True)
class FileNameSearchResult:
    folder_name: str
    relative_path: str


@dataclass(frozen=True)
class BulkReplacePlanItem:
    relative_path: str
    match_count: int


@dataclass(frozen=True)
class BulkRenamePlanItem:
    old_relative_path: str
    new_relative_path: str
    conflict: bool = False


@dataclass(frozen=True)
class BulkApplyReviewResult:
    summary: str
    review_dir: Path
    audit_description: str


@dataclass(frozen=True)
class BulkRollbackPlanResult:
    summary: str
    rollback_dir: Path
    audit_description: str


@dataclass(frozen=True)
class BulkWritePreflightResult:
    summary: str
    preflight_dir: Path
    audit_description: str


@dataclass(frozen=True)
class BulkOperatorChecklistResult:
    summary: str
    checklist_dir: Path
    manifest_path: Path
    checklist_path: Path
    audit_description: str


@dataclass(frozen=True)
class BulkOperatorChecklistVerification:
    summary: str
    checklist_dir: Path | None
    status: str
    audit_description: str


@dataclass(frozen=True)
class FileTrashEntry:
    original_folder_name: str
    original_relative_path: str
    trash_path: str
    deleted_at: str

    def display_text(self) -> str:
        return f"{self.original_folder_name}/{self.original_relative_path}"


class AllowlistedFileTools:
    """Safe file tools scoped to configured allowed folders."""

    def __init__(
        self,
        folders_path: str | Path = DEFAULT_FOLDERS_PATH,
        trash_dir: str | Path = DEFAULT_FILE_TRASH_DIR,
        manifest_path: str | Path = DEFAULT_FILE_TRASH_MANIFEST,
        bulk_backup_dir: str | Path = DEFAULT_BULK_BACKUP_DIR,
        bulk_approval_dir: str | Path = DEFAULT_BULK_APPROVAL_DIR,
        bulk_review_dir: str | Path = DEFAULT_BULK_REVIEW_DIR,
        bulk_rollback_dir: str | Path = DEFAULT_BULK_ROLLBACK_DIR,
        bulk_preflight_dir: str | Path = DEFAULT_BULK_PREFLIGHT_DIR,
        bulk_checklist_dir: str | Path = DEFAULT_BULK_CHECKLIST_DIR,
    ) -> None:
        self.folders_path = Path(folders_path)
        self.trash_dir = Path(trash_dir)
        self.manifest_path = Path(manifest_path)
        self.bulk_backup_dir = Path(bulk_backup_dir)
        self.bulk_approval_dir = Path(bulk_approval_dir)
        self.bulk_review_dir = Path(bulk_review_dir)
        self.bulk_rollback_dir = Path(bulk_rollback_dir)
        self.bulk_preflight_dir = Path(bulk_preflight_dir)
        self.bulk_checklist_dir = Path(bulk_checklist_dir)

    def folder_names(self) -> list[str]:
        return sorted(self._allowed_folders())

    def list_files_summary(self, folder_name: str, limit: int = MAX_LIST_ITEMS) -> str:
        canonical_name, root = self._resolve_folder(folder_name)
        entries = self._list_files(root, limit=limit)
        if not entries:
            return f"No readable files found in allowlisted folder: {canonical_name}"

        lines = [f"Readable files in {canonical_name}:"]
        for index, path in enumerate(entries, start=1):
            lines.append(f"{index}. {_relative_text(path, root)}")
        if len(entries) == limit:
            lines.append(f"Showing first {limit} readable file(s).")
        return "\n".join(lines)

    def read_file_summary(self, folder_name: str, relative_path: str) -> str:
        canonical_name, root = self._resolve_folder(folder_name)
        file_path = self._resolve_file(root, relative_path)
        self._validate_text_file(file_path, max_bytes=MAX_READ_BYTES)

        try:
            text = file_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            raise FileToolError(f"Could not read file: {_relative_text(file_path, root)}") from exc

        preview = text[:MAX_READ_CHARS]
        lines = [
            f"File preview from {canonical_name}: {_relative_text(file_path, root)}",
            preview.rstrip() if preview else "(empty file)",
        ]
        if len(text) > MAX_READ_CHARS:
            lines.append(f"Preview truncated at {MAX_READ_CHARS} character(s).")
        return "\n".join(lines)

    def open_file_preview_summary(self, folder_name: str, relative_path: str) -> str:
        """Return a safe in-assistant preview instead of launching the file."""
        preview = self.read_file_summary(folder_name, relative_path)
        return (
            "Safe file open preview\n"
            "The file was not launched in Windows. Showing a local text preview instead.\n"
            f"{preview}"
        )

    def move_file_to_trash(self, folder_name: str, relative_path: str) -> FileTrashEntry:
        canonical_name, root = self._resolve_folder(folder_name)
        file_path = self.validate_trash_candidate(canonical_name, relative_path)

        entries = self.list_file_trash()
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        trash_name = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex}-{file_path.name}"
        trash_path = self.trash_dir / trash_name
        try:
            shutil.move(str(file_path), trash_path)
        except OSError as exc:
            raise FileToolError(f"Could not move file to assistant trash: {relative_path}") from exc

        entry = FileTrashEntry(
            original_folder_name=canonical_name,
            original_relative_path=_relative_text(file_path, root),
            trash_path=str(trash_path),
            deleted_at=_utc_now_iso(),
        )
        entries.append(entry)
        self._write_file_trash(entries)
        return entry

    def move_temp_pattern_file_to_trash(
        self, folder_name: str, relative_path: str, allowed_patterns: tuple[str, ...]
    ) -> FileTrashEntry:
        """Move a file matching a known temp-file pattern (*.tmp, Thumbs.db,
        etc.) to the assistant trash, bypassing the general TEXT_EXTENSIONS
        restriction used by move_file_to_trash().

        This exists specifically for maintenance/cleanup flows: real temp
        clutter is rarely a "common text file" (it's .tmp/.bak/Thumbs.db/
        .DS_Store/etc.), so the stricter text-only check would otherwise
        block clearing it. The safety net here is the explicit pattern
        allowlist the caller must supply -- only files matching a known,
        narrow junk-file pattern can go through this path, never an
        arbitrary extension.
        """
        import fnmatch as _fnmatch

        canonical_name, root = self._resolve_folder(folder_name)
        file_path = self._resolve_file(root, relative_path)
        self._reject_trash_storage_path(file_path)
        if not any(_fnmatch.fnmatch(file_path.name, pattern) for pattern in allowed_patterns):
            raise FileToolError(
                f"'{relative_path}' does not match a known temp-file pattern; refusing to trash it."
            )

        entries = self.list_file_trash()
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        trash_name = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex}-{file_path.name}"
        trash_path = self.trash_dir / trash_name
        try:
            shutil.move(str(file_path), trash_path)
        except OSError as exc:
            raise FileToolError(f"Could not move file to assistant trash: {relative_path}") from exc

        entry = FileTrashEntry(
            original_folder_name=canonical_name,
            original_relative_path=_relative_text(file_path, root),
            trash_path=str(trash_path),
            deleted_at=_utc_now_iso(),
        )
        entries.append(entry)
        self._write_file_trash(entries)
        return entry

    def validate_trash_candidate(self, folder_name: str, relative_path: str) -> Path:
        """Return the resolved file path if it can be moved to assistant trash."""
        _, root = self._resolve_folder(folder_name)
        file_path = self._resolve_file(root, relative_path)
        self._reject_trash_storage_path(file_path)
        if file_path.suffix.lower() not in TEXT_EXTENSIONS:
            raise FileToolError("Only common text files can be moved to assistant trash.")
        return file_path

    def list_file_trash(self) -> list[FileTrashEntry]:
        if not self.manifest_path.exists():
            return []
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise FileToolError(f"Invalid file trash manifest: {self.manifest_path}") from exc
        except OSError as exc:
            raise FileToolError(f"Could not read file trash manifest: {self.manifest_path}") from exc

        if not isinstance(raw, dict) or not isinstance(raw.get("deleted_files"), list):
            raise FileToolError("File trash manifest must contain a 'deleted_files' array.")

        entries: list[FileTrashEntry] = []
        for item in raw["deleted_files"]:
            if not isinstance(item, dict):
                continue
            folder_name = item.get("original_folder_name")
            relative_path = item.get("original_relative_path")
            trash_path = item.get("trash_path")
            deleted_at = item.get("deleted_at")
            if (
                isinstance(folder_name, str)
                and isinstance(relative_path, str)
                and isinstance(trash_path, str)
                and isinstance(deleted_at, str)
            ):
                entries.append(
                    FileTrashEntry(
                        original_folder_name=folder_name,
                        original_relative_path=relative_path,
                        trash_path=trash_path,
                        deleted_at=deleted_at,
                    )
                )
        return entries

    def file_trash_summary(self) -> str:
        entries = self.list_file_trash()
        if not entries:
            return "File trash is empty."

        lines = ["File trash:"]
        for index, entry in enumerate(entries, start=1):
            lines.append(f"{index}. {entry.display_text()} (deleted {entry.deleted_at})")
        return "\n".join(lines)

    def restore_file_from_trash(self, entry_number: int) -> FileTrashEntry:
        entries = self.list_file_trash()
        if entry_number < 1 or entry_number > len(entries):
            raise FileToolError(f"File trash number must be between 1 and {len(entries)}.")

        entry = entries[entry_number - 1]
        _, root = self._resolve_folder(entry.original_folder_name)
        target_path = self._resolve_restore_target(root, entry.original_relative_path)
        trash_path = Path(entry.trash_path)
        if not trash_path.exists() or not trash_path.is_file():
            raise FileToolError(f"Trashed file is missing: {entry.trash_path}")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(trash_path), target_path)
        except OSError as exc:
            raise FileToolError(f"Could not restore file: {entry.display_text()}") from exc

        entries.pop(entry_number - 1)
        self._write_file_trash(entries)
        return entry

    def trash_entries_older_than(self, days: int) -> list[tuple[int, FileTrashEntry]]:
        """Return (1-based entry_number, entry) pairs for trash items whose
        deleted_at timestamp is older than the given number of days.
        """
        from datetime import datetime, timezone

        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        results: list[tuple[int, FileTrashEntry]] = []
        for index, entry in enumerate(self.list_file_trash(), start=1):
            try:
                deleted_at = datetime.strptime(entry.deleted_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            if deleted_at.timestamp() < cutoff:
                results.append((index, entry))
        return results

    def purge_trash_entries(self, entry_numbers: list[int]) -> list[FileTrashEntry]:
        """Permanently delete specific trash entries by 1-based entry number.

        This is the one genuinely irreversible deletion path in the app. It
        is reachable only as an explicit second step on items that are
        already sitting in the reversible trash (i.e. the person already
        confirmed removing them once) -- never a direct delete of a live
        file. Callers are expected to have already shown the person exactly
        which entries this will affect and gotten a fresh confirmation.
        """
        entries = self.list_file_trash()
        if not entry_numbers:
            raise FileToolError("No trash entries were specified to purge.")

        unique_numbers = sorted(set(entry_numbers), reverse=True)
        for number in unique_numbers:
            if number < 1 or number > len(entries):
                raise FileToolError(f"File trash number must be between 1 and {len(entries)}.")

        purged: list[FileTrashEntry] = []
        for number in unique_numbers:
            entry = entries[number - 1]
            trash_path = Path(entry.trash_path)
            try:
                if trash_path.exists():
                    trash_path.unlink()
            except OSError as exc:
                raise FileToolError(f"Could not permanently delete: {entry.display_text()}") from exc
            purged.append(entry)
            del entries[number - 1]

        self._write_file_trash(entries)
        return purged

    def bulk_replace_required_confirmation_phrase(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """The exact phrase the operator must type back to commit this plan.

        Deliberately derived from the live plan (folder + file count) so it
        cannot be copy-pasted from a stale/different plan without the count
        matching, and so the operator has to have actually looked at what
        they're approving.
        """
        canonical_name, _root = self._resolve_folder(folder_name)
        clean_old = " ".join(old_text.strip().split())
        clean_new = " ".join(new_text.strip().split())
        items = self.bulk_replace_plan(folder_name, clean_old, clean_new, limit=limit)
        return f"apply {len(items)} files in {canonical_name}"

    def validate_bulk_replace_commit(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        confirmation_phrase: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> tuple[Path, dict[str, object]]:
        """Run every commit precondition without writing anything.

        Returns (backup_dir, backup_manifest) if everything checks out, or
        raises FileToolError describing exactly what's wrong. This is safe
        to call eagerly (e.g. before even offering a confirmation prompt)
        since it has no side effects, and is also re-run at actual commit
        time as defense in depth against anything changing in between.
        """
        canonical_name, root = self._resolve_folder(folder_name)
        clean_old = " ".join(old_text.strip().split())
        clean_new = " ".join(new_text.strip().split())
        if not clean_old:
            raise FileToolError("Bulk replace commit needs text to find.")
        if not clean_new:
            raise FileToolError("Bulk replace commit needs replacement text.")

        backup_dir, backup_manifest = self._latest_manifest(self.bulk_backup_dir)
        if backup_manifest.get("kind") != "bulk_replace_backup":
            raise FileToolError("No bulk replace backup found. Run a backup first.")
        if backup_manifest.get("folder") != canonical_name:
            raise FileToolError(
                f"Latest backup is for folder '{backup_manifest.get('folder')}', not '{canonical_name}'. "
                "Take a fresh backup for this folder first."
            )
        if backup_manifest.get("find") != clean_old or backup_manifest.get("replace_with") != clean_new:
            raise FileToolError(
                "Latest backup does not match this find/replace text. Take a fresh backup first."
            )
        if backup_manifest.get("apply_enabled"):
            raise FileToolError("This backup has already been applied. Take a fresh backup to apply again.")

        status, notes = _manifest_hash_status(backup_manifest, "Backup")
        if status != "ok":
            raise FileToolError(f"Backup manifest failed integrity check: {'; '.join(notes)}")

        backup_files = backup_manifest.get("files")
        if not isinstance(backup_files, list) or not backup_files:
            raise FileToolError("Backup manifest has no files recorded.")

        # Re-verify the live files on disk still match exactly what was
        # backed up (no drift since the backup was taken) before writing
        # anything.
        for record in backup_files:
            if not isinstance(record, dict):
                raise FileToolError("Backup manifest is malformed.")
            relative_path = record.get("relative_path")
            expected_hash = record.get("source_sha256")
            if not isinstance(relative_path, str) or not relative_path:
                raise FileToolError("Backup manifest has an invalid file entry.")
            live_path = self._resolve_file(root, relative_path)
            if not live_path.exists():
                raise FileToolError(
                    f"File has changed since backup (now missing): {relative_path}. "
                    "Take a fresh backup before committing."
                )
            live_hash = _file_metadata(live_path)["sha256"]
            if live_hash != expected_hash:
                raise FileToolError(
                    f"File has changed since backup: {relative_path}. "
                    "Take a fresh backup before committing."
                )

        required_phrase = self.bulk_replace_required_confirmation_phrase(
            folder_name, clean_old, clean_new, limit=limit
        )
        if confirmation_phrase.strip() != required_phrase:
            raise FileToolError(
                f"Confirmation phrase did not match. Expected exactly: '{required_phrase}'"
            )
        if len(backup_files) != int(required_phrase.split()[1]):
            raise FileToolError(
                "The plan has changed since the backup was taken (different file count). "
                "Take a fresh backup before committing."
            )

        return backup_dir, backup_manifest

    def commit_bulk_replace_plan(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        confirmation_phrase: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Actually apply a previously backed-up bulk replace plan.

        Preconditions, all required (see validate_bulk_replace_commit):
        1. A backup for this exact folder/find/replace already exists
           (via backup_bulk_replace_plan), its manifest hash is intact, and
           it has not already been applied.
        2. The live files on disk right now match exactly what the backup
           recorded (same files, same content hashes) -- if anything has
           changed since the backup was taken, this refuses rather than
           applying against a plan that's gone stale.
        3. confirmation_phrase exactly matches the phrase computed fresh
           from the current plan (see bulk_replace_required_confirmation_phrase).

        On success, files are modified in place, but originals remain
        recoverable via rollback_bulk_replace_commit() using this same
        backup, since the backup copies are never deleted.
        """
        canonical_name, root = self._resolve_folder(folder_name)
        clean_old = " ".join(old_text.strip().split())
        clean_new = " ".join(new_text.strip().split())
        backup_dir, backup_manifest = self.validate_bulk_replace_commit(
            folder_name, old_text, new_text, confirmation_phrase, limit=limit
        )
        backup_files = backup_manifest["files"]

        changed_files: list[str] = []
        for record in backup_files:
            relative_path = record["relative_path"]
            live_path = self._resolve_file(root, relative_path)
            try:
                original_text = live_path.read_text(encoding="utf-8")
                updated_text = original_text.replace(clean_old, clean_new)
                live_path.write_text(updated_text, encoding="utf-8")
            except OSError as exc:
                raise FileToolError(f"Failed applying change to: {relative_path}") from exc
            changed_files.append(relative_path)

        backup_manifest["apply_enabled"] = True
        backup_manifest["applied_at"] = _utc_now_iso()
        self._write_bulk_backup_manifest(backup_dir, _annotate_manifest_hash(backup_manifest))

        return (
            f"Done: Applied bulk replace to {len(changed_files)} file(s) in '{canonical_name}'. "
            f"Backup preserved at {backup_dir} for rollback."
        )

    def rollback_bulk_replace_commit(self) -> str:
        """Restore files from the most recent applied bulk replace backup.

        Only works on a backup that was actually committed
        (apply_enabled=True) and has not already been rolled back, and
        verifies each backed-up file's hash before restoring it.
        """
        backup_dir, backup_manifest = self._latest_manifest(self.bulk_backup_dir)
        if backup_manifest.get("kind") != "bulk_replace_backup":
            raise FileToolError("No bulk replace backup found to roll back.")
        if not backup_manifest.get("apply_enabled"):
            raise FileToolError("This backup was never applied, so there is nothing to roll back.")
        if backup_manifest.get("rolled_back_at"):
            raise FileToolError("This backup has already been rolled back.")

        status, notes = _manifest_hash_status(backup_manifest, "Backup")
        if status != "ok":
            raise FileToolError(f"Backup manifest failed integrity check: {'; '.join(notes)}")

        canonical_name = backup_manifest.get("folder")
        if not isinstance(canonical_name, str):
            raise FileToolError("Backup manifest is missing its folder name.")
        _canonical_name, root = self._resolve_folder(canonical_name)

        entries = _rollback_entries_from_backup_manifest(backup_manifest)
        restored: list[str] = []
        for entry in entries:
            backup_relative_path = entry["backup_relative_path"]
            restore_relative_path = entry["restore_relative_path"]
            backup_file_path = backup_dir / "files" / backup_relative_path
            expected_hash = entry.get("backup_sha256")
            if not backup_file_path.exists():
                raise FileToolError(f"Backup copy is missing, cannot restore: {backup_relative_path}")
            actual_hash = _file_metadata(backup_file_path)["sha256"]
            if expected_hash and actual_hash != expected_hash:
                raise FileToolError(
                    f"Backup copy integrity check failed for: {backup_relative_path}"
                )
            restore_target = self._resolve_file(root, restore_relative_path)
            try:
                shutil.copy2(backup_file_path, restore_target)
            except OSError as exc:
                raise FileToolError(f"Could not restore file: {restore_relative_path}") from exc
            restored.append(restore_relative_path)

        backup_manifest["rolled_back_at"] = _utc_now_iso()
        self._write_bulk_backup_manifest(backup_dir, _annotate_manifest_hash(backup_manifest))

        return f"Done: Rolled back {len(restored)} file(s) in '{canonical_name}' to their pre-apply state."

    def search_files_summary(
        self,
        folder_name: str,
        query: str,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> str:
        clean_query = " ".join(query.strip().split())
        if not clean_query:
            raise FileToolError("File search needs text to find.")

        canonical_name, root = self._resolve_folder(folder_name)
        results = self.search_files(folder_name, clean_query, limit=limit)
        if not results:
            return f"No readable file matches for '{clean_query}' in {canonical_name}."

        lines = [f"File search results for '{clean_query}' in {canonical_name}:"]
        for index, result in enumerate(results, start=1):
            lines.append(
                f"{index}. {result.relative_path}:{result.line_number}: {result.line_text}"
            )
        if len(results) == limit:
            lines.append(f"Showing first {limit} match(es).")
        return "\n".join(lines)

    def search_files(
        self,
        folder_name: str,
        query: str,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> list[FileSearchResult]:
        canonical_name, root = self._resolve_folder(folder_name)
        clean_query = query.casefold()
        results: list[FileSearchResult] = []

        for file_path in self._list_files(root, limit=10_000):
            try:
                self._validate_text_file(file_path, max_bytes=MAX_SEARCH_BYTES)
                lines = file_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            except FileToolError:
                continue
            except OSError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if clean_query in line.casefold():
                    results.append(
                        FileSearchResult(
                            folder_name=canonical_name,
                            relative_path=_relative_text(file_path, root),
                            line_number=line_number,
                            line_text=_trim_line(line),
                        )
                    )
                    if len(results) >= limit:
                        return results
        return results

    def search_file_names_summary(
        self,
        folder_name: str,
        query: str,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> str:
        clean_query = " ".join(query.strip().split())
        if not clean_query:
            raise FileToolError("Filename search needs text to find.")

        canonical_name, _ = self._resolve_folder(folder_name)
        results = self.search_file_names(folder_name, clean_query, limit=limit)
        if not results:
            return f"No readable filenames matching '{clean_query}' in {canonical_name}."

        lines = [f"Filename search results for '{clean_query}' in {canonical_name}:"]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. {result.relative_path}")
        if len(results) == limit:
            lines.append(f"Showing first {limit} filename match(es).")
        return "\n".join(lines)

    def search_file_names(
        self,
        folder_name: str,
        query: str,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> list[FileNameSearchResult]:
        canonical_name, root = self._resolve_folder(folder_name)
        clean_query = query.casefold()
        results: list[FileNameSearchResult] = []

        for file_path in self._list_files(root, limit=10_000):
            relative_path = _relative_text(file_path, root)
            if clean_query in relative_path.casefold():
                results.append(
                    FileNameSearchResult(
                        folder_name=canonical_name,
                        relative_path=relative_path,
                    )
                )
                if len(results) >= limit:
                    return results
        return results

    def bulk_replace_plan_summary(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Return a dry-run content replacement plan without writing files."""
        clean_old = " ".join(old_text.strip().split())
        clean_new = " ".join(new_text.strip().split())
        if not clean_old:
            raise FileToolError("Bulk replace preview needs text to find.")
        if not clean_new:
            raise FileToolError("Bulk replace preview needs replacement text.")
        if clean_old == clean_new:
            raise FileToolError("Bulk replace preview needs different find and replacement text.")

        canonical_name, _ = self._resolve_folder(folder_name)
        items = self.bulk_replace_plan(folder_name, clean_old, clean_new, limit=limit)
        if not items:
            return f"No bulk replace matches for '{clean_old}' in {canonical_name}. No files were changed."

        total_matches = sum(item.match_count for item in items)
        lines = [
            "Bulk replace dry run",
            "No files were changed.",
            f"Folder: {canonical_name}",
            f"Find: {clean_old}",
            f"Replace with: {clean_new}",
            f"Planned files: {len(items)}",
            f"Planned replacements: {total_matches}",
            "Plan:",
        ]
        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. {item.relative_path}: {item.match_count} replacement(s)")
        if len(items) == limit:
            lines.append(f"Showing first {limit} planned file(s).")
        return "\n".join(lines)

    def bulk_replace_apply_plan_summary(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Return the safety design for applying a replace plan without writing files."""
        dry_run = self.bulk_replace_plan_summary(folder_name, old_text, new_text, limit=limit)
        return "\n".join(
            [
                "Bulk replace apply safety plan",
                "No files were changed.",
                "Apply is not enabled in this build.",
                _bulk_apply_requirements_text(),
                "Current dry run:",
                dry_run,
            ]
        )

    def backup_bulk_replace_plan(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Create local backup copies for a replace plan without editing files."""
        clean_old = " ".join(old_text.strip().split())
        clean_new = " ".join(new_text.strip().split())
        if not clean_old:
            raise FileToolError("Bulk replace backup needs text to find.")
        if not clean_new:
            raise FileToolError("Bulk replace backup needs replacement text.")
        if clean_old == clean_new:
            raise FileToolError("Bulk replace backup needs different find and replacement text.")

        canonical_name, root = self._resolve_folder(folder_name)
        items = self.bulk_replace_plan(folder_name, clean_old, clean_new, limit=limit)
        if not items:
            return f"No bulk replace matches for '{clean_old}' in {canonical_name}. No backup was created."

        backup_dir = self._create_bulk_backup_dir("replace")
        copied_files: list[str] = []
        manifest_files: list[dict[str, object]] = []
        for item in items:
            source = self._resolve_file(root, item.relative_path)
            self._validate_text_file(source, max_bytes=MAX_SEARCH_BYTES)
            source_metadata = _prefixed_file_metadata(source, "source")
            destination = backup_dir / "files" / item.relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, destination)
            except OSError as exc:
                raise FileToolError(f"Could not back up file: {item.relative_path}") from exc
            backup_metadata = _prefixed_file_metadata(destination, "backup")
            copied_files.append(item.relative_path)
            manifest_files.append(
                {
                    "relative_path": item.relative_path,
                    "match_count": item.match_count,
                    **source_metadata,
                    **backup_metadata,
                }
            )

        manifest = {
            "kind": "bulk_replace_backup",
            "created_at": _utc_now_iso(),
            "folder": canonical_name,
            "find": clean_old,
            "replace_with": clean_new,
            "apply_enabled": False,
            "hash_algorithm": "sha256",
            "files": manifest_files,
        }
        self._write_bulk_backup_manifest(backup_dir, _annotate_manifest_hash(manifest))
        return _bulk_backup_summary("Bulk replace backup created", backup_dir, copied_files)

    def approve_bulk_replace_plan(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        selection_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Save per-file approvals for a replace plan without editing files."""
        clean_old = " ".join(old_text.strip().split())
        clean_new = " ".join(new_text.strip().split())
        if not clean_old:
            raise FileToolError("Bulk replace approval needs text to find.")
        if not clean_new:
            raise FileToolError("Bulk replace approval needs replacement text.")
        if clean_old == clean_new:
            raise FileToolError("Bulk replace approval needs different find and replacement text.")

        canonical_name, root = self._resolve_folder(folder_name)
        items = self.bulk_replace_plan(folder_name, clean_old, clean_new, limit=limit)
        if not items:
            return f"No bulk replace matches for '{clean_old}' in {canonical_name}. No approval was saved."

        selected_indexes = _parse_bulk_selection(selection_text, len(items))
        approved_items = [items[index - 1] for index in selected_indexes]
        approval_dir = self._create_bulk_approval_dir("replace")
        manifest = {
            "kind": "bulk_replace_approval",
            "created_at": _utc_now_iso(),
            "folder": canonical_name,
            "find": clean_old,
            "replace_with": clean_new,
            "apply_enabled": False,
            "approved_indexes": selected_indexes,
            "approved_files": [
                {
                    "relative_path": item.relative_path,
                    "match_count": item.match_count,
                    **_prefixed_file_metadata(self._resolve_file(root, item.relative_path), "source"),
                }
                for item in approved_items
            ],
            "hash_algorithm": "sha256",
        }
        self._write_bulk_approval_manifest(approval_dir, _annotate_manifest_hash(manifest))
        return _bulk_approval_summary("Bulk replace approval saved", approval_dir, selected_indexes, [
            item.relative_path for item in approved_items
        ])

    def bulk_replace_plan(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> list[BulkReplacePlanItem]:
        _, root = self._resolve_folder(folder_name)
        clean_old = old_text.casefold()
        items: list[BulkReplacePlanItem] = []

        for file_path in self._list_files(root, limit=10_000):
            try:
                self._validate_text_file(file_path, max_bytes=MAX_SEARCH_BYTES)
                text = file_path.read_text(encoding="utf-8-sig", errors="replace")
            except FileToolError:
                continue
            except OSError:
                continue

            match_count = text.casefold().count(clean_old)
            if match_count:
                items.append(
                    BulkReplacePlanItem(
                        relative_path=_relative_text(file_path, root),
                        match_count=match_count,
                    )
                )
                if len(items) >= limit:
                    return items
        return items

    def bulk_rename_plan_summary(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Return a dry-run filename replacement plan without renaming files."""
        clean_old = old_text.strip()
        clean_new = new_text.strip()
        if not clean_old:
            raise FileToolError("Bulk rename preview needs filename text to find.")
        if not clean_new:
            raise FileToolError("Bulk rename preview needs replacement filename text.")
        if clean_old == clean_new:
            raise FileToolError("Bulk rename preview needs different find and replacement text.")
        if any(char in clean_new for char in ("/", "\\", ":", "*", "?", '"', "<", ">", "|")):
            raise FileToolError("Bulk rename replacement cannot contain path or wildcard characters.")

        canonical_name, _ = self._resolve_folder(folder_name)
        items = self.bulk_rename_plan(folder_name, clean_old, clean_new, limit=limit)
        if not items:
            return f"No bulk rename matches for '{clean_old}' in {canonical_name}. No files were changed."

        lines = [
            "Bulk rename dry run",
            "No files were changed.",
            f"Folder: {canonical_name}",
            f"Filename find: {clean_old}",
            f"Replace with: {clean_new}",
            f"Planned renames: {len(items)}",
            "Plan:",
        ]
        for index, item in enumerate(items, start=1):
            suffix = " (conflict: target already exists)" if item.conflict else ""
            lines.append(f"{index}. {item.old_relative_path} -> {item.new_relative_path}{suffix}")
        if len(items) == limit:
            lines.append(f"Showing first {limit} planned rename(s).")
        return "\n".join(lines)

    def bulk_rename_apply_plan_summary(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Return the safety design for applying a rename plan without renaming files."""
        dry_run = self.bulk_rename_plan_summary(folder_name, old_text, new_text, limit=limit)
        return "\n".join(
            [
                "Bulk rename apply safety plan",
                "No files were changed.",
                "Apply is not enabled in this build.",
                "Any rename conflict blocks the whole apply step.",
                _bulk_apply_requirements_text(),
                "Current dry run:",
                dry_run,
            ]
        )

    def backup_bulk_rename_plan(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Create local backup copies for a rename plan without renaming files."""
        clean_old = old_text.strip()
        clean_new = new_text.strip()
        if not clean_old:
            raise FileToolError("Bulk rename backup needs filename text to find.")
        if not clean_new:
            raise FileToolError("Bulk rename backup needs replacement filename text.")
        if clean_old == clean_new:
            raise FileToolError("Bulk rename backup needs different find and replacement text.")
        if any(char in clean_new for char in ("/", "\\", ":", "*", "?", '"', "<", ">", "|")):
            raise FileToolError("Bulk rename replacement cannot contain path or wildcard characters.")

        canonical_name, root = self._resolve_folder(folder_name)
        items = self.bulk_rename_plan(folder_name, clean_old, clean_new, limit=limit)
        if not items:
            return f"No bulk rename matches for '{clean_old}' in {canonical_name}. No backup was created."
        if any(item.conflict for item in items):
            raise FileToolError("Bulk rename backup blocked because at least one planned rename has a conflict.")

        backup_dir = self._create_bulk_backup_dir("rename")
        copied_files: list[str] = []
        manifest_files: list[dict[str, object]] = []
        for item in items:
            source = self._resolve_file(root, item.old_relative_path)
            self._validate_text_file(source, max_bytes=MAX_SEARCH_BYTES)
            source_metadata = _prefixed_file_metadata(source, "source")
            destination = backup_dir / "files" / item.old_relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, destination)
            except OSError as exc:
                raise FileToolError(f"Could not back up file: {item.old_relative_path}") from exc
            backup_metadata = _prefixed_file_metadata(destination, "backup")
            copied_files.append(item.old_relative_path)
            manifest_files.append(
                {
                    "old_relative_path": item.old_relative_path,
                    "new_relative_path": item.new_relative_path,
                    **source_metadata,
                    **backup_metadata,
                }
            )

        manifest = {
            "kind": "bulk_rename_backup",
            "created_at": _utc_now_iso(),
            "folder": canonical_name,
            "filename_find": clean_old,
            "replace_with": clean_new,
            "apply_enabled": False,
            "hash_algorithm": "sha256",
            "files": manifest_files,
        }
        self._write_bulk_backup_manifest(backup_dir, _annotate_manifest_hash(manifest))
        return _bulk_backup_summary("Bulk rename backup created", backup_dir, copied_files)

    def approve_bulk_rename_plan(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        selection_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> str:
        """Save per-file approvals for a rename plan without renaming files."""
        clean_old = old_text.strip()
        clean_new = new_text.strip()
        if not clean_old:
            raise FileToolError("Bulk rename approval needs filename text to find.")
        if not clean_new:
            raise FileToolError("Bulk rename approval needs replacement filename text.")
        if clean_old == clean_new:
            raise FileToolError("Bulk rename approval needs different find and replacement text.")
        if any(char in clean_new for char in ("/", "\\", ":", "*", "?", '"', "<", ">", "|")):
            raise FileToolError("Bulk rename replacement cannot contain path or wildcard characters.")

        canonical_name, root = self._resolve_folder(folder_name)
        items = self.bulk_rename_plan(folder_name, clean_old, clean_new, limit=limit)
        if not items:
            return f"No bulk rename matches for '{clean_old}' in {canonical_name}. No approval was saved."
        if any(item.conflict for item in items):
            raise FileToolError("Bulk rename approval blocked because at least one planned rename has a conflict.")

        selected_indexes = _parse_bulk_selection(selection_text, len(items))
        approved_items = [items[index - 1] for index in selected_indexes]
        approval_dir = self._create_bulk_approval_dir("rename")
        manifest = {
            "kind": "bulk_rename_approval",
            "created_at": _utc_now_iso(),
            "folder": canonical_name,
            "filename_find": clean_old,
            "replace_with": clean_new,
            "apply_enabled": False,
            "approved_indexes": selected_indexes,
            "approved_files": [
                {
                    "old_relative_path": item.old_relative_path,
                    "new_relative_path": item.new_relative_path,
                    **_prefixed_file_metadata(self._resolve_file(root, item.old_relative_path), "source"),
                }
                for item in approved_items
            ],
            "hash_algorithm": "sha256",
        }
        self._write_bulk_approval_manifest(approval_dir, _annotate_manifest_hash(manifest))
        return _bulk_approval_summary("Bulk rename approval saved", approval_dir, selected_indexes, [
            f"{item.old_relative_path} -> {item.new_relative_path}" for item in approved_items
        ])

    def bulk_rename_plan(
        self,
        folder_name: str,
        old_text: str,
        new_text: str,
        limit: int = MAX_BULK_PLAN_ITEMS,
    ) -> list[BulkRenamePlanItem]:
        _, root = self._resolve_folder(folder_name)
        items: list[BulkRenamePlanItem] = []

        for file_path in self._list_files(root, limit=10_000):
            if old_text.casefold() not in file_path.name.casefold():
                continue
            new_name = _case_insensitive_replace(file_path.name, old_text, new_text)
            new_path = file_path.with_name(new_name)
            items.append(
                BulkRenamePlanItem(
                    old_relative_path=_relative_text(file_path, root),
                    new_relative_path=_relative_text(new_path, root),
                    conflict=new_path.exists() and new_path != file_path,
                )
            )
            if len(items) >= limit:
                return items
        return items

    def parse_read_request(self, text: str) -> tuple[str, str]:
        """Parse '<folder name> <relative path>' using configured folder names."""
        normalized_text = " ".join(text.strip().split())
        if not normalized_text:
            raise FileToolError("Read file expects: read file in <folder> <relative path>")

        for folder_name in sorted(self.folder_names(), key=len, reverse=True):
            prefix = f"{folder_name} "
            if normalized_text.lower().startswith(prefix):
                relative_path = normalized_text[len(prefix) :].strip()
                if not relative_path:
                    raise FileToolError("Read file needs a relative file path.")
                return folder_name, relative_path
        raise FileToolError("Read file folder must be one of: " + ", ".join(self.folder_names()))

    def parse_file_request(self, text: str, verb: str) -> tuple[str, str]:
        """Parse '<folder name> <relative path>' for a file operation."""
        normalized_text = " ".join(text.strip().split())
        if not normalized_text:
            raise FileToolError(f"{verb} expects: {verb} file in <folder> <relative path>")

        for folder_name in sorted(self.folder_names(), key=len, reverse=True):
            prefix = f"{folder_name} "
            if normalized_text.lower().startswith(prefix):
                relative_path = normalized_text[len(prefix) :].strip()
                if not relative_path:
                    raise FileToolError(f"{verb} needs a relative file path.")
                return folder_name, relative_path
        raise FileToolError(f"{verb} folder must be one of: " + ", ".join(self.folder_names()))

    def resolve_allowlisted_file(self, folder_name: str, relative_path: str) -> tuple[str, Path]:
        """Resolve an allowlisted file target and return normalized folder name and path."""
        canonical_name, root = self._resolve_folder(folder_name)
        file_path = self._resolve_file(root, relative_path)
        return canonical_name, file_path

    @staticmethod
    def bulk_apply_safety_text() -> str:
        return "\n".join(
            [
                "Bulk apply safety",
                "Apply is not enabled in this build.",
                "Current status: preview and safety planning only.",
                _bulk_apply_requirements_text(),
                "Available planning commands:",
                "- bulk replace apply plan in <folder> find <text> with <text>",
                "- bulk rename apply plan in <folder> replace <name text> with <name text>",
            ]
        )

    @staticmethod
    def bulk_write_command_design_text() -> str:
        return "\n".join(
            [
                "Confirmed bulk write command design",
                "Status: design only. No files are written in this build.",
                "Future command shape:",
                "- prepare: bulk write preflight",
                "- execute: confirm bulk write <preflight id>",
                "Required manifests:",
                "- backup manifest with original file copies and source metadata",
                "- approval manifest with approved file list",
                "- audit-linked apply review with status review_ready",
                "- rollback plan with one restore entry per backed-up file",
                "- write preflight with status preflight_ready",
                "- manifest hashes for backup, approval, review, rollback, and preflight records",
                "Required rollback checks before any write:",
                "- rollback manifest kind must be bulk_rollback_plan",
                "- restore_enabled must still be false before write",
                "- rollback entry count must match backed-up file count",
                "- every rollback backup file must exist under the backup files folder",
                "- every restore path must stay inside the same allowlisted folder",
                "- each target file must still match the preflight source hash and size",
                "- rename writes must prove destination paths do not already exist",
                "Required confirmation:",
                "- Show the approved file count and rollback entry count.",
                "- Require a fresh typed phrase: confirm bulk write.",
                "- Record requested command, manifests, checks, and result in action audit.",
                "Failure behavior:",
                "- If any rollback check fails, do not write any file.",
                "- If any target hash changed since preflight, do not write any file.",
                "- If a write fails after starting, stop immediately and require the separate restore command.",
            ]
        )

    @staticmethod
    def bulk_restore_command_design_text() -> str:
        return "\n".join(
            [
                "Confirmed bulk restore command design",
                "Status: design only. No files are restored in this build.",
                "Future command shape:",
                "- prepare: bulk rollback plan",
                "- execute: confirm bulk restore <rollback id>",
                "Required manifests:",
                "- rollback plan created from a local bulk backup",
                "- original backup manifest embedded or referenced by the rollback plan",
                "- action audit entry from the failed or completed write attempt",
                "- manifest hashes for backup, rollback, and restore review records",
                "Required restore checks before any restore:",
                "- rollback manifest kind must be bulk_rollback_plan",
                "- restore_enabled must become true only inside the confirmed restore implementation",
                "- every backup file must exist and match the recorded backup hash and size",
                "- every restore path must stay inside the original allowlisted folder",
                "- restore must refuse to overwrite unrelated files unless the write audit proves the assistant changed them",
                "- restore must process files one by one and record each result",
                "- rename restore must separately review cleanup of renamed targets",
                "Required confirmation:",
                "- Show the restore entry count and affected allowlisted folder.",
                "- Require a fresh typed phrase: confirm bulk restore.",
                "- Record requested command, manifests, checks, and result in action audit.",
                "Failure behavior:",
                "- If any rollback check fails, do not restore any file.",
                "- If a restore entry is ambiguous, skip it and report manual review required.",
                "- Never permanently delete files as part of restore.",
            ]
        )

    def create_bulk_apply_review(self) -> BulkApplyReviewResult:
        """Create an audit-ready review from the latest backup and approval manifests."""
        backup_dir, backup_manifest = self._latest_manifest(self.bulk_backup_dir)
        approval_dir, approval_manifest = self._latest_manifest(self.bulk_approval_dir)
        review_status, review_notes = _bulk_review_status(backup_manifest, approval_manifest)
        review_dir = self._create_bulk_review_dir()
        manifest = {
            "kind": "bulk_apply_review",
            "created_at": _utc_now_iso(),
            "apply_enabled": False,
            "status": review_status,
            "backup_manifest": str(backup_dir / "manifest.json"),
            "approval_manifest": str(approval_dir / "manifest.json"),
            "notes": review_notes,
            "backup": backup_manifest,
            "approval": approval_manifest,
        }
        self._write_bulk_review_manifest(review_dir, _annotate_manifest_hash(manifest))

        approved_count = _manifest_file_count(approval_manifest, key="approved_files")
        backup_count = _manifest_file_count(backup_manifest, key="files")
        lines = [
            "Bulk apply review created",
            "No original files were changed.",
            "Apply is still not enabled in this build.",
            f"Review status: {review_status}",
            f"Review folder: {review_dir}",
            f"Backup manifest: {backup_dir / 'manifest.json'}",
            f"Approval manifest: {approval_dir / 'manifest.json'}",
            f"Backed up files: {backup_count}",
            f"Approved files: {approved_count}",
            "Review notes:",
        ]
        lines.extend(f"- {note}" for note in review_notes)
        lines.append("Manifest: manifest.json")
        audit_description = f"Bulk apply review: {review_status} ({approved_count} approved file(s))"
        return BulkApplyReviewResult("\n".join(lines), review_dir, audit_description)

    def create_bulk_rollback_plan(self) -> BulkRollbackPlanResult:
        """Create a rollback plan from the latest backup manifest without restoring files."""
        backup_dir, backup_manifest = self._latest_manifest(self.bulk_backup_dir)
        rollback_dir = self._create_bulk_rollback_dir()
        entries = _rollback_entries_from_backup_manifest(backup_manifest)
        manifest = {
            "kind": "bulk_rollback_plan",
            "created_at": _utc_now_iso(),
            "restore_enabled": False,
            "backup_manifest": str(backup_dir / "manifest.json"),
            "backup": backup_manifest,
            "rollback_entries": entries,
        }
        self._write_bulk_rollback_manifest(rollback_dir, _annotate_manifest_hash(manifest))

        lines = [
            "Bulk rollback plan created",
            "No original files were changed.",
            "Restore is not enabled in this build.",
            f"Rollback folder: {rollback_dir}",
            f"Backup manifest: {backup_dir / 'manifest.json'}",
            f"Planned restore entries: {len(entries)}",
            "Plan:",
        ]
        for index, entry in enumerate(entries, start=1):
            lines.append(f"{index}. {entry['backup_relative_path']} -> {entry['restore_relative_path']}")
        if backup_manifest.get("kind") == "bulk_rename_backup":
            lines.append("Note: rename rollback would also need a separate reviewed cleanup of renamed targets.")
        lines.append("Manifest: manifest.json")
        audit_description = f"Bulk rollback plan ({len(entries)} restore entr(y/ies))"
        return BulkRollbackPlanResult("\n".join(lines), rollback_dir, audit_description)

    def create_bulk_write_preflight(self) -> BulkWritePreflightResult:
        """Create a final no-write preflight for a future confirmed bulk write step."""
        backup_dir, backup_manifest = self._latest_manifest(self.bulk_backup_dir)
        approval_dir, approval_manifest = self._latest_manifest(self.bulk_approval_dir)
        review_dir, review_manifest = self._latest_manifest(self.bulk_review_dir)
        rollback_dir, rollback_manifest = self._latest_manifest(self.bulk_rollback_dir)
        status, notes = _bulk_write_preflight_status(
            backup_dir,
            backup_manifest,
            approval_manifest,
            review_manifest,
            rollback_manifest,
        )
        preflight_dir = self._create_bulk_preflight_dir()
        approved_count = _manifest_file_count(approval_manifest, key="approved_files")
        rollback_count = _manifest_file_count(rollback_manifest, key="rollback_entries")
        signed_review_metadata = _build_bulk_preflight_review_metadata(
            status=status,
            approved_count=approved_count,
            rollback_count=rollback_count,
            backup_manifest_path=backup_dir / "manifest.json",
            approval_manifest_path=approval_dir / "manifest.json",
            review_manifest_path=review_dir / "manifest.json",
            rollback_manifest_path=rollback_dir / "manifest.json",
            notes=notes,
            backup_manifest=backup_manifest,
            approval_manifest=approval_manifest,
            review_manifest=review_manifest,
            rollback_manifest=rollback_manifest,
        )
        manifest = {
            "kind": "bulk_write_preflight",
            "created_at": _utc_now_iso(),
            "write_enabled": False,
            "restore_enabled": False,
            "status": status,
            "backup_manifest": str(backup_dir / "manifest.json"),
            "approval_manifest": str(approval_dir / "manifest.json"),
            "review_manifest": str(review_dir / "manifest.json"),
            "rollback_manifest": str(rollback_dir / "manifest.json"),
            "notes": notes,
            "signed_review_metadata": signed_review_metadata,
            "backup": backup_manifest,
            "approval": approval_manifest,
            "review": review_manifest,
            "rollback": rollback_manifest,
        }
        self._write_bulk_preflight_manifest(preflight_dir, _annotate_manifest_hash(manifest))

        lines = [
            "Bulk write preflight created",
            "No original files were changed.",
            "Write is not enabled in this build.",
            "Restore is not enabled in this build.",
            f"Preflight status: {status}",
            f"Preflight folder: {preflight_dir}",
            f"Backup manifest: {backup_dir / 'manifest.json'}",
            f"Approval manifest: {approval_dir / 'manifest.json'}",
            f"Review manifest: {review_dir / 'manifest.json'}",
            f"Rollback manifest: {rollback_dir / 'manifest.json'}",
            f"Approved files: {approved_count}",
            f"Rollback entries: {rollback_count}",
            "Preflight notes:",
        ]
        lines.extend(f"- {note}" for note in notes)
        lines.extend(
            [
                "Signed review metadata:",
                f"- Schema: {signed_review_metadata['schema']}",
                f"- Signature: {signed_review_metadata['review_signature']}",
                "- Purpose: tamper-evident local preflight review; it does not enable writes or restores.",
            ]
        )
        lines.append("Manifest: manifest.json")
        audit_description = f"Bulk write preflight: {status} ({approved_count} approved file(s))"
        return BulkWritePreflightResult("\n".join(lines), preflight_dir, audit_description)

    def create_bulk_write_operator_checklist(self) -> BulkOperatorChecklistResult:
        """Create a local operator checklist for future bulk write review without writing files."""
        preflight_dir, preflight_manifest = self._latest_manifest(self.bulk_preflight_dir)
        checklist_dir = self._create_bulk_checklist_dir("write")
        manifest = _build_bulk_operator_checklist_manifest(
            kind="bulk_write_operator_checklist",
            operation="write",
            source_manifest_path=preflight_dir / "manifest.json",
            source_manifest=preflight_manifest,
            checklist_items=_bulk_write_operator_checklist_items(),
        )
        self._write_bulk_checklist_files(checklist_dir, manifest)
        status = str(preflight_manifest.get("status", "unknown"))
        approval_manifest = preflight_manifest.get("approval")
        approved_count = _manifest_file_count(approval_manifest, key="approved_files") if isinstance(approval_manifest, dict) else 0
        lines = [
            "Bulk write operator checklist created",
            "No files were written, renamed, deleted, or restored.",
            f"Source preflight status: {status}",
            f"Approved files: {approved_count}",
            f"Checklist folder: {checklist_dir}",
            "Files: checklist.md, manifest.json",
        ]
        audit_description = f"Bulk write operator checklist ({status})"
        return BulkOperatorChecklistResult(
            "\n".join(lines),
            checklist_dir,
            checklist_dir / "manifest.json",
            checklist_dir / "checklist.md",
            audit_description,
        )

    def create_bulk_restore_operator_checklist(self) -> BulkOperatorChecklistResult:
        """Create a local operator checklist for future bulk restore review without restoring files."""
        rollback_dir, rollback_manifest = self._latest_manifest(self.bulk_rollback_dir)
        checklist_dir = self._create_bulk_checklist_dir("restore")
        manifest = _build_bulk_operator_checklist_manifest(
            kind="bulk_restore_operator_checklist",
            operation="restore",
            source_manifest_path=rollback_dir / "manifest.json",
            source_manifest=rollback_manifest,
            checklist_items=_bulk_restore_operator_checklist_items(),
        )
        self._write_bulk_checklist_files(checklist_dir, manifest)
        restore_count = _manifest_file_count(rollback_manifest, key="rollback_entries")
        lines = [
            "Bulk restore operator checklist created",
            "No files were written, renamed, deleted, or restored.",
            f"Planned restore entries: {restore_count}",
            f"Checklist folder: {checklist_dir}",
            "Files: checklist.md, manifest.json",
        ]
        audit_description = f"Bulk restore operator checklist ({restore_count} restore entr(y/ies))"
        return BulkOperatorChecklistResult(
            "\n".join(lines),
            checklist_dir,
            checklist_dir / "manifest.json",
            checklist_dir / "checklist.md",
            audit_description,
        )

    def verify_bulk_write_operator_checklist(self) -> BulkOperatorChecklistVerification:
        """Verify the latest bulk write checklist without writing files."""
        return self._verify_bulk_operator_checklist(
            operation="write",
            expected_kind="bulk_write_operator_checklist",
            expected_source_kind="bulk_write_preflight",
            expected_source_status="preflight_ready",
        )

    def verify_bulk_restore_operator_checklist(self) -> BulkOperatorChecklistVerification:
        """Verify the latest bulk restore checklist without restoring files."""
        return self._verify_bulk_operator_checklist(
            operation="restore",
            expected_kind="bulk_restore_operator_checklist",
            expected_source_kind="bulk_rollback_plan",
            expected_source_status=None,
        )

    def _verify_bulk_operator_checklist(
        self,
        *,
        operation: str,
        expected_kind: str,
        expected_source_kind: str,
        expected_source_status: str | None,
    ) -> BulkOperatorChecklistVerification:
        title = f"Bulk {operation} checklist verification"
        notes = ["No files were written, renamed, deleted, or restored."]
        checklist_dir: Path | None = None

        try:
            checklist_dir, manifest = self._latest_bulk_checklist_manifest(operation)
            notes.extend(
                _bulk_operator_checklist_verification_notes(
                    manifest=manifest,
                    expected_kind=expected_kind,
                    expected_operation=operation,
                    expected_source_kind=expected_source_kind,
                    expected_source_status=expected_source_status,
                )
            )
        except FileToolError as exc:
            notes.append(str(exc))

        status = "verified" if all(not note.startswith("BLOCKED:") for note in notes) else "blocked"
        lines = [
            title,
            f"Status: {status}",
        ]
        if checklist_dir is not None:
            lines.append(f"Checklist folder: {checklist_dir}")
        lines.extend(
            [
                "Verification notes:",
                *[f"- {note}" for note in notes],
                "This does not grant permission, write files, or restore files.",
            ]
        )
        audit_description = f"Bulk {operation} checklist verification: {status}"
        return BulkOperatorChecklistVerification(
            "\n".join(lines),
            checklist_dir,
            status,
            audit_description,
        )

    def _allowed_folders(self) -> dict[str, str]:
        try:
            return load_allowed_folders(self.folders_path)
        except ActionError as exc:
            raise FileToolError(str(exc)) from exc

    def _resolve_folder(self, folder_name: str) -> tuple[str, Path]:
        folders = self._allowed_folders()
        canonical_name = normalize_action_text(folder_name)
        target = folders.get(canonical_name)
        if target is None:
            raise FileToolError("Allowed folder must be one of: " + ", ".join(sorted(folders)))

        root = Path(target).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileToolError(f"Allowed folder is not available: {canonical_name}")
        return canonical_name, root

    def _resolve_file(self, root: Path, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or candidate.drive:
            raise FileToolError("File path must be relative to the allowlisted folder.")
        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root):
            raise FileToolError("File path must stay inside the allowlisted folder.")
        if not resolved.exists():
            raise FileToolError(f"File not found: {relative_path}")
        if not resolved.is_file():
            raise FileToolError(f"Target is not a file: {relative_path}")
        return resolved

    def _resolve_restore_target(self, root: Path, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or candidate.drive:
            raise FileToolError("Restore path must be relative to the allowlisted folder.")
        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root):
            raise FileToolError("Restore path must stay inside the allowlisted folder.")
        if resolved.exists():
            raise FileToolError(f"Restore target already exists: {relative_path}")
        return resolved

    def _reject_trash_storage_path(self, path: Path) -> None:
        resolved = path.resolve()
        trash_dir = self.trash_dir.resolve()
        manifest = self.manifest_path.resolve()
        if resolved == manifest or resolved.is_relative_to(trash_dir):
            raise FileToolError("Assistant trash storage files cannot be moved to trash.")

    def _create_bulk_backup_dir(self, kind: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup_dir = self.bulk_backup_dir / f"bulk-{kind}-{timestamp}"
        if backup_dir.exists():
            backup_dir = self.bulk_backup_dir / f"bulk-{kind}-{timestamp}-{uuid4().hex[:8]}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        return backup_dir

    def _create_bulk_approval_dir(self, kind: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        approval_dir = self.bulk_approval_dir / f"bulk-{kind}-approval-{timestamp}"
        if approval_dir.exists():
            approval_dir = self.bulk_approval_dir / f"bulk-{kind}-approval-{timestamp}-{uuid4().hex[:8]}"
        approval_dir.mkdir(parents=True, exist_ok=False)
        return approval_dir

    def _create_bulk_review_dir(self) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        review_dir = self.bulk_review_dir / f"bulk-apply-review-{timestamp}"
        if review_dir.exists():
            review_dir = self.bulk_review_dir / f"bulk-apply-review-{timestamp}-{uuid4().hex[:8]}"
        review_dir.mkdir(parents=True, exist_ok=False)
        return review_dir

    def _create_bulk_rollback_dir(self) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        rollback_dir = self.bulk_rollback_dir / f"bulk-rollback-plan-{timestamp}"
        if rollback_dir.exists():
            rollback_dir = self.bulk_rollback_dir / f"bulk-rollback-plan-{timestamp}-{uuid4().hex[:8]}"
        rollback_dir.mkdir(parents=True, exist_ok=False)
        return rollback_dir

    def _create_bulk_preflight_dir(self) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        preflight_dir = self.bulk_preflight_dir / f"bulk-write-preflight-{timestamp}"
        if preflight_dir.exists():
            preflight_dir = self.bulk_preflight_dir / f"bulk-write-preflight-{timestamp}-{uuid4().hex[:8]}"
        preflight_dir.mkdir(parents=True, exist_ok=False)
        return preflight_dir

    def _create_bulk_checklist_dir(self, operation: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        checklist_dir = self.bulk_checklist_dir / f"bulk-{operation}-checklist-{timestamp}"
        if checklist_dir.exists():
            checklist_dir = self.bulk_checklist_dir / f"bulk-{operation}-checklist-{timestamp}-{uuid4().hex[:8]}"
        checklist_dir.mkdir(parents=True, exist_ok=False)
        return checklist_dir

    @staticmethod
    def _latest_manifest(root: Path) -> tuple[Path, dict[str, object]]:
        if not root.exists():
            raise FileToolError(f"No bulk manifest folder found at: {root}")
        candidates = [
            path
            for path in root.iterdir()
            if path.is_dir() and (path / "manifest.json").exists()
        ]
        if not candidates:
            raise FileToolError(f"No bulk manifests found at: {root}")
        latest = sorted(candidates, key=lambda path: path.name, reverse=True)[0]
        try:
            raw = json.loads((latest / "manifest.json").read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise FileToolError(f"Invalid bulk manifest: {latest / 'manifest.json'}") from exc
        except OSError as exc:
            raise FileToolError(f"Could not read bulk manifest: {latest / 'manifest.json'}") from exc
        if not isinstance(raw, dict):
            raise FileToolError(f"Bulk manifest must be a JSON object: {latest / 'manifest.json'}")
        return latest, raw

    def _latest_bulk_checklist_manifest(self, operation: str) -> tuple[Path, dict[str, object]]:
        if not self.bulk_checklist_dir.exists():
            raise FileToolError(f"No bulk checklist folder found at: {self.bulk_checklist_dir}")
        prefix = f"bulk-{operation}-checklist-"
        candidates = [
            path
            for path in self.bulk_checklist_dir.iterdir()
            if path.is_dir() and path.name.startswith(prefix) and (path / "manifest.json").exists()
        ]
        if not candidates:
            raise FileToolError(f"No bulk {operation} checklist manifests found at: {self.bulk_checklist_dir}")
        latest = sorted(candidates, key=lambda path: path.name, reverse=True)[0]
        return latest, _read_json_manifest(latest / "manifest.json", "Bulk checklist")

    def _list_files(self, root: Path, limit: int) -> list[Path]:
        files: list[Path] = []
        for path in sorted(root.rglob("*")):
            if len(files) >= limit:
                break
            if any(part in SKIPPED_DIR_NAMES for part in path.parts):
                continue
            if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
                files.append(path)
        return files

    @staticmethod
    def _validate_text_file(path: Path, max_bytes: int) -> None:
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            raise FileToolError("Only common text files can be read or searched.")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise FileToolError(f"Could not inspect file: {path.name}") from exc
        if size > max_bytes:
            raise FileToolError(f"File is too large for a safe preview: {path.name}")

    def _write_file_trash(self, entries: list[FileTrashEntry]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "deleted_files": [
                {
                    "original_folder_name": entry.original_folder_name,
                    "original_relative_path": entry.original_relative_path,
                    "trash_path": entry.trash_path,
                    "deleted_at": entry.deleted_at,
                }
                for entry in entries
            ]
        }
        try:
            self.manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise FileToolError(f"Could not write file trash manifest: {self.manifest_path}") from exc

    @staticmethod
    def _write_bulk_backup_manifest(backup_dir: Path, manifest: dict[str, object]) -> None:
        try:
            (backup_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise FileToolError(f"Could not write bulk backup manifest: {backup_dir}") from exc

    @staticmethod
    def _write_bulk_approval_manifest(approval_dir: Path, manifest: dict[str, object]) -> None:
        try:
            (approval_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise FileToolError(f"Could not write bulk approval manifest: {approval_dir}") from exc

    @staticmethod
    def _write_bulk_review_manifest(review_dir: Path, manifest: dict[str, object]) -> None:
        try:
            (review_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise FileToolError(f"Could not write bulk apply review manifest: {review_dir}") from exc

    @staticmethod
    def _write_bulk_rollback_manifest(rollback_dir: Path, manifest: dict[str, object]) -> None:
        try:
            (rollback_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise FileToolError(f"Could not write bulk rollback manifest: {rollback_dir}") from exc

    @staticmethod
    def _write_bulk_preflight_manifest(preflight_dir: Path, manifest: dict[str, object]) -> None:
        try:
            (preflight_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise FileToolError(f"Could not write bulk write preflight manifest: {preflight_dir}") from exc

    @staticmethod
    def _write_bulk_checklist_files(checklist_dir: Path, manifest: dict[str, object]) -> None:
        try:
            (checklist_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            (checklist_dir / "checklist.md").write_text(
                _bulk_operator_checklist_markdown(manifest),
                encoding="utf-8",
            )
        except OSError as exc:
            raise FileToolError(f"Could not write bulk operator checklist: {checklist_dir}") from exc


def file_tools_help_text(folders_path: str | Path = DEFAULT_FOLDERS_PATH) -> str:
    tools = AllowlistedFileTools(folders_path)
    try:
        folders = ", ".join(tools.folder_names())
    except FileToolError as exc:
        folders = f"unavailable ({exc})"
    return (
        "Safe file tools\n"
        f"Allowed folders: {folders}\n"
        "Commands:\n"
        "- list files in <folder>\n"
        "- search files in <folder> for <text>\n"
        "- find files in <folder> for <name text>\n"
        "- read file in <folder> <relative path>\n"
        "- open file in <folder> <relative path> (safe preview; does not launch the file)\n"
        "- launch file in <folder> <relative path> (requires confirmation and file-type allowlist)\n"
        "- file type trust <extension>\n"
        "- trust file type source <extension>: <source path>[; <source path>...]\n"
        "- trust file type signer <extension>: <signer token>[; <signer token>...]\n"
        "- trust file type thumbprint <extension>: <thumbprint>[; <thumbprint>...]\n"
        "- trust file type issuer <extension>: <issuer token>[; <issuer token>...]\n"
        "- trust file type validity <extension>: required|off\n"
        "- trust file type revocation <extension>: required|off|ocsp|crl|both\n"
        "- clear file type trust <extension>\n"
        "- preview replace in <folder> find <text> with <text> (dry run only)\n"
        "- preview rename files in <folder> replace <name text> with <name text> (dry run only)\n"
        "- bulk apply safety (explains backup and per-file approval requirements)\n"
        "- bulk replace apply plan in <folder> find <text> with <text> (safety plan only)\n"
        "- bulk rename apply plan in <folder> replace <name text> with <name text> (safety plan only)\n"
        "- backup bulk replace in <folder> find <text> with <text> (copies planned files; does not apply)\n"
        "- backup bulk rename in <folder> replace <name text> with <name text> (copies planned files; does not apply)\n"
        "- approve bulk replace in <folder> find <text> with <text> files <numbers|all> (saves approval only)\n"
        "- approve bulk rename in <folder> replace <name text> with <name text> files <numbers|all> (saves approval only)\n"
        "- bulk apply review (creates audit-linked review; does not apply)\n"
        "- bulk rollback plan (creates restore plan from latest backup; does not restore)\n"
        "- bulk write preflight (validates manifests and signs review metadata; does not write or restore)\n"
        "- bulk write checklist (review checklist only; does not write)\n"
        "- bulk restore checklist (review checklist only; does not restore)\n"
        "- verify bulk write checklist (integrity check only; does not write)\n"
        "- verify bulk restore checklist (integrity check only; does not restore)\n"
        "- bulk write command design (design only; does not write)\n"
        "- bulk restore command design (design only; does not restore)\n"
        "- delete file in <folder> <relative path> (requires confirmation; moves to assistant trash)\n"
        "- file trash\n"
        "- restore file <trash number>\n"
        "File commands are limited to allowlisted folders. Open shows a text preview only. Launch file requires confirmation and explicit file-type allowlisting before Windows open. Optional trust signals can also require trusted sources, signer token matches, exact certificate thumbprint pins, issuer-token matches, currently-valid certificates, and certificate revocation checks. Bulk previews do not write files. Delete moves text files to assistant trash, not permanent deletion."
    )


def _bulk_backup_summary(title: str, backup_dir: Path, copied_files: list[str]) -> str:
    lines = [
        title,
        "No original files were changed.",
        "Apply is still not enabled in this build.",
        f"Backup folder: {backup_dir}",
        f"Backed up files: {len(copied_files)}",
        "Hash algorithm: sha256",
        "Files:",
    ]
    for index, relative_path in enumerate(copied_files, start=1):
        lines.append(f"{index}. {relative_path}")
    lines.append("Manifest: manifest.json")
    return "\n".join(lines)


def _bulk_approval_summary(
    title: str,
    approval_dir: Path,
    selected_indexes: list[int],
    approved_files: list[str],
) -> str:
    lines = [
        title,
        "No original files were changed.",
        "Apply is still not enabled in this build.",
        f"Approval folder: {approval_dir}",
        f"Approved file count: {len(approved_files)}",
        "Approved indexes: " + ", ".join(str(index) for index in selected_indexes),
        "Hash algorithm: sha256",
        "Files:",
    ]
    for index, relative_path in enumerate(approved_files, start=1):
        lines.append(f"{index}. {relative_path}")
    lines.append("Manifest: manifest.json")
    return "\n".join(lines)


def _parse_bulk_selection(selection_text: str, item_count: int) -> list[int]:
    clean_selection = selection_text.strip().lower()
    if not clean_selection:
        raise FileToolError("Bulk approval needs file numbers or 'all'.")
    if clean_selection == "all":
        return list(range(1, item_count + 1))

    selected: list[int] = []
    for raw_part in clean_selection.replace(",", " ").split():
        try:
            number = int(raw_part)
        except ValueError as exc:
            raise FileToolError("Bulk approval file selection must be numbers or 'all'.") from exc
        if number < 1 or number > item_count:
            raise FileToolError(f"Bulk approval file number must be between 1 and {item_count}.")
        if number not in selected:
            selected.append(number)
    if not selected:
        raise FileToolError("Bulk approval needs at least one file number.")
    return selected


def _bulk_review_status(
    backup_manifest: dict[str, object],
    approval_manifest: dict[str, object],
) -> tuple[str, list[str]]:
    notes = [
        "Apply is disabled; this review is for audit and manual inspection only.",
    ]
    backup_hash_status, backup_hash_notes = _manifest_hash_status(backup_manifest, "Backup")
    notes.extend(backup_hash_notes)
    if backup_hash_status != "ok":
        return "blocked", notes

    approval_hash_status, approval_hash_notes = _manifest_hash_status(approval_manifest, "Approval")
    notes.extend(approval_hash_notes)
    if approval_hash_status != "ok":
        return "blocked", notes

    backup_kind = backup_manifest.get("kind")
    approval_kind = approval_manifest.get("kind")
    expected_pairs = {
        "bulk_replace_backup": "bulk_replace_approval",
        "bulk_rename_backup": "bulk_rename_approval",
    }
    if not isinstance(backup_kind, str) or not isinstance(approval_kind, str):
        notes.append("Backup or approval manifest is missing a valid kind.")
        return "blocked", notes
    if expected_pairs.get(backup_kind) != approval_kind:
        notes.append(f"Manifest kinds do not match: {backup_kind} vs {approval_kind}.")
        return "blocked", notes

    for field in _required_review_fields(backup_kind):
        if backup_manifest.get(field) != approval_manifest.get(field):
            notes.append(f"Manifest field mismatch: {field}.")
            return "blocked", notes

    backup_count = _manifest_file_count(backup_manifest, key="files")
    approved_count = _manifest_file_count(approval_manifest, key="approved_files")
    if backup_count <= 0:
        notes.append("Backup manifest has no files.")
        return "blocked", notes
    if approved_count <= 0:
        notes.append("Approval manifest has no approved files.")
        return "blocked", notes
    if approved_count > backup_count:
        notes.append("Approval manifest has more approved files than the backup manifest.")
        return "blocked", notes

    hash_status, hash_notes = _bulk_approval_hash_status(backup_manifest, approval_manifest)
    notes.extend(hash_notes)
    if hash_status != "ok":
        return "blocked", notes

    notes.append("Backup and approval manifests are compatible.")
    notes.append("A future apply step would still require a separate confirmation and audit entry.")
    return "review_ready", notes


def _required_review_fields(backup_kind: str) -> tuple[str, ...]:
    if backup_kind == "bulk_replace_backup":
        return ("folder", "find", "replace_with")
    if backup_kind == "bulk_rename_backup":
        return ("folder", "filename_find", "replace_with")
    return ()


def _manifest_file_count(manifest: dict[str, object], key: str) -> int:
    files = manifest.get(key)
    if not isinstance(files, list):
        return 0
    return len(files)


def _rollback_entries_from_backup_manifest(manifest: dict[str, object]) -> list[dict[str, object]]:
    kind = manifest.get("kind")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise FileToolError("Backup manifest has no files to plan rollback from.")

    entries: list[dict[str, str]] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        if kind == "bulk_replace_backup":
            relative_path = raw_file.get("relative_path")
            if isinstance(relative_path, str) and relative_path:
                entry = {
                    "backup_relative_path": relative_path,
                    "restore_relative_path": relative_path,
                }
                _copy_hash_fields(raw_file, entry, ("backup_size", "backup_sha256"))
                entries.append(entry)
        elif kind == "bulk_rename_backup":
            old_relative_path = raw_file.get("old_relative_path")
            if isinstance(old_relative_path, str) and old_relative_path:
                entry = {
                    "backup_relative_path": old_relative_path,
                    "restore_relative_path": old_relative_path,
                }
                _copy_hash_fields(raw_file, entry, ("backup_size", "backup_sha256"))
                entries.append(entry)
        else:
            raise FileToolError(f"Unsupported backup manifest kind for rollback: {kind}")
    if not entries:
        raise FileToolError("Backup manifest has no valid rollback entries.")
    return entries


def _file_metadata(path: Path) -> dict[str, object]:
    try:
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FileToolError(f"Could not hash file: {path}") from exc
    return {"size": size, "sha256": digest.hexdigest()}


def _prefixed_file_metadata(path: Path, prefix: str) -> dict[str, object]:
    metadata = _file_metadata(path)
    return {
        f"{prefix}_size": metadata["size"],
        f"{prefix}_sha256": metadata["sha256"],
    }


def _copy_hash_fields(source: dict[str, object], target: dict[str, object], fields: tuple[str, ...]) -> None:
    for field in fields:
        value = source.get(field)
        if value is not None:
            target[field] = value


def _manifest_sha256(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(encoded)
    return digest.hexdigest()


def _bulk_preflight_review_signature(metadata: dict[str, object]) -> str:
    payload = {key: value for key, value in metadata.items() if key != "review_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(encoded)
    return digest.hexdigest()


def _bulk_operator_checklist_signature(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "checklist_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(encoded)
    return digest.hexdigest()


def _read_json_manifest(path: Path, label: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise FileToolError(f"Invalid {label.lower()} manifest: {path}") from exc
    except OSError as exc:
        raise FileToolError(f"Could not read {label.lower()} manifest: {path}") from exc
    if not isinstance(raw, dict):
        raise FileToolError(f"{label} manifest must be a JSON object: {path}")
    return raw


def _bulk_operator_checklist_verification_notes(
    *,
    manifest: dict[str, object],
    expected_kind: str,
    expected_operation: str,
    expected_source_kind: str,
    expected_source_status: str | None,
) -> list[str]:
    notes: list[str] = []

    if manifest.get("schema") != BULK_OPERATOR_CHECKLIST_SCHEMA:
        notes.append("BLOCKED: Checklist schema is not recognized.")
    if manifest.get("kind") != expected_kind:
        notes.append("BLOCKED: Checklist kind does not match the requested operation.")
    if manifest.get("operation") != expected_operation:
        notes.append("BLOCKED: Checklist operation does not match the requested operation.")
    if manifest.get("write_enabled") is not False:
        notes.append("BLOCKED: Checklist must keep write_enabled false.")
    if manifest.get("restore_enabled") is not False:
        notes.append("BLOCKED: Checklist must keep restore_enabled false.")
    if manifest.get("applies_changes") is not False:
        notes.append("BLOCKED: Checklist must keep applies_changes false.")

    recorded_signature = manifest.get("checklist_signature")
    if not isinstance(recorded_signature, str) or not recorded_signature:
        notes.append("BLOCKED: Checklist signature is missing.")
    elif recorded_signature != _bulk_operator_checklist_signature(manifest):
        notes.append("BLOCKED: Checklist signature mismatch.")
    else:
        notes.append("Checklist signature matches.")

    checklist = manifest.get("checklist")
    if not isinstance(checklist, list) or not checklist:
        notes.append("BLOCKED: Checklist items are missing.")
    else:
        notes.append(f"Checklist contains {len(checklist)} required review item(s).")

    source_manifest_text = manifest.get("source_manifest")
    if not isinstance(source_manifest_text, str) or not source_manifest_text:
        notes.append("BLOCKED: Source manifest path is missing.")
        return notes

    source_manifest_path = Path(source_manifest_text)
    if not source_manifest_path.is_file():
        notes.append(f"BLOCKED: Source manifest file is missing: {source_manifest_path}")
        return notes

    source_manifest = _read_json_manifest(source_manifest_path, "Source")
    source_hash_status, source_hash_notes = _manifest_hash_status(source_manifest, "Source")
    notes.extend(source_hash_notes)
    if source_hash_status != "ok":
        notes.append("BLOCKED: Source manifest hash could not be verified.")

    if manifest.get("source_manifest_kind") != source_manifest.get("kind"):
        notes.append("BLOCKED: Recorded source manifest kind does not match the source file.")
    if manifest.get("source_manifest_sha256") != source_manifest.get("manifest_sha256"):
        notes.append("BLOCKED: Recorded source manifest hash does not match the source file.")

    if source_manifest.get("kind") != expected_source_kind:
        notes.append("BLOCKED: Source manifest kind is not valid for this checklist.")
    elif expected_source_status is not None and source_manifest.get("status") != expected_source_status:
        notes.append(f"BLOCKED: Source manifest status is not {expected_source_status}.")
    else:
        notes.append("Source manifest matches the checklist record.")

    return notes


def _build_bulk_operator_checklist_manifest(
    *,
    kind: str,
    operation: str,
    source_manifest_path: Path,
    source_manifest: dict[str, object],
    checklist_items: list[str],
) -> dict[str, object]:
    manifest = {
        "schema": BULK_OPERATOR_CHECKLIST_SCHEMA,
        "kind": kind,
        "operation": operation,
        "created_at": _utc_now_iso(),
        "write_enabled": False,
        "restore_enabled": False,
        "applies_changes": False,
        "source_manifest": str(source_manifest_path),
        "source_manifest_kind": source_manifest.get("kind"),
        "source_manifest_sha256": source_manifest.get("manifest_sha256"),
        "source_status": source_manifest.get("status"),
        "checklist": checklist_items,
        "notes": [
            "This checklist is for human review only.",
            "Creating this checklist does not write, rename, delete, or restore files.",
            "A future implementation would still require separate typed confirmation and audit.",
        ],
    }
    manifest["checklist_signature"] = _bulk_operator_checklist_signature(manifest)
    return manifest


def _bulk_write_operator_checklist_items() -> list[str]:
    return [
        "Confirm the latest bulk write preflight status is preflight_ready.",
        "Confirm backup, approval, apply review, rollback, and preflight manifest hashes match.",
        "Confirm approved file count and rollback entry count are shown to the user.",
        "Confirm every target file still matches the preflight source hash and size before any future write.",
        "Confirm rollback plan exists and restore_enabled remains false before any future write.",
        "Confirm no write starts unless the user types the exact future confirmation phrase.",
        "Confirm any failed check blocks all writes.",
    ]


def _bulk_restore_operator_checklist_items() -> list[str]:
    return [
        "Confirm the rollback manifest kind is bulk_rollback_plan.",
        "Confirm restore_enabled is false in the review artifact.",
        "Confirm every backup file exists and matches recorded backup hash and size before any future restore.",
        "Confirm every restore path stays inside the original allowlisted folder.",
        "Confirm restore refuses to overwrite unrelated files.",
        "Confirm restore never permanently deletes files.",
        "Confirm any ambiguous restore entry is skipped and reported for manual review.",
    ]


def _bulk_operator_checklist_markdown(manifest: dict[str, object]) -> str:
    lines = [
        "# Bulk Operator Checklist",
        "",
        f"Operation: {manifest.get('operation')}",
        f"Source manifest: {manifest.get('source_manifest')}",
        f"Source status: {manifest.get('source_status')}",
        "",
        "This checklist is review-only. It did not write, rename, delete, or restore files.",
        "",
        "## Required Checks",
    ]
    checklist = manifest.get("checklist")
    if isinstance(checklist, list):
        lines.extend(f"- [ ] {item}" for item in checklist)
    lines.extend(
        [
            "",
            "## Final Review",
            "- [ ] I understand this checklist does not grant permission or execute anything.",
            "- [ ] I will only proceed through a separately implemented confirmation-gated path.",
            "",
            f"Checklist signature: {manifest.get('checklist_signature')}",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_bulk_preflight_review_metadata(
    *,
    status: str,
    approved_count: int,
    rollback_count: int,
    backup_manifest_path: Path,
    approval_manifest_path: Path,
    review_manifest_path: Path,
    rollback_manifest_path: Path,
    notes: list[str],
    backup_manifest: dict[str, object],
    approval_manifest: dict[str, object],
    review_manifest: dict[str, object],
    rollback_manifest: dict[str, object],
) -> dict[str, object]:
    """Build a local tamper-evident review record without enabling writes."""
    metadata: dict[str, object] = {
        "schema": BULK_PREFLIGHT_REVIEW_SCHEMA,
        "created_at": _utc_now_iso(),
        "status": status,
        "write_enabled": False,
        "restore_enabled": False,
        "approved_files": approved_count,
        "rollback_entries": rollback_count,
        "backup_manifest": str(backup_manifest_path),
        "approval_manifest": str(approval_manifest_path),
        "review_manifest": str(review_manifest_path),
        "rollback_manifest": str(rollback_manifest_path),
        "backup_manifest_sha256": backup_manifest.get("manifest_sha256"),
        "approval_manifest_sha256": approval_manifest.get("manifest_sha256"),
        "review_manifest_sha256": review_manifest.get("manifest_sha256"),
        "rollback_manifest_sha256": rollback_manifest.get("manifest_sha256"),
        "notes": notes,
        "review_notes": [
            "Signed review metadata is local and tamper-evident only.",
            "Write and restore remain disabled in this build.",
            "A future write or restore command would still require separate typed confirmation.",
        ],
    }
    metadata["review_signature"] = _bulk_preflight_review_signature(metadata)
    return metadata


def _annotate_manifest_hash(manifest: dict[str, object]) -> dict[str, object]:
    manifest["manifest_sha256"] = _manifest_sha256(manifest)
    return manifest


def _manifest_hash_status(manifest: dict[str, object], label: str) -> tuple[str, list[str]]:
    recorded_hash = manifest.get("manifest_sha256")
    if not isinstance(recorded_hash, str) or not recorded_hash:
        return "blocked", [f"{label} manifest is missing a manifest hash."]
    if recorded_hash != _manifest_sha256(manifest):
        return "blocked", [f"{label} manifest hash mismatch."]
    return "ok", [f"{label} manifest hash matches."]


def _backup_entry_key(manifest_kind: object, entry: dict[str, object]) -> str | None:
    if manifest_kind == "bulk_replace_backup":
        value = entry.get("relative_path")
    elif manifest_kind == "bulk_rename_backup":
        value = entry.get("old_relative_path")
    else:
        return None
    return value if isinstance(value, str) and value else None


def _approval_entry_key(manifest_kind: object, entry: dict[str, object]) -> str | None:
    if manifest_kind == "bulk_replace_approval":
        value = entry.get("relative_path")
    elif manifest_kind == "bulk_rename_approval":
        value = entry.get("old_relative_path")
    else:
        return None
    return value if isinstance(value, str) and value else None


def _backup_entries_by_path(backup_manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_files = backup_manifest.get("files")
    if not isinstance(raw_files, list):
        return {}
    entries: dict[str, dict[str, object]] = {}
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        key = _backup_entry_key(backup_manifest.get("kind"), raw_file)
        if key:
            entries[key] = raw_file
    return entries


def _bulk_approval_hash_status(
    backup_manifest: dict[str, object],
    approval_manifest: dict[str, object],
) -> tuple[str, list[str]]:
    notes: list[str] = []
    backup_entries = _backup_entries_by_path(backup_manifest)
    raw_approved = approval_manifest.get("approved_files")
    if not isinstance(raw_approved, list):
        return "blocked", ["Approval manifest has no approved file hash metadata."]

    for raw_file in raw_approved:
        if not isinstance(raw_file, dict):
            return "blocked", ["Approval manifest contains an invalid approved file entry."]
        key = _approval_entry_key(approval_manifest.get("kind"), raw_file)
        if key is None:
            return "blocked", ["Approval manifest contains an approved file without a relative path."]
        backup_entry = backup_entries.get(key)
        if backup_entry is None:
            return "blocked", [f"Approved file is missing from backup manifest: {key}."]
        if raw_file.get("source_size") != backup_entry.get("source_size"):
            return "blocked", [f"Source size mismatch for approved file: {key}."]
        if raw_file.get("source_sha256") != backup_entry.get("source_sha256"):
            return "blocked", [f"Source hash mismatch for approved file: {key}."]

    notes.append("Approved file source hashes match the backup manifest.")
    return "ok", notes


def _bulk_backup_file_hash_status(
    backup_dir: Path,
    backup_manifest: dict[str, object],
) -> tuple[str, list[str]]:
    notes: list[str] = []
    files_dir = backup_dir / "files"
    raw_files = backup_manifest.get("files")
    if not isinstance(raw_files, list):
        return "blocked", ["Backup manifest has no file hash metadata."]

    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            return "blocked", ["Backup manifest contains an invalid file entry."]
        relative_path = _backup_entry_key(backup_manifest.get("kind"), raw_file)
        if relative_path is None:
            return "blocked", ["Backup manifest contains a file without a relative backup path."]
        backup_path = (files_dir / relative_path).resolve()
        try:
            backup_path.relative_to(files_dir.resolve())
        except ValueError:
            return "blocked", [f"Backup file path escapes backup folder: {relative_path}."]
        if not backup_path.is_file():
            return "blocked", [f"Backup file is missing: {relative_path}."]
        metadata = _file_metadata(backup_path)
        if raw_file.get("backup_size") != metadata["size"]:
            return "blocked", [f"Backup size mismatch: {relative_path}."]
        if raw_file.get("backup_sha256") != metadata["sha256"]:
            return "blocked", [f"Backup hash mismatch: {relative_path}."]

    notes.append("Backup file hashes match the backup manifest.")
    return "ok", notes


def _bulk_rollback_hash_status(
    backup_manifest: dict[str, object],
    rollback_manifest: dict[str, object],
) -> tuple[str, list[str]]:
    backup_entries = _backup_entries_by_path(backup_manifest)
    raw_entries = rollback_manifest.get("rollback_entries")
    if not isinstance(raw_entries, list):
        return "blocked", ["Rollback manifest has no rollback hash metadata."]

    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            return "blocked", ["Rollback manifest contains an invalid entry."]
        relative_path = raw_entry.get("backup_relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            return "blocked", ["Rollback entry is missing a backup relative path."]
        backup_entry = backup_entries.get(relative_path)
        if backup_entry is None:
            return "blocked", [f"Rollback entry is missing from backup manifest: {relative_path}."]
        if raw_entry.get("backup_size") != backup_entry.get("backup_size"):
            return "blocked", [f"Rollback backup size mismatch: {relative_path}."]
        if raw_entry.get("backup_sha256") != backup_entry.get("backup_sha256"):
            return "blocked", [f"Rollback backup hash mismatch: {relative_path}."]

    return "ok", ["Rollback entry hashes match the backup manifest."]


def _bulk_write_preflight_status(
    backup_dir: Path,
    backup_manifest: dict[str, object],
    approval_manifest: dict[str, object],
    review_manifest: dict[str, object],
    rollback_manifest: dict[str, object],
) -> tuple[str, list[str]]:
    notes = [
        "Write and restore are disabled; this preflight is for audit and manual inspection only.",
    ]
    backup_hash_status, backup_hash_notes = _manifest_hash_status(backup_manifest, "Backup")
    notes.extend(backup_hash_notes)
    if backup_hash_status != "ok":
        return "blocked", notes

    approval_hash_status, approval_hash_notes = _manifest_hash_status(approval_manifest, "Approval")
    notes.extend(approval_hash_notes)
    if approval_hash_status != "ok":
        return "blocked", notes

    review_hash_status, review_hash_notes = _manifest_hash_status(review_manifest, "Review")
    notes.extend(review_hash_notes)
    if review_hash_status != "ok":
        return "blocked", notes

    rollback_hash_status, rollback_hash_notes = _manifest_hash_status(rollback_manifest, "Rollback")
    notes.extend(rollback_hash_notes)
    if rollback_hash_status != "ok":
        return "blocked", notes

    review_status, review_notes = _bulk_review_status(backup_manifest, approval_manifest)
    notes.extend(review_notes)
    if review_status != "review_ready":
        notes.append("Apply review is not ready.")
        return "blocked", notes

    if review_manifest.get("kind") != "bulk_apply_review":
        notes.append("Latest review manifest is not a bulk apply review.")
        return "blocked", notes
    if review_manifest.get("status") != "review_ready":
        notes.append("Latest review manifest is not review_ready.")
        return "blocked", notes
    if review_manifest.get("apply_enabled") is not False:
        notes.append("Review manifest must keep apply_enabled false.")
        return "blocked", notes

    if rollback_manifest.get("kind") != "bulk_rollback_plan":
        notes.append("Latest rollback manifest is not a rollback plan.")
        return "blocked", notes
    if rollback_manifest.get("restore_enabled") is not False:
        notes.append("Rollback manifest must keep restore_enabled false.")
        return "blocked", notes

    rollback_count = _manifest_file_count(rollback_manifest, key="rollback_entries")
    backup_count = _manifest_file_count(backup_manifest, key="files")
    approved_count = _manifest_file_count(approval_manifest, key="approved_files")
    if rollback_count != backup_count:
        notes.append("Rollback entry count does not match backed up file count.")
        return "blocked", notes
    if approved_count <= 0:
        notes.append("No approved files found.")
        return "blocked", notes

    backup_hash_status, backup_hash_notes = _bulk_backup_file_hash_status(backup_dir, backup_manifest)
    notes.extend(backup_hash_notes)
    if backup_hash_status != "ok":
        return "blocked", notes

    rollback_hash_status, rollback_hash_notes = _bulk_rollback_hash_status(backup_manifest, rollback_manifest)
    notes.extend(rollback_hash_notes)
    if rollback_hash_status != "ok":
        return "blocked", notes

    notes.append("Backup, approval, review, and rollback manifests are compatible.")
    notes.append("Manifest hashes verified for backup, approval, review, rollback, approved files, and backup files.")
    notes.append("A future write step would still require a separate typed confirmation.")
    return "preflight_ready", notes


def _bulk_apply_requirements_text() -> str:
    return "\n".join(
        [
            "Backup requirement:",
            "- Create a timestamped local backup before changing any planned file.",
            "- Preserve each file's relative path inside the backup folder.",
            "Per-file approval requirement:",
            "- Show every planned file by number before apply.",
            "- Require explicit approval for each file or a typed all-files confirmation.",
            "Blocking rules:",
            "- Path traversal, unreadable files, oversized files, and rename conflicts stop apply.",
            "Audit requirement:",
            "- Record the command, approved files, backup path, and final result locally.",
        ]
    )


def _relative_text(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _trim_line(line: str, limit: int = 160) -> str:
    compact = " ".join(line.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _case_insensitive_replace(text: str, old: str, new: str) -> str:
    lowered = text.casefold()
    old_lowered = old.casefold()
    result: list[str] = []
    index = 0
    while True:
        match_index = lowered.find(old_lowered, index)
        if match_index == -1:
            result.append(text[index:])
            return "".join(result)
        result.append(text[index:match_index])
        result.append(new)
        index = match_index + len(old)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
