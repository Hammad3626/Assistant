"""Tests for the named backup/maintenance workflow.

These operations are implemented as plain Python file operations (no
subprocess/shell involved at all), scoped strictly to the existing folder
allowlist, with all "deletion" going through the reversible assistant trash.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistant.actions import save_allowed_folders
from assistant.backup_tools import (
    BackupToolError,
    backup_folder,
    find_temp_files,
    list_backups,
)
from assistant.core import LocalAssistant


class BackupToolsTests(unittest.TestCase):
    def _make_workspace(self, temp_dir: str) -> tuple[Path, Path, Path]:
        root = Path(temp_dir)
        source = root / "docs"
        source.mkdir()
        (source / "a.txt").write_text("hello", encoding="utf-8")
        (source / "notes.tmp").write_text("junk", encoding="utf-8")
        (source / "Thumbs.db").write_text("junk", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"docs": str(source)}, folders_path)
        return root, source, folders_path

    def test_backup_folder_copies_without_modifying_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, source, folders_path = self._make_workspace(temp_dir)
            backup_root = root / "backups"

            result = backup_folder("docs", folders_path, backup_root)

            self.assertEqual(result.file_count, 3)
            dest_files = sorted(p.name for p in Path(result.destination).rglob("*") if p.is_file())
            self.assertEqual(dest_files, ["Thumbs.db", "a.txt", "notes.tmp"])
            # Source must be untouched.
            source_files = sorted(p.name for p in source.rglob("*") if p.is_file())
            self.assertEqual(source_files, ["Thumbs.db", "a.txt", "notes.tmp"])

    def test_backup_folder_rejects_unallowlisted_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, _source, folders_path = self._make_workspace(temp_dir)
            with self.assertRaises(BackupToolError):
                backup_folder("not-a-real-folder", folders_path, root / "backups")

    def test_list_backups_reflects_recorded_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, _source, folders_path = self._make_workspace(temp_dir)
            backup_root = root / "backups"
            backup_folder("docs", folders_path, backup_root)

            records = list_backups("docs", backup_root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["folder_name"], "docs")

    def test_find_temp_files_only_matches_known_junk_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _root, _source, folders_path = self._make_workspace(temp_dir)
            matches = find_temp_files("docs", folders_path)
            names = sorted(m.relative_path for m in matches)
            self.assertEqual(names, ["Thumbs.db", "notes.tmp"])
            # a.txt must never be flagged as temp clutter.
            self.assertNotIn("a.txt", names)


class BackupMaintenanceCoreWorkflowTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> tuple[LocalAssistant, Path]:
        root = Path(temp_dir)
        source = root / "docs"
        source.mkdir()
        (source / "a.txt").write_text("hello", encoding="utf-8")
        (source / "notes.tmp").write_text("junk", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"docs": str(source)}, folders_path)
        assistant = LocalAssistant(
            use_llm=False,
            folders_path=folders_path,
            backup_root=root / "backups",
            data_export_dir=root / "exports",
            file_trash_dir=root / "file-trash",
            file_trash_manifest_path=root / "file-trash-manifest.json",
        )
        return assistant, source

    def test_backup_folder_command_does_not_collide_with_bulk_backup_commands(self) -> None:
        """Regression test: 'backup folder <name>' must not shadow the
        pre-existing 'backup bulk replace/rename in ...' commands.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)

            bulk_response = assistant.respond(
                "backup bulk replace in docs find hello with goodbye"
            )
            folder_response = assistant.respond("backup folder docs")

            self.assertNotEqual(bulk_response.text, folder_response.text)
            assert folder_response.pending_action is not None
            self.assertEqual(folder_response.pending_action.kind, "backup_folder")

    def test_folder_backups_command_does_not_collide_with_data_export_backups(self) -> None:
        """Regression test: 'list folder backups'/'folder backups' must not
        shadow the pre-existing data-export 'backups'/'list backups' command.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)

            data_export_response = assistant.respond("backups")
            self.assertNotIn("No backups found", data_export_response.text)

    def test_backup_folder_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)

            response = assistant.respond("backup folder docs")
            self.assertIsNotNone(response.pending_action)
            assert response.pending_action is not None
            self.assertEqual(response.pending_action.kind, "backup_folder")

            result = assistant.confirm_pending_action(response.pending_action)
            self.assertIn("Done: Backed up 'docs'", result)

            listing = assistant.respond("list folder backups docs")
            self.assertIn("docs", listing.text)

    def test_clear_temp_files_moves_to_reversible_trash_not_permanent_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, source = self._make_assistant(temp_dir)

            find_response = assistant.respond("find temp files in docs")
            self.assertIn("notes.tmp", find_response.text)

            clear_response = assistant.respond("clear temp files in docs")
            self.assertIsNotNone(clear_response.pending_action)
            assert clear_response.pending_action is not None
            self.assertEqual(clear_response.pending_action.kind, "clear_temp_files")
            self.assertIn("reversible", clear_response.text)
            self.assertIn("not permanent deletion", clear_response.text)

            result = assistant.confirm_pending_action(clear_response.pending_action)
            self.assertIn("Done: Moved 1 temp file", result)

            # The temp file must be gone from the source folder...
            self.assertFalse((source / "notes.tmp").exists())
            self.assertTrue((source / "a.txt").exists())
            # ...but recoverable from the assistant trash, not permanently deleted.
            trash_entries = assistant._file_tools().list_file_trash()
            self.assertEqual(len(trash_entries), 1)
            self.assertTrue(Path(trash_entries[0].trash_path).exists())

    def test_clear_temp_files_with_no_matches_does_not_create_pending_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "clean"
            source.mkdir()
            (source / "a.txt").write_text("hello", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"clean": str(source)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                backup_root=root / "backups",
                data_export_dir=root / "exports",
            )

            response = assistant.respond("clear temp files in clean")
            self.assertIsNone(response.pending_action)
            self.assertIn("Nothing to clear", response.text)


if __name__ == "__main__":
    unittest.main()
