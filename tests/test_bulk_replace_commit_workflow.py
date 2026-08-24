"""Tests for the real bulk-replace commit and rollback workflow.

Key invariants under test:
- Commit is impossible without a matching, hash-intact prior backup.
- Commit requires an exact confirmation phrase computed fresh from the live
  plan (proving the operator read and understood the scope).
- Commit refuses if live files have drifted from what was backed up.
- Every commit remains reversible via rollback, which restores original
  content and verifies backup integrity before restoring.
- Double-apply and double-rollback are both rejected.
- The confirmation-phrase gate fails fast (no pending action created) before
  offering the standard 'yes' confirmation step.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistant.actions import save_allowed_folders
from assistant.core import LocalAssistant
from assistant.file_tools import AllowlistedFileTools, FileToolError


class BulkReplaceCommitUnitTests(unittest.TestCase):
    def _tools(self, temp_dir: str) -> tuple[AllowlistedFileTools, Path]:
        root = Path(temp_dir)
        source = root / "docs"
        source.mkdir()
        (source / "a.txt").write_text("hello world hello", encoding="utf-8")
        (source / "b.txt").write_text("hello there", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"docs": str(source)}, folders_path)
        tools = AllowlistedFileTools(
            folders_path=folders_path,
            trash_dir=root / "trash",
            manifest_path=root / "trash-manifest.json",
            bulk_backup_dir=root / "bulk-backups",
            bulk_approval_dir=root / "bulk-approvals",
            bulk_review_dir=root / "bulk-reviews",
            bulk_rollback_dir=root / "bulk-rollbacks",
            bulk_preflight_dir=root / "bulk-preflights",
            bulk_checklist_dir=root / "bulk-checklists",
        )
        return tools, source

    def test_commit_blocked_without_prior_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            with self.assertRaises(FileToolError):
                tools.commit_bulk_replace_plan("docs", "hello", "goodbye", "apply 2 files in docs")

    def test_commit_blocked_with_wrong_confirmation_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")
            with self.assertRaises(FileToolError) as ctx:
                tools.commit_bulk_replace_plan("docs", "hello", "goodbye", "not the right phrase")
            self.assertIn("Confirmation phrase did not match", str(ctx.exception))

    def test_required_phrase_reflects_actual_file_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            phrase = tools.bulk_replace_required_confirmation_phrase("docs", "hello", "goodbye")
            self.assertEqual(phrase, "apply 2 files in docs")

    def test_commit_succeeds_with_correct_phrase_and_writes_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")
            phrase = tools.bulk_replace_required_confirmation_phrase("docs", "hello", "goodbye")

            result = tools.commit_bulk_replace_plan("docs", "hello", "goodbye", phrase)

            self.assertIn("Applied bulk replace to 2 file(s)", result)
            self.assertEqual((source / "a.txt").read_text(encoding="utf-8"), "goodbye world goodbye")
            self.assertEqual((source / "b.txt").read_text(encoding="utf-8"), "goodbye there")

    def test_commit_blocked_on_double_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")
            phrase = tools.bulk_replace_required_confirmation_phrase("docs", "hello", "goodbye")
            tools.commit_bulk_replace_plan("docs", "hello", "goodbye", phrase)

            with self.assertRaises(FileToolError) as ctx:
                tools.commit_bulk_replace_plan("docs", "hello", "goodbye", phrase)
            self.assertIn("already been applied", str(ctx.exception))

    def test_commit_blocked_when_file_drifted_since_backup(self) -> None:
        """Regression test: if a file changes after the backup was taken but
        before commit, the commit must refuse rather than apply blindly --
        and must not modify the drifted file at all.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")

            (source / "a.txt").write_text("hello world -- edited externally!", encoding="utf-8")

            phrase = tools.bulk_replace_required_confirmation_phrase("docs", "hello", "goodbye")
            with self.assertRaises(FileToolError) as ctx:
                tools.commit_bulk_replace_plan("docs", "hello", "goodbye", phrase)
            self.assertIn("changed since backup", str(ctx.exception))
            # The drifted file must be untouched by the failed commit attempt.
            self.assertEqual(
                (source / "a.txt").read_text(encoding="utf-8"), "hello world -- edited externally!"
            )

    def test_rollback_restores_original_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")
            phrase = tools.bulk_replace_required_confirmation_phrase("docs", "hello", "goodbye")
            tools.commit_bulk_replace_plan("docs", "hello", "goodbye", phrase)

            result = tools.rollback_bulk_replace_commit()

            self.assertIn("Rolled back 2 file(s)", result)
            self.assertEqual((source / "a.txt").read_text(encoding="utf-8"), "hello world hello")
            self.assertEqual((source / "b.txt").read_text(encoding="utf-8"), "hello there")

    def test_rollback_blocked_if_never_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")

            with self.assertRaises(FileToolError) as ctx:
                tools.rollback_bulk_replace_commit()
            self.assertIn("never applied", str(ctx.exception))

    def test_rollback_blocked_on_double_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, _source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")
            phrase = tools.bulk_replace_required_confirmation_phrase("docs", "hello", "goodbye")
            tools.commit_bulk_replace_plan("docs", "hello", "goodbye", phrase)
            tools.rollback_bulk_replace_commit()

            with self.assertRaises(FileToolError) as ctx:
                tools.rollback_bulk_replace_commit()
            self.assertIn("already been rolled back", str(ctx.exception))

    def test_validate_bulk_replace_commit_is_side_effect_free(self) -> None:
        """The eager validation helper must never write to disk, so it's
        safe to call before offering a confirmation prompt.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            tools, source = self._tools(temp_dir)
            tools.backup_bulk_replace_plan("docs", "hello", "goodbye")
            phrase = tools.bulk_replace_required_confirmation_phrase("docs", "hello", "goodbye")
            before = (source / "a.txt").read_text(encoding="utf-8")

            tools.validate_bulk_replace_commit("docs", "hello", "goodbye", phrase)

            after = (source / "a.txt").read_text(encoding="utf-8")
            self.assertEqual(before, after)


class BulkReplaceCommitCoreWorkflowTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> tuple[LocalAssistant, Path]:
        root = Path(temp_dir)
        source = root / "docs"
        source.mkdir()
        (source / "a.txt").write_text("hello world", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"docs": str(source)}, folders_path)
        assistant = LocalAssistant(
            use_llm=False,
            folders_path=folders_path,
            data_export_dir=root / "exports",
        )
        return assistant, source

    def test_commit_command_fails_fast_without_backup_no_pending_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            response = assistant.respond(
                "commit bulk replace in docs find hello with goodbye confirm apply 1 files in docs"
            )
            self.assertIsNone(response.pending_action)
            self.assertIn("File tools error", response.text)

    def test_commit_command_fails_fast_with_wrong_phrase_no_pending_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            assistant.respond("backup bulk replace in docs find hello with goodbye")

            response = assistant.respond(
                "commit bulk replace in docs find hello with goodbye confirm nonsense phrase"
            )
            self.assertIsNone(response.pending_action)
            self.assertIn("did not match", response.text)

    def test_commit_end_to_end_then_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, source = self._make_assistant(temp_dir)
            assistant.respond("backup bulk replace in docs find hello with goodbye")

            response = assistant.respond(
                "commit bulk replace in docs find hello with goodbye confirm apply 1 files in docs"
            )
            self.assertIsNotNone(response.pending_action)
            assert response.pending_action is not None
            self.assertEqual(response.pending_action.kind, "commit_bulk_replace")

            result = assistant.confirm_pending_action(response.pending_action)
            self.assertIn("Applied bulk replace to 1 file(s)", result)
            self.assertEqual((source / "a.txt").read_text(encoding="utf-8"), "goodbye world")

            rollback_response = assistant.respond("rollback bulk replace")
            self.assertIsNotNone(rollback_response.pending_action)
            assert rollback_response.pending_action is not None
            self.assertEqual(rollback_response.pending_action.kind, "rollback_bulk_replace")

            rollback_result = assistant.confirm_pending_action(rollback_response.pending_action)
            self.assertIn("Rolled back 1 file(s)", rollback_result)
            self.assertEqual((source / "a.txt").read_text(encoding="utf-8"), "hello world")

    def test_commit_never_writes_files_before_final_yes_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, source = self._make_assistant(temp_dir)
            assistant.respond("backup bulk replace in docs find hello with goodbye")

            assistant.respond(
                "commit bulk replace in docs find hello with goodbye confirm apply 1 files in docs"
            )
            # Only respond() was called (no confirm_pending_action yet) --
            # the file must still be untouched.
            self.assertEqual((source / "a.txt").read_text(encoding="utf-8"), "hello world")

    def test_malformed_commit_command_gives_helpful_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant, _source = self._make_assistant(temp_dir)
            response = assistant.respond("commit bulk replace in docs missing keywords")
            self.assertIsNone(response.pending_action)
            self.assertIn("commit bulk replace in <folder>", response.text)


if __name__ == "__main__":
    unittest.main()
