import json
import tempfile
import unittest
from pathlib import Path

from assistant.launch_requests import LaunchRequestStore
from assistant.safety_snapshot import safety_snapshot_text
from assistant.shell_tools import add_shell_command, remove_shell_command


class SafetySnapshotTests(unittest.TestCase):
    def test_summarizes_launch_requests_and_shell_reviews_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requests = LaunchRequestStore(root / "launch_requests.json")
            requests.request_app("paint", "mspaint.exe")
            requests.request_script_review("cleanup", "tools/cleanup.py")
            shell_commands_path = root / "shell_commands.json"
            add_shell_command("python check", ["python", "--version"], shell_commands_path)
            remove_shell_command("python check", shell_commands_path)

            text = safety_snapshot_text(requests, shell_commands_path)

        self.assertIn("Safety snapshot", text)
        self.assertIn("Read-only", text)
        self.assertIn("Launch review requests: 2", text)
        self.assertIn("Shell allowlist review records: 2", text)
        self.assertIn("signature valid", text)
        self.assertIn("No apps, scripts, files, folders, or shell commands were opened or run", text)
        self.assertIn("running still requires run shell <name> and confirmation", text)

    def test_empty_snapshot_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            text = safety_snapshot_text(
                LaunchRequestStore(root / "launch_requests.json"),
                root / "shell_commands.json",
            )

        self.assertIn("Launch review requests: 0", text)
        self.assertIn("Shell allowlist review records: 0", text)
        self.assertIn("None saved", text)

    def test_can_filter_snapshot_by_review_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requests = LaunchRequestStore(root / "launch_requests.json")
            requests.request_app("paint", "mspaint.exe")
            requests.request_script_review("cleanup", "tools/cleanup.py")
            shell_commands_path = root / "shell_commands.json"
            add_shell_command("python check", ["python", "--version"], shell_commands_path)

            launch_text = safety_snapshot_text(requests, shell_commands_path, review_type="launch")
            shell_text = safety_snapshot_text(requests, shell_commands_path, review_type="shell")
            script_text = safety_snapshot_text(
                requests,
                shell_commands_path,
                review_type="scripts",
                script_checklist_dir=root / "script-checklists",
            )

        self.assertIn("Safety snapshot: launch requests", launch_text)
        self.assertIn("Launch review requests: 2", launch_text)
        self.assertNotIn("Shell allowlist review records", launch_text)
        self.assertIn("Safety snapshot: shell reviews", shell_text)
        self.assertIn("Shell allowlist review records: 1", shell_text)
        self.assertNotIn("Launch review requests", shell_text)
        self.assertIn("Safety snapshot: script reviews", script_text)
        self.assertIn("Script review requests: 1", script_text)
        self.assertIn("1. cleanup -> tools/cleanup.py", script_text)
        self.assertIn("checklist: missing; verification: blocked", script_text)
        self.assertIn("Use script review checklist <number>", script_text)
        self.assertNotIn("Launch review requests", script_text)
        self.assertNotIn("Shell allowlist review records", script_text)

    def test_script_snapshot_reports_verified_checklist_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            script.write_text("print('review only')\n", encoding="utf-8")
            requests = LaunchRequestStore(root / "launch_requests.json")
            requests.request_script_review("cleanup", str(script))
            requests.create_script_review_checklist(1, output_dir=root / "script-checklists")

            text = safety_snapshot_text(
                requests,
                root / "shell_commands.json",
                review_type="scripts",
                script_checklist_dir=root / "script-checklists",
            )

        self.assertIn("Safety snapshot: script reviews", text)
        self.assertIn("checklist: verified", text)
        self.assertIn("script-checklist-cleanup", text)

    def test_drift_threshold_filters_by_active_warning_type_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checklist_dir = root / "script-checklists"
            preflight_dir = root / "script-preflights"
            readiness_dir = root / "script-readiness"
            run_simulation_dir = root / "script-run-simulations"
            allowlist_simulation_dir = root / "script-allowlist-simulations"
            requests = LaunchRequestStore(root / "launch_requests.json")

            # Request 1: only the script content changes after readiness, so just a hash mismatch.
            hash_only_script = root / "hash_only.py"
            hash_only_script.write_text("print('hash only')\n", encoding="utf-8")
            requests.request_script_review("hash-only", str(hash_only_script))
            requests.create_script_review_checklist(1, output_dir=checklist_dir)
            requests.create_script_allowlist_preflight(1, checklist_dir=checklist_dir, output_dir=preflight_dir)
            requests.create_script_execution_readiness_bundle(
                1, checklist_dir=checklist_dir, preflight_dir=preflight_dir, output_dir=readiness_dir
            )
            hash_only_script.write_text("print('hash only changed')\n", encoding="utf-8")
            requests.simulate_confirmed_script_run(
                1, "confirm script run", readiness_dir=readiness_dir, output_dir=run_simulation_dir
            )
            requests.simulate_script_allowlist_entry(
                1, "python --version", readiness_dir=readiness_dir, output_dir=allowlist_simulation_dir
            )

            # Request 2: readiness metadata is also tampered, triggering signature, hash, and path warnings.
            full_drift_script = root / "full_drift.py"
            full_drift_script.write_text("print('full drift')\n", encoding="utf-8")
            requests.request_script_review("full-drift", str(full_drift_script))
            requests.create_script_review_checklist(2, output_dir=checklist_dir)
            requests.create_script_allowlist_preflight(2, checklist_dir=checklist_dir, output_dir=preflight_dir)
            requests.create_script_execution_readiness_bundle(
                2, checklist_dir=checklist_dir, preflight_dir=preflight_dir, output_dir=readiness_dir
            )
            readiness_manifest_path = sorted(
                readiness_dir.glob("script-execution-readiness-full-drift-*/manifest.json")
            )[-1]
            readiness_manifest = json.loads(readiness_manifest_path.read_text(encoding="utf-8-sig"))
            readiness_manifest["static_metadata"]["path"] = str(root / "tampered.py")
            readiness_manifest_path.write_text(json.dumps(readiness_manifest, indent=2) + "\n", encoding="utf-8")
            full_drift_script.write_text("print('full drift changed')\n", encoding="utf-8")
            requests.simulate_confirmed_script_run(
                2, "confirm script run", readiness_dir=readiness_dir, output_dir=run_simulation_dir
            )
            requests.simulate_script_allowlist_entry(
                2, "python --version", readiness_dir=readiness_dir, output_dir=allowlist_simulation_dir
            )

            all_drift_text = safety_snapshot_text(
                requests,
                root / "shell_commands.json",
                review_type="scripts-drift",
                script_execution_readiness_dir=readiness_dir,
                script_run_simulation_dir=run_simulation_dir,
                script_allowlist_simulation_dir=allowlist_simulation_dir,
            )
            threshold_text = safety_snapshot_text(
                requests,
                root / "shell_commands.json",
                review_type="scripts-drift",
                script_execution_readiness_dir=readiness_dir,
                script_run_simulation_dir=run_simulation_dir,
                script_allowlist_simulation_dir=allowlist_simulation_dir,
                drift_warning_threshold=2,
            )

        self.assertIn("Script requests with drift warnings: 2", all_drift_text)
        self.assertIn("hash-only", all_drift_text)
        self.assertIn("full-drift", all_drift_text)
        self.assertIn("Script requests with drift warnings (>= 2 warning type(s)): 1", threshold_text)
        self.assertNotIn("hash-only", threshold_text)
        self.assertIn("full-drift", threshold_text)


if __name__ == "__main__":
    unittest.main()
