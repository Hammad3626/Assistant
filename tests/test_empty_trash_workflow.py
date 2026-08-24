"""Tests for the explicit, confirmation-gated "empty trash" workflow.

Permanent deletion in this app has exactly one entry point:
purge_trash_entries(), reachable only via the "empty trash" /
"empty trash older than N days" commands, and only for items that are
already sitting in the reversible assistant trash (i.e. the person already
confirmed removing them once, as a normal delete-to-trash). It always
requires a second, explicit confirmation that previews exactly what will be
permanently removed.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from assistant.actions import save_allowed_folders
from assistant.core import LocalAssistant
from assistant.file_tools import AllowlistedFileTools, FileToolError


class EmptyTrashCoreWorkflowTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> tuple[LocalAssistant, Path]:
        root = Path(temp_dir)
        source = root / "docs"
        source.mkdir()
        (source / "a.txt").write_text("hello", encoding="utf-8")
        (source / "b.txt").write_text("world", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"docs": str(source)}, folders_path)
        assistant = LocalAssistant(
            use_llm=False,
            folders_path=folders_path,
            file_trash_dir=root / "trash",
            file_trash_manifest_path=root / "trash-manifest.json",
            data_export_dir=root / "exports",
        )
        return assistant, source

    def test_empty_trash_with_nothing_in_trash_has_no_pending_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            response = assistant.respond("empty trash")
            self.assertIsNone(response.pending_action)
            self.assertIn("Nothing to do", response.text)

    def test_empty_trash_requires_confirmation_and_previews_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            delete_response = assistant.respond("delete file in docs a.txt")
            assistant.confirm_pending_action(delete_response.pending_action)

            response = assistant.respond("empty trash")
            self.assertIsNotNone(response.pending_action)
            assert response.pending_action is not None
            self.assertEqual(response.pending_action.kind, "empty_trash")
            self.assertIn("PERMANENTLY", response.text)
            self.assertIn("cannot be undone", response.text)
            self.assertIn("docs/a.txt", response.text)

    def test_empty_trash_end_to_end_permanently_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            delete_response = assistant.respond("delete file in docs a.txt")
            assistant.confirm_pending_action(delete_response.pending_action)

            tools = assistant._file_tools()
            trash_entries = tools.list_file_trash()
            self.assertEqual(len(trash_entries), 1)
            trash_path = Path(trash_entries[0].trash_path)
            self.assertTrue(trash_path.exists())

            empty_response = assistant.respond("empty trash")
            result = assistant.confirm_pending_action(empty_response.pending_action)

            self.assertIn("Permanently deleted 1 trash entry", result)
            self.assertFalse(trash_path.exists())
            self.assertEqual(tools.list_file_trash(), [])

    def test_empty_trash_only_affects_specified_entries_not_all_files(self) -> None:
        """A file that was never moved to trash must never be touched by
        empty trash, even if it lives in the same allowlisted folder.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, source = self._make_assistant(temp_dir)
            delete_response = assistant.respond("delete file in docs a.txt")
            assistant.confirm_pending_action(delete_response.pending_action)

            empty_response = assistant.respond("empty trash")
            assistant.confirm_pending_action(empty_response.pending_action)

            # b.txt was never deleted/trashed and must be untouched.
            self.assertTrue((source / "b.txt").exists())

    def test_empty_trash_older_than_days_only_selects_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            delete_response = assistant.respond("delete file in docs a.txt")
            assistant.confirm_pending_action(delete_response.pending_action)

            # A freshly trashed entry is not older than 30 days.
            response = assistant.respond("empty trash older than 30 days")
            self.assertIsNone(response.pending_action)
            self.assertIn("Nothing to do", response.text)

            # But it is older than -1 days (i.e. everything qualifies).
            response = assistant.respond("empty trash older than 0 days")
            self.assertIsNotNone(response.pending_action)

    def test_empty_trash_malformed_days_argument_gives_helpful_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            response = assistant.respond("empty trash older than banana days")
            self.assertIsNone(response.pending_action)
            self.assertIn("empty trash", response.text.lower())


class PurgeTrashEntriesUnitTests(unittest.TestCase):
    def _tools(self, temp_dir: str) -> tuple[AllowlistedFileTools, Path]:
        root = Path(temp_dir)
        source = root / "docs"
        source.mkdir()
        (source / "a.txt").write_text("hello", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"docs": str(source)}, folders_path)
        tools = AllowlistedFileTools(
            folders_path=folders_path,
            trash_dir=root / "trash",
            manifest_path=root / "trash-manifest.json",
        )
        return tools, source

    def test_purge_requires_at_least_one_entry_number(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            with self.assertRaises(FileToolError):
                tools.purge_trash_entries([])

    def test_purge_rejects_out_of_range_entry_number(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            tools.move_file_to_trash("docs", "a.txt")
            with self.assertRaises(FileToolError):
                tools.purge_trash_entries([5])

    def test_trash_entries_older_than_uses_deleted_at_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            tools.move_file_to_trash("docs", "a.txt")

            # Not older than 30 days yet.
            self.assertEqual(tools.trash_entries_older_than(30), [])
            # Older than -1 days (i.e. any positive-in-the-past cutoff) matches.
            matches = tools.trash_entries_older_than(0)
            self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
