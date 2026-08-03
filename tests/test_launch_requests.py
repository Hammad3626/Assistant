import tempfile
import unittest
import json
from pathlib import Path

from assistant.launch_requests import LaunchRequestError, LaunchRequestStore, blocked_unlisted_launch_text


class LaunchRequestTests(unittest.TestCase):
    def test_app_request_is_saved_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LaunchRequestStore(Path(temp_dir) / "launch_requests.json")

            request = store.request_app("paint", "mspaint.exe", "trusted Windows app")
            summary = store.summary()

        self.assertEqual(request.kind, "app")
        self.assertIn("app 'paint' -> mspaint.exe", summary)
        self.assertIn("local review only", summary)

    def test_script_review_request_is_saved_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LaunchRequestStore(Path(temp_dir) / "launch_requests.json")

            request = store.request_script_review("cleanup", "tools/cleanup.py")

        self.assertEqual(request.kind, "script")
        self.assertIn("cleanup.py", request.display_text())
        self.assertEqual(request.script_review_risk, "unknown")
        self.assertIn("file was not found for inspection", request.script_review_summary)
        self.assertIn("static-review", request.display_text())

    def test_script_review_summarizes_existing_script_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            marker = root / "should_not_exist.txt"
            script.write_text(
                "import os\n"
                f"os.system('echo unsafe > {marker}')\n"
                "print('review only')\n",
                encoding="utf-8",
            )
            store = LaunchRequestStore(root / "launch_requests.json")

            request = store.request_script_review("cleanup", str(script))
            saved = store.list_requests()[0]

        self.assertFalse(marker.exists())
        self.assertEqual(request.script_review_risk, "high")
        self.assertIn("read-only static inspection", request.script_review_summary)
        self.assertIn("shell or process launch", request.script_review_summary)
        self.assertIn("lines 3", request.script_review_summary)
        self.assertEqual(saved.script_review_summary, request.script_review_summary)

    def test_script_review_checklist_manifest_is_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            marker = root / "should_not_exist.txt"
            script.write_text(
                f"print('review only, no write to {marker}')\n",
                encoding="utf-8",
            )
            store = LaunchRequestStore(root / "launch_requests.json")
            store.request_script_review("cleanup", str(script))

            result = store.create_script_review_checklist(1, output_dir=root / "checklists")
            verification = store.verify_script_review_checklist(1, output_dir=root / "checklists")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            checklist_text = result.checklist_path.read_text(encoding="utf-8")

        self.assertFalse(marker.exists())
        self.assertIn("Script operator checklist created", result.summary)
        self.assertIn("No script was run", result.summary)
        self.assertEqual(manifest["schema"], "script_review_operator_checklist_v1")
        self.assertFalse(manifest["execution_enabled"])
        self.assertFalse(manifest["runs_script"])
        self.assertFalse(manifest["allowlist_enabled"])
        self.assertEqual(manifest["static_metadata"]["hash_status"], "recorded")
        self.assertIn("checklist_signature", manifest)
        self.assertIn("# Script Operator Checklist", checklist_text)
        self.assertIn("Status: verified", verification.summary)
        self.assertIn("does not grant permission", verification.summary)

    def test_script_review_checklist_numbers_are_script_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            script.write_text("print('review only')\n", encoding="utf-8")
            store = LaunchRequestStore(root / "launch_requests.json")
            store.request_app("paint", "mspaint.exe")
            store.request_script_review("cleanup", str(script))

            result = store.create_script_review_checklist(1, output_dir=root / "checklists")
            verification = store.verify_script_review_checklist(1, output_dir=root / "checklists")

        self.assertIn("script 'cleanup'", result.summary)
        self.assertIn("Status: verified", verification.summary)

    def test_script_review_checklist_verification_blocks_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            script.write_text("print('review only')\n", encoding="utf-8")
            store = LaunchRequestStore(root / "launch_requests.json")
            store.request_script_review("cleanup", str(script))
            result = store.create_script_review_checklist(1, output_dir=root / "checklists")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            manifest["runs_script"] = True
            result.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            verification = store.verify_script_review_checklist(1, output_dir=root / "checklists")

        self.assertIn("Status: blocked", verification.summary)
        self.assertIn("runs_script", verification.summary)

    def test_script_allowlist_preflight_is_review_only_and_signed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            marker = root / "should_not_exist.txt"
            script.write_text(
                f"print('review only, no write to {marker}')\n",
                encoding="utf-8",
            )
            store = LaunchRequestStore(root / "launch_requests.json")
            store.request_script_review("cleanup", str(script))
            store.create_script_review_checklist(1, output_dir=root / "checklists")

            result = store.create_script_allowlist_preflight(
                1,
                checklist_dir=root / "checklists",
                output_dir=root / "preflights",
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

        self.assertFalse(marker.exists())
        self.assertIn("Script allowlist preflight created", result.summary)
        self.assertIn("Preflight status: preflight_ready", result.summary)
        self.assertEqual(result.status, "preflight_ready")
        self.assertEqual(manifest["schema"], "script_allowlist_preflight_v1")
        self.assertEqual(manifest["status"], "preflight_ready")
        self.assertFalse(manifest["execution_enabled"])
        self.assertFalse(manifest["runs_script"])
        self.assertFalse(manifest["allowlist_enabled"])
        self.assertEqual(manifest["static_metadata"]["hash_status"], "recorded")
        self.assertIn("preflight_signature", manifest)

    def test_script_allowlist_preflight_blocks_without_verified_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            script.write_text("print('review only')\n", encoding="utf-8")
            store = LaunchRequestStore(root / "launch_requests.json")
            store.request_script_review("cleanup", str(script))

            result = store.create_script_allowlist_preflight(
                1,
                checklist_dir=root / "missing-checklists",
                output_dir=root / "preflights",
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

        self.assertIn("Preflight status: blocked", result.summary)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(manifest["status"], "blocked")
        self.assertFalse(manifest["allowlist_enabled"])

    def test_file_and_folder_review_requests_are_saved_without_opening(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "report.pdf"
            document.write_text("local test", encoding="utf-8")
            folder = root / "archive"
            folder.mkdir()
            store = LaunchRequestStore(
                root / "launch_requests.json",
                file_type_allowlist_path=root / "file_types.json",
            )

            file_request = store.request_file_review("report", str(document))
            folder_request = store.request_folder_review("archive", str(folder))
            summary = store.summary()

        self.assertEqual(file_request.kind, "file")
        self.assertEqual(folder_request.kind, "folder")
        self.assertIn("document (.pdf)", file_request.file_type_category)
        self.assertEqual(file_request.file_type_extension, ".pdf")
        self.assertFalse(file_request.file_type_allowed_for_launch)
        self.assertEqual(file_request.file_type_risk, "medium")
        self.assertIn("read-only", file_request.file_type_note)
        self.assertIn("not allowlisted", file_request.file_type_note)
        self.assertIn("file-type:", file_request.display_text())
        self.assertIn("launch-eligible: no", file_request.display_text())
        self.assertIn("file 'report'", summary)
        self.assertIn("folder 'archive'", summary)

    def test_file_review_can_be_marked_launch_eligible_via_explicit_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "report.pdf"
            document.write_text("local test", encoding="utf-8")
            store = LaunchRequestStore(
                root / "launch_requests.json",
                file_type_allowlist_path=root / "file_types.json",
            )

            store.file_type_allowlist.allow_extension(".pdf")
            request = store.request_file_review("report", str(document))

        self.assertTrue(request.file_type_allowed_for_launch)
        self.assertIn("allowlisted", request.file_type_note)
        self.assertIn("launch-eligible: yes", request.display_text())

    def test_file_review_detects_high_risk_executable_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "tool.exe"
            executable.write_text("placeholder", encoding="utf-8")
            store = LaunchRequestStore(
                root / "launch_requests.json",
                file_type_allowlist_path=root / "file_types.json",
            )

            request = store.request_file_review("tool", str(executable))

        self.assertEqual(request.kind, "file")
        self.assertIn("executable (.exe)", request.file_type_category)
        self.assertEqual(request.file_type_risk, "high")
        self.assertIn("blocked", request.file_type_note)

    def test_rejects_shell_executables_and_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LaunchRequestStore(Path(temp_dir) / "launch_requests.json")

            with self.assertRaises(LaunchRequestError):
                store.request_app("shell", "powershell.exe")

            with self.assertRaises(LaunchRequestError):
                store.request_script_review("bad", "tools/run.py;calc.exe")

            with self.assertRaises(LaunchRequestError):
                store.request_file_review("missing", str(Path(temp_dir) / "missing.pdf"))

    def test_blocked_launch_text_points_to_review_requests(self) -> None:
        text = blocked_unlisted_launch_text()

        self.assertIn("Unlisted apps, scripts, files, and folders cannot open", text)
        self.assertIn("request app", text)


if __name__ == "__main__":
    unittest.main()
