"""Tests for generic action-audit logging in confirm_pending_action().

Previously, action_audit_store.record() was only ever called from two
niche script-simulation code paths -- every other confirmed action (delete
file, empty trash, commit bulk replace, send notification, add app/folder,
run shell command, etc.) left no audit trail at all. confirm_pending_action()
now wraps _execute_pending_action() and records every attempt, successful
or not.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistant.actions import PendingAction, save_allowed_folders
from assistant.audit import ActionAuditStore
from assistant.core import LocalAssistant


class ConfirmPendingActionAuditTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> tuple[LocalAssistant, Path]:
        root = Path(temp_dir)
        source = root / "docs"
        source.mkdir()
        (source / "a.txt").write_text("hello", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"docs": str(source)}, folders_path)
        assistant = LocalAssistant(
            use_llm=False,
            folders_path=folders_path,
            data_export_dir=root / "exports",
            action_audit_store=ActionAuditStore(root / "action_audit.jsonl"),
        )
        return assistant, source

    def test_successful_action_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            response = assistant.respond("delete file in docs a.txt")
            assistant.confirm_pending_action(response.pending_action)

            entries = assistant.action_audit_store.recent()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].status, "confirmed")
            self.assertEqual(entries[0].action_kind, "file_delete")
            self.assertIn("Done", entries[0].result)

    def test_multiple_actions_all_recorded_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, source = self._make_assistant(temp_dir)
            (source / "b.txt").write_text("world", encoding="utf-8")

            r1 = assistant.respond("delete file in docs a.txt")
            assistant.confirm_pending_action(r1.pending_action)
            r2 = assistant.respond("delete file in docs b.txt")
            assistant.confirm_pending_action(r2.pending_action)

            entries = assistant.action_audit_store.recent(limit=10)
            self.assertEqual(len(entries), 2)
            self.assertIn("a.txt", entries[0].description)
            self.assertIn("b.txt", entries[1].description)

    def test_exception_during_execution_is_recorded_as_error_and_still_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            bad_action = PendingAction(
                kind="task_delete", target="not-a-number", description="Delete task not-a-number"
            )

            with self.assertRaises(ValueError):
                assistant.confirm_pending_action(bad_action)

            entries = assistant.action_audit_store.recent()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].status, "error")
            self.assertIn("Unhandled error", entries[0].result)

    def test_sensitive_actions_are_all_recorded(self) -> None:
        """Specifically verify the newer, more consequential action kinds
        from this session (empty trash, bulk commit, notifications) are
        captured, not just the older simple ones.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)

            delete_response = assistant.respond("delete file in docs a.txt")
            assistant.confirm_pending_action(delete_response.pending_action)

            empty_response = assistant.respond("empty trash")
            assistant.confirm_pending_action(empty_response.pending_action)

            entries = assistant.action_audit_store.recent(limit=10)
            kinds = {entry.action_kind for entry in entries}
            self.assertIn("file_delete", kinds)
            self.assertIn("empty_trash", kinds)


if __name__ == "__main__":
    unittest.main()
