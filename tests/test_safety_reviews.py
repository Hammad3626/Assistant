import json
import tempfile
import unittest
from pathlib import Path

from assistant.actions import save_allowed_folders
from assistant.file_tools import AllowlistedFileTools
from assistant.launch_requests import LaunchRequestStore
from assistant.safety_reviews import export_safety_reviews, safety_review_export_summary
from assistant.shell_tools import add_shell_command


class SafetyReviewExportTests(unittest.TestCase):
    def test_exports_shell_and_bulk_signed_reviews_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "notes.txt").write_text("quiet keyboard\n", encoding="utf-8")
            folders_path = root / "folders.json"
            shell_commands_path = root / "shell_commands.json"
            launch_requests_path = root / "launch_requests.json"
            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            add_shell_command("python check", ["python", "--version"], shell_commands_path)
            script = root / "cleanup.py"
            script.write_text("print('review only')\n", encoding="utf-8")
            launch_requests = LaunchRequestStore(launch_requests_path)
            launch_requests.request_script_review("cleanup", str(script))
            launch_requests.create_script_review_checklist(
                1,
                output_dir=root / "exports" / "script-review-checklists",
            )
            launch_requests.create_script_allowlist_preflight(
                1,
                checklist_dir=root / "exports" / "script-review-checklists",
                output_dir=root / "exports" / "script-allowlist-preflights",
            )

            tools = AllowlistedFileTools(
                folders_path,
                bulk_backup_dir=root / "exports" / "bulk-file-backups",
                bulk_approval_dir=root / "exports" / "bulk-file-approvals",
                bulk_review_dir=root / "exports" / "bulk-apply-reviews",
                bulk_rollback_dir=root / "exports" / "bulk-rollback-plans",
                bulk_preflight_dir=root / "exports" / "bulk-write-preflights",
            )
            tools.backup_bulk_replace_plan("workspace", "quiet", "silent")
            tools.approve_bulk_replace_plan("workspace", "quiet", "silent", "1")
            tools.create_bulk_apply_review()
            tools.create_bulk_rollback_plan()
            tools.create_bulk_write_preflight()

            export_dir = export_safety_reviews(
                shell_commands_path=shell_commands_path,
                bulk_preflight_dir=root / "exports" / "bulk-write-preflights",
                launch_requests_path=launch_requests_path,
                script_checklist_dir=root / "exports" / "script-review-checklists",
                script_preflight_dir=root / "exports" / "script-allowlist-preflights",
                output_dir=root / "exports" / "safety-review-exports",
            )
            summary = safety_review_export_summary(export_dir)
            manifest = json.loads((export_dir / "safety_reviews.json").read_text(encoding="utf-8"))

        self.assertIn("Signed safety review export created", summary)
        self.assertIn("No commands were run", summary)
        self.assertEqual(manifest["kind"], "safety_review_export")
        self.assertEqual(manifest["shell_review_count"], 1)
        self.assertEqual(manifest["bulk_preflight_review_count"], 1)
        self.assertEqual(manifest["script_review_count"], 1)
        self.assertEqual(manifest["script_checklist_review_count"], 1)
        self.assertEqual(manifest["script_preflight_review_count"], 1)
        self.assertTrue(manifest["records"]["shell_reviews"][0]["signature_valid"])
        self.assertTrue(manifest["records"]["bulk_preflight_reviews"][0]["signature_valid"])
        self.assertTrue(manifest["records"]["script_reviews"][0]["signature_valid"])
        self.assertTrue(manifest["records"]["script_checklist_reviews"][0]["signature_valid"])
        self.assertTrue(manifest["records"]["script_preflight_reviews"][0]["signature_valid"])
        self.assertFalse(manifest["records"]["script_reviews"][0]["runs_script"])
        self.assertFalse(manifest["records"]["script_checklist_reviews"][0]["runs_script"])
        self.assertFalse(manifest["records"]["script_preflight_reviews"][0]["runs_script"])
        self.assertIn("export_signature", manifest)


if __name__ == "__main__":
    unittest.main()
