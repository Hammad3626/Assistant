import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from assistant.shell_tools import (
    ShellToolError,
    add_shell_command,
    create_shell_review_checklist,
    get_shell_command,
    latest_shell_review_metadata,
    load_shell_commands,
    parse_shell_command_request,
    remove_shell_command,
    run_shell_command,
    save_shell_commands,
    shell_command_risk_profile,
    shell_command_signed_review_text,
    shell_command_static_review_notes,
    shell_command_wizard_text,
    shell_commands_summary,
    verify_shell_review_checklist,
)


class ShellToolsTests(unittest.TestCase):
    def test_loads_named_safe_shell_commands(self) -> None:
        commands = load_shell_commands()

        self.assertIn("python version", commands)
        self.assertEqual(commands["python version"].argv, ("python", "--version"))

    def test_summary_lists_safe_commands(self) -> None:
        text = shell_commands_summary()

        self.assertIn("Safe shell commands", text)
        self.assertIn("python version", text)

    def test_rejects_shell_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shell_commands.json"
            path.write_text(
                '{"commands": {"bad": ["powershell.exe", "-Command", "Get-ChildItem"]}}',
                encoding="utf-8",
            )

            with self.assertRaises(ShellToolError):
                load_shell_commands(path)

    def test_rejects_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shell_commands.json"
            path.write_text(
                '{"commands": {"bad": ["python", "--version", "&&", "del"]}}',
                encoding="utf-8",
            )

            with self.assertRaises(ShellToolError):
                load_shell_commands(path)

    def test_rejects_inline_python_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shell_commands.json"
            path.write_text(
                '{"commands": {"bad": ["python", "-c", "print(1)"]}}',
                encoding="utf-8",
            )

            with self.assertRaises(ShellToolError):
                load_shell_commands(path)

    def test_add_shell_command_saves_valid_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shell_commands.json"

            command = add_shell_command("Python Version", ["python", "--version"], path)
            commands = load_shell_commands(path)
            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(command.name, "python version")
        self.assertIn("python version", commands)
        self.assertEqual(commands["python version"].argv, ("python", "--version"))
        self.assertEqual(raw["reviews"][0]["action"], "add")
        self.assertEqual(raw["reviews"][0]["command_name"], "python version")
        self.assertEqual(raw["reviews"][0]["static_risk"]["level"], "low")
        self.assertIn("review_signature", raw["reviews"][0])

    def test_save_shell_commands_validates_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shell_commands.json"

            save_shell_commands({"python version": get_shell_command("python version")}, path)
            text = shell_commands_summary(path)

        self.assertIn("python version", text)

    def test_parse_shell_command_request(self) -> None:
        name, argv = parse_shell_command_request("python version: python --version")

        self.assertEqual(name, "python version")
        self.assertEqual(argv, ["python", "--version"])

    def test_shell_command_wizard_text_describes_safe_flow(self) -> None:
        text = shell_command_wizard_text()

        self.assertIn("Safe shell command wizard", text)
        self.assertIn("name: executable arg1 arg2", text)
        self.assertIn("The command is saved only", text)
        self.assertIn("Static review notes", text)
        self.assertIn("Static risk scoring", text)

    def test_static_review_notes_describe_saved_command_without_running(self) -> None:
        command = get_shell_command("python version")

        text = shell_command_static_review_notes(command)

        self.assertIn("Static review notes", text)
        self.assertIn("Saved only", text)
        self.assertIn("Validation passed", text)
        self.assertIn("Execution gate", text)
        self.assertIn("Static risk score: low", text)
        self.assertIn("Python review", text)

    def test_static_risk_profile_flags_package_tools_for_extra_review(self) -> None:
        command = get_shell_command("pip version")

        risk = shell_command_risk_profile(command)

        self.assertEqual(risk.level, "medium")
        self.assertGreaterEqual(risk.score, 4)
        self.assertTrue(any("Package tools" in reason for reason in risk.reasons))

    def test_creates_shell_operator_checklist_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            commands_path = root / "shell_commands.json"
            add_shell_command("python check", ["python", "--version"], commands_path)

            result = create_shell_review_checklist(
                "python check",
                commands_path=commands_path,
                output_dir=root / "checklists",
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            checklist_text = result.checklist_path.read_text(encoding="utf-8")

        self.assertIn("Shell operator checklist created", result.summary)
        self.assertIn("No shell command was run", result.summary)
        self.assertEqual(manifest["schema"], "safe_shell_operator_checklist_v1")
        self.assertFalse(manifest["execution_enabled"])
        self.assertFalse(manifest["runs_command"])
        self.assertEqual(manifest["static_risk"]["level"], "low")
        self.assertIn("checklist_signature", manifest)
        self.assertIn("# Shell Operator Checklist", checklist_text)
        self.assertIn("- [ ] Confirm the executable", checklist_text)

    def test_verifies_shell_operator_checklist_integrity_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            commands_path = root / "shell_commands.json"
            add_shell_command("python check", ["python", "--version"], commands_path)
            create_shell_review_checklist(
                "python check",
                commands_path=commands_path,
                output_dir=root / "checklists",
            )

            result = verify_shell_review_checklist(
                "python check",
                commands_path=commands_path,
                output_dir=root / "checklists",
            )

        self.assertEqual(result.status, "verified")
        self.assertIn("Checklist signature matches", result.summary)
        self.assertIn("No shell command was run", result.summary)

    def test_shell_operator_checklist_verification_blocks_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            commands_path = root / "shell_commands.json"
            add_shell_command("python check", ["python", "--version"], commands_path)
            checklist = create_shell_review_checklist(
                "python check",
                commands_path=commands_path,
                output_dir=root / "checklists",
            )
            manifest = json.loads(checklist.manifest_path.read_text(encoding="utf-8"))
            manifest["argv"] = ["python", "--help"]
            checklist.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            result = verify_shell_review_checklist(
                "python check",
                commands_path=commands_path,
                output_dir=root / "checklists",
            )

        self.assertEqual(result.status, "blocked")
        self.assertIn("Checklist command no longer matches", result.summary)
        self.assertIn("Checklist signature mismatch", result.summary)

    def test_signed_review_metadata_text_describes_tamper_evident_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shell_commands.json"
            command = add_shell_command("python check", ["python", "--version"], path)

            metadata = latest_shell_review_metadata(path, "add", command)
            text = shell_command_signed_review_text(metadata)

        self.assertIn("Signed review metadata", text)
        self.assertIn("Action: add", text)
        self.assertIn("Static risk: low", text)
        self.assertIn("Signature:", text)
        self.assertIn("does not run the command", text)

    def test_remove_shell_command_updates_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shell_commands.json"
            add_shell_command("python check", ["python", "--version"], path)

            removed = remove_shell_command("python check", path)
            commands = load_shell_commands(path)
            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(removed.name, "python check")
        self.assertNotIn("python check", commands)
        self.assertEqual([review["action"] for review in raw["reviews"]], ["add", "remove"])

    def test_get_unknown_command_reports_allowed_names(self) -> None:
        with self.assertRaises(ShellToolError) as context:
            get_shell_command("delete everything")

        self.assertIn("Shell command must be one of", str(context.exception))

    @patch("assistant.shell_tools.subprocess.run")
    def test_run_shell_command_captures_output_without_shell(self, mock_run) -> None:
        mock_run.return_value = Mock(returncode=0, stdout="Python 3.12.6\n", stderr="")
        command = get_shell_command("python version")

        output = run_shell_command(command)

        argv = mock_run.call_args.args[0]
        self.assertEqual(argv, ["python", "--version"])
        self.assertNotIn("shell", mock_run.call_args.kwargs)
        self.assertIn("exit code 0", output)
        self.assertIn("Python 3.12.6", output)


if __name__ == "__main__":
    unittest.main()
