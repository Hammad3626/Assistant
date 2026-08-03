import json
import tempfile
import unittest
from pathlib import Path

from assistant.actions import save_allowed_folders
from assistant.file_tools import AllowlistedFileTools, FileToolError, file_tools_help_text


class FileToolsTests(unittest.TestCase):
    def test_lists_reads_and_searches_allowlisted_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "notes.txt").write_text("quiet keyboard\ntea list\n", encoding="utf-8")
            (workspace / "script.py").write_text("print('quiet mode')\n", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(
                folders_path,
                bulk_backup_dir=root / "bulk_backups",
                bulk_approval_dir=root / "bulk_approvals",
                bulk_review_dir=root / "bulk_reviews",
                bulk_rollback_dir=root / "bulk_rollbacks",
                bulk_preflight_dir=root / "bulk_preflights",
                bulk_checklist_dir=root / "bulk_checklists",
            )

            listed = tools.list_files_summary("workspace")
            preview = tools.read_file_summary("workspace", "notes.txt")
            open_preview = tools.open_file_preview_summary("workspace", "notes.txt")
            search = tools.search_files_summary("workspace", "quiet")
            name_search = tools.search_file_names_summary("workspace", "script")
            replace_plan = tools.bulk_replace_plan_summary("workspace", "quiet", "silent")
            rename_plan = tools.bulk_rename_plan_summary("workspace", "notes", "journal")
            replace_apply_plan = tools.bulk_replace_apply_plan_summary("workspace", "quiet", "silent")
            rename_apply_plan = tools.bulk_rename_apply_plan_summary("workspace", "notes", "journal")
            replace_backup = tools.backup_bulk_replace_plan("workspace", "quiet", "silent")
            rename_backup = tools.backup_bulk_rename_plan("workspace", "notes", "journal")
            replace_approval = tools.approve_bulk_replace_plan("workspace", "quiet", "silent", "1, 2")
            rename_approval = tools.approve_bulk_rename_plan("workspace", "notes", "journal", "all")
            review = tools.create_bulk_apply_review()
            rollback = tools.create_bulk_rollback_plan()
            preflight = tools.create_bulk_write_preflight()
            write_checklist = tools.create_bulk_write_operator_checklist()
            restore_checklist = tools.create_bulk_restore_operator_checklist()
            write_verification = tools.verify_bulk_write_operator_checklist()
            restore_verification = tools.verify_bulk_restore_operator_checklist()
            notes_text_after_plan = (workspace / "notes.txt").read_text(encoding="utf-8")
            backup_dirs = sorted((root / "bulk_backups").iterdir())
            approval_dirs = sorted((root / "bulk_approvals").iterdir())
            review_dirs = sorted((root / "bulk_reviews").iterdir())
            rollback_dirs = sorted((root / "bulk_rollbacks").iterdir())
            preflight_dirs = sorted((root / "bulk_preflights").iterdir())
            checklist_dirs = sorted((root / "bulk_checklists").iterdir())
            backup_manifest_exists = [
                (backup_dir / "manifest.json").exists() for backup_dir in backup_dirs
            ]
            backup_manifests = [
                json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
                for backup_dir in backup_dirs
            ]
            backed_up_notes_exists = [
                (backup_dir / "files" / "notes.txt").exists() for backup_dir in backup_dirs
            ]
            approval_manifests = [
                json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
                for approval_dir in approval_dirs
            ]
            review_manifest = json.loads((review.review_dir / "manifest.json").read_text(encoding="utf-8"))
            rollback_manifest = json.loads((rollback.rollback_dir / "manifest.json").read_text(encoding="utf-8"))
            preflight_manifest = json.loads((preflight.preflight_dir / "manifest.json").read_text(encoding="utf-8"))
            write_checklist_manifest = json.loads(write_checklist.manifest_path.read_text(encoding="utf-8"))
            restore_checklist_manifest = json.loads(restore_checklist.manifest_path.read_text(encoding="utf-8"))
            write_checklist_text = write_checklist.checklist_path.read_text(encoding="utf-8")

        self.assertIn("notes.txt", listed)
        self.assertIn("script.py", listed)
        self.assertIn("File preview from workspace: notes.txt", preview)
        self.assertIn("Safe file open preview", open_preview)
        self.assertIn("The file was not launched in Windows", open_preview)
        self.assertIn("quiet keyboard", preview)
        self.assertIn("notes.txt:1", search)
        self.assertIn("script.py:1", search)
        self.assertIn("Filename search results", name_search)
        self.assertIn("script.py", name_search)
        self.assertIn("Bulk replace dry run", replace_plan)
        self.assertIn("No files were changed", replace_plan)
        self.assertIn("notes.txt: 1 replacement(s)", replace_plan)
        self.assertIn("Bulk rename dry run", rename_plan)
        self.assertIn("notes.txt -> journal.txt", rename_plan)
        self.assertIn("Bulk replace apply safety plan", replace_apply_plan)
        self.assertIn("Apply is not enabled in this build", replace_apply_plan)
        self.assertIn("Backup requirement", replace_apply_plan)
        self.assertIn("Per-file approval requirement", replace_apply_plan)
        self.assertIn("Bulk rename apply safety plan", rename_apply_plan)
        self.assertIn("Any rename conflict blocks", rename_apply_plan)
        self.assertIn("Bulk replace backup created", replace_backup)
        self.assertIn("Bulk rename backup created", rename_backup)
        self.assertIn("Hash algorithm: sha256", replace_backup)
        self.assertIn("Bulk replace approval saved", replace_approval)
        self.assertIn("Bulk rename approval saved", rename_approval)
        self.assertIn("Hash algorithm: sha256", replace_approval)
        self.assertIn("Bulk apply review created", review.summary)
        self.assertIn("Review status: review_ready", review.summary)
        self.assertIn("Approved file source hashes match", review.summary)
        self.assertIn("Bulk rollback plan created", rollback.summary)
        self.assertIn("Restore is not enabled", rollback.summary)
        self.assertIn("Bulk write preflight created", preflight.summary)
        self.assertIn("Preflight status: preflight_ready", preflight.summary)
        self.assertIn("Manifest hashes verified", preflight.summary)
        self.assertIn("Signed review metadata", preflight.summary)
        self.assertIn("Bulk write operator checklist created", write_checklist.summary)
        self.assertIn("No files were written", write_checklist.summary)
        self.assertIn("Bulk restore operator checklist created", restore_checklist.summary)
        self.assertIn("No files were written", restore_checklist.summary)
        self.assertEqual(write_verification.status, "verified")
        self.assertIn("Bulk write checklist verification", write_verification.summary)
        self.assertIn("Status: verified", write_verification.summary)
        self.assertIn("Checklist signature matches", write_verification.summary)
        self.assertEqual(restore_verification.status, "verified")
        self.assertIn("Bulk restore checklist verification", restore_verification.summary)
        self.assertIn("Status: verified", restore_verification.summary)
        self.assertIn("Source manifest matches", restore_verification.summary)
        self.assertEqual(len(backup_dirs), 2)
        self.assertEqual(len(approval_dirs), 2)
        self.assertEqual(len(review_dirs), 1)
        self.assertEqual(len(rollback_dirs), 1)
        self.assertEqual(len(preflight_dirs), 1)
        self.assertEqual(len(checklist_dirs), 2)
        self.assertEqual(backup_manifest_exists, [True, True])
        self.assertIn("bulk_replace_backup", {manifest["kind"] for manifest in backup_manifests})
        self.assertTrue(all(manifest["hash_algorithm"] == "sha256" for manifest in backup_manifests))
        self.assertTrue(all("source_sha256" in manifest["files"][0] for manifest in backup_manifests))
        self.assertTrue(all("backup_sha256" in manifest["files"][0] for manifest in backup_manifests))
        self.assertIn("bulk_replace_approval", {manifest["kind"] for manifest in approval_manifests})
        self.assertTrue(all(manifest["hash_algorithm"] == "sha256" for manifest in approval_manifests))
        self.assertTrue(all("source_sha256" in manifest["approved_files"][0] for manifest in approval_manifests))
        self.assertTrue(all(manifest["apply_enabled"] is False for manifest in approval_manifests))
        self.assertEqual(review_manifest["kind"], "bulk_apply_review")
        self.assertFalse(review_manifest["apply_enabled"])
        self.assertIn("manifest_sha256", review_manifest)
        self.assertEqual(rollback_manifest["kind"], "bulk_rollback_plan")
        self.assertFalse(rollback_manifest["restore_enabled"])
        self.assertIn("manifest_sha256", rollback_manifest)
        self.assertIn("backup_sha256", rollback_manifest["rollback_entries"][0])
        self.assertEqual(preflight_manifest["kind"], "bulk_write_preflight")
        self.assertFalse(preflight_manifest["write_enabled"])
        self.assertFalse(preflight_manifest["restore_enabled"])
        self.assertEqual(preflight_manifest["signed_review_metadata"]["schema"], "bulk_write_preflight_review_v1")
        self.assertEqual(preflight_manifest["signed_review_metadata"]["status"], "preflight_ready")
        self.assertFalse(preflight_manifest["signed_review_metadata"]["write_enabled"])
        self.assertFalse(preflight_manifest["signed_review_metadata"]["restore_enabled"])
        self.assertIn("review_signature", preflight_manifest["signed_review_metadata"])
        self.assertIn("manifest_sha256", preflight_manifest)
        self.assertEqual(write_checklist_manifest["schema"], "bulk_operator_checklist_v1")
        self.assertEqual(write_checklist_manifest["operation"], "write")
        self.assertFalse(write_checklist_manifest["write_enabled"])
        self.assertFalse(write_checklist_manifest["restore_enabled"])
        self.assertFalse(write_checklist_manifest["applies_changes"])
        self.assertIn("checklist_signature", write_checklist_manifest)
        self.assertEqual(restore_checklist_manifest["operation"], "restore")
        self.assertIn("# Bulk Operator Checklist", write_checklist_text)
        self.assertTrue(any(backed_up_notes_exists))
        self.assertEqual(notes_text_after_plan, "quiet keyboard\ntea list\n")

    def test_bulk_write_preflight_blocks_when_backup_hash_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "notes.txt").write_text("quiet keyboard\n", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(
                folders_path,
                bulk_backup_dir=root / "bulk_backups",
                bulk_approval_dir=root / "bulk_approvals",
                bulk_review_dir=root / "bulk_reviews",
                bulk_rollback_dir=root / "bulk_rollbacks",
                bulk_preflight_dir=root / "bulk_preflights",
            )

            tools.backup_bulk_replace_plan("workspace", "quiet", "silent")
            tools.approve_bulk_replace_plan("workspace", "quiet", "silent", "1")
            tools.create_bulk_apply_review()
            tools.create_bulk_rollback_plan()
            backup_dir = sorted((root / "bulk_backups").iterdir())[0]
            (backup_dir / "files" / "notes.txt").write_text("changed backup\n", encoding="utf-8")
            preflight = tools.create_bulk_write_preflight()
            preflight_manifest = json.loads((preflight.preflight_dir / "manifest.json").read_text(encoding="utf-8"))

        self.assertIn("Preflight status: blocked", preflight.summary)
        self.assertIn("Backup hash mismatch: notes.txt", preflight.summary)
        self.assertIn("Signed review metadata", preflight.summary)
        self.assertEqual(preflight_manifest["signed_review_metadata"]["status"], "blocked")
        self.assertFalse(preflight_manifest["signed_review_metadata"]["write_enabled"])
        self.assertFalse(preflight_manifest["signed_review_metadata"]["restore_enabled"])
        self.assertIn("review_signature", preflight_manifest["signed_review_metadata"])
        self.assertIn("manifest_sha256", preflight_manifest)
        self.assertEqual(preflight_manifest["status"], "blocked")

    def test_bulk_operator_checklist_verification_blocks_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "notes.txt").write_text("quiet keyboard\n", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(
                folders_path,
                bulk_backup_dir=root / "bulk_backups",
                bulk_approval_dir=root / "bulk_approvals",
                bulk_review_dir=root / "bulk_reviews",
                bulk_rollback_dir=root / "bulk_rollbacks",
                bulk_preflight_dir=root / "bulk_preflights",
                bulk_checklist_dir=root / "bulk_checklists",
            )

            tools.backup_bulk_replace_plan("workspace", "quiet", "silent")
            tools.approve_bulk_replace_plan("workspace", "quiet", "silent", "1")
            tools.create_bulk_apply_review()
            tools.create_bulk_rollback_plan()
            tools.create_bulk_write_preflight()
            checklist = tools.create_bulk_write_operator_checklist()
            manifest_path = checklist.manifest_path
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["operation"] = "restore"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            verification = tools.verify_bulk_write_operator_checklist()

        self.assertEqual(verification.status, "blocked")
        self.assertIn("Status: blocked", verification.summary)
        self.assertIn("Checklist signature mismatch", verification.summary)

    def test_bulk_plans_skip_generated_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            export_dir = workspace / "exports" / "bulk-file-backups"
            export_dir.mkdir(parents=True)
            (workspace / "notes.txt").write_text("quiet keyboard\n", encoding="utf-8")
            (export_dir / "copy.txt").write_text("quiet backup\n", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path)

            plan = tools.bulk_replace_plan_summary("workspace", "quiet", "silent")

        self.assertIn("notes.txt: 1 replacement(s)", plan)
        self.assertNotIn("exports/", plan)

    def test_bulk_apply_safety_text_is_plan_only(self) -> None:
        text = AllowlistedFileTools.bulk_apply_safety_text()

        self.assertIn("Bulk apply safety", text)
        self.assertIn("Apply is not enabled in this build", text)
        self.assertIn("Backup requirement", text)
        self.assertIn("Per-file approval requirement", text)
        self.assertIn("bulk replace apply plan", text)

    def test_bulk_write_and_restore_designs_are_design_only(self) -> None:
        write_text = AllowlistedFileTools.bulk_write_command_design_text()
        restore_text = AllowlistedFileTools.bulk_restore_command_design_text()

        self.assertIn("Confirmed bulk write command design", write_text)
        self.assertIn("No files are written", write_text)
        self.assertIn("confirm bulk write", write_text)
        self.assertIn("source hash and size", write_text)
        self.assertIn("Confirmed bulk restore command design", restore_text)
        self.assertIn("No files are restored", restore_text)
        self.assertIn("confirm bulk restore", restore_text)
        self.assertIn("backup hash and size", restore_text)

    def test_bulk_rename_plan_reports_conflicts_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "notes.txt").write_text("first\n", encoding="utf-8")
            (workspace / "journal.txt").write_text("second\n", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path)

            plan = tools.bulk_rename_plan_summary("workspace", "notes", "journal")
            with self.assertRaises(FileToolError):
                tools.backup_bulk_rename_plan("workspace", "notes", "journal")
            with self.assertRaises(FileToolError):
                tools.approve_bulk_rename_plan("workspace", "notes", "journal", "all")
            notes_exists = (workspace / "notes.txt").exists()
            journal_exists = (workspace / "journal.txt").exists()

        self.assertIn("conflict: target already exists", plan)
        self.assertTrue(notes_exists)
        self.assertTrue(journal_exists)

    def test_bulk_preview_rejects_empty_or_unsafe_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path)

            with self.assertRaises(FileToolError):
                tools.bulk_replace_plan_summary("workspace", "", "new")
            with self.assertRaises(FileToolError):
                tools.bulk_rename_plan_summary("workspace", "old", "../new")
            with self.assertRaises(FileToolError):
                tools.approve_bulk_replace_plan("workspace", "", "new", "1")

    def test_rejects_paths_outside_allowlisted_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "secret.txt"
            outside.write_text("private", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path)

            with self.assertRaises(FileToolError):
                tools.read_file_summary("workspace", "../secret.txt")

            with self.assertRaises(FileToolError):
                tools.open_file_preview_summary("workspace", "../secret.txt")

    def test_rejects_non_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "image.png").write_bytes(b"\x89PNG\r\n")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path)

            with self.assertRaises(FileToolError):
                tools.read_file_summary("workspace", "image.png")

    def test_parse_read_request_uses_longest_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            folders_path = root / "folders.json"
            save_allowed_folders({"project": str(project), "project folder": str(project)}, folders_path)
            tools = AllowlistedFileTools(folders_path)

            folder_name, relative_path = tools.parse_read_request("project folder README.md")

        self.assertEqual(folder_name, "project folder")
        self.assertEqual(relative_path, "README.md")

    def test_help_lists_allowed_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)

            text = file_tools_help_text(folders_path)

        self.assertIn("Safe file tools", text)
        self.assertIn("workspace", text)
        self.assertIn("launch file in <folder> <relative path>", text)
        self.assertIn("trust file type revocation <extension>", text)

    def test_moves_file_to_trash_and_restores_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "notes.txt"
            target.write_text("quiet keyboard\n", encoding="utf-8")
            trash_dir = root / "trash"
            manifest_path = root / "manifest.json"
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path, trash_dir=trash_dir, manifest_path=manifest_path)

            entry = tools.move_file_to_trash("workspace", "notes.txt")
            trash_summary = tools.file_trash_summary()
            self.assertFalse(target.exists())
            restored = tools.restore_file_from_trash(1)
            self.assertTrue(target.exists())
            restored_text = target.read_text(encoding="utf-8")

        self.assertEqual(entry.display_text(), "workspace/notes.txt")
        self.assertIn("File trash:", trash_summary)
        self.assertEqual(restored.display_text(), "workspace/notes.txt")
        self.assertEqual(restored_text, "quiet keyboard\n")

    def test_rejects_trashing_paths_outside_allowlisted_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "secret.txt"
            outside.write_text("private", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path, trash_dir=root / "trash", manifest_path=root / "manifest.json")

            with self.assertRaises(FileToolError):
                tools.move_file_to_trash("workspace", "../secret.txt")

    def test_rejects_trashing_non_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "image.png").write_bytes(b"\x89PNG\r\n")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path, trash_dir=root / "trash", manifest_path=root / "manifest.json")

            with self.assertRaises(FileToolError):
                tools.move_file_to_trash("workspace", "image.png")

    def test_restore_refuses_to_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "notes.txt"
            target.write_text("first\n", encoding="utf-8")
            folders_path = root / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            tools = AllowlistedFileTools(folders_path, trash_dir=root / "trash", manifest_path=root / "manifest.json")
            tools.move_file_to_trash("workspace", "notes.txt")
            target.write_text("replacement\n", encoding="utf-8")

            with self.assertRaises(FileToolError):
                tools.restore_file_from_trash(1)


if __name__ == "__main__":
    unittest.main()
