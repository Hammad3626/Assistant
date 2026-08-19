import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistant.actions import (
    ActionError,
    add_allowed_app,
    add_allowed_folder,
    execute_action,
    load_allowed_apps,
    load_allowed_folders,
    parse_action,
    save_allowed_apps,
    save_allowed_folders,
)


class ActionTests(unittest.TestCase):
    def test_parse_allowed_app_action(self) -> None:
        action = parse_action("open calculator")

        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.kind, "app")
        self.assertEqual(action.target, "calc.exe")

    def test_parse_chrome_as_allowed_app(self) -> None:
        action = parse_action("open chrome")

        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.kind, "app")
        self.assertTrue(action.target.lower().endswith("chrome.exe"))

    def test_parse_allowed_folder_action(self) -> None:
        action = parse_action("open downloads")

        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.kind, "folder")
        self.assertIn("Downloads", action.target)

    @patch("assistant.actions._drive_exists", return_value=True)
    def test_parse_detected_drive_action(self, mock_drive_exists) -> None:
        action = parse_action("open C drive")

        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.kind, "folder")
        self.assertEqual(action.target, "C:\\")
        self.assertEqual(action.description, "Open C drive")
        mock_drive_exists.assert_called_once_with("C:\\")

    def test_parse_this_pc_and_windows_settings_actions(self) -> None:
        this_pc = parse_action("open this pc")
        settings = parse_action("open settings")

        self.assertIsNotNone(this_pc)
        self.assertIsNotNone(settings)
        assert this_pc is not None
        assert settings is not None
        self.assertEqual(this_pc.kind, "special")
        self.assertEqual(this_pc.target, "shell:MyComputerFolder")
        self.assertEqual(settings.kind, "special")
        self.assertEqual(settings.target, "ms-settings:")

    def test_rejects_arbitrary_command(self) -> None:
        self.assertIsNone(parse_action("run powershell remove files"))

    def test_load_custom_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "apps.json"
            save_allowed_apps({"paint": "mspaint.exe"}, path)

            action = parse_action("open paint", apps_path=path)

        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.target, "mspaint.exe")

    def test_load_custom_folder_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            path = folder / "folders.json"
            save_allowed_folders({"workspace": str(folder)}, path)

            action = parse_action("open workspace", folders_path=path)

        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.kind, "folder")
        self.assertEqual(Path(action.target), folder)

    def test_rejects_shell_executable_in_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "apps.json"

            with self.assertRaises(ActionError):
                save_allowed_apps({"shell": "powershell.exe"}, path)

    def test_add_allowed_app_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "apps.json"
            add_allowed_app("paint", "mspaint.exe", path)

            apps = load_allowed_apps(path)

        self.assertEqual(apps["paint"], "mspaint.exe")

    def test_add_allowed_folder_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            path = folder / "folders.json"
            add_allowed_folder("workspace", str(folder), path)

            folders = load_allowed_folders(path)

        self.assertEqual(Path(folders["workspace"]), folder)

    def test_rejects_folder_shell_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "folders.json"

            with self.assertRaises(ActionError):
                save_allowed_folders({"bad": f"{temp_dir};calc.exe"}, path)

    @patch("assistant.actions.subprocess.Popen")
    def test_execute_app_uses_allowlisted_target(self, mock_popen) -> None:
        action = parse_action("open notepad")
        assert action is not None

        result = execute_action(action)

        mock_popen.assert_called_once_with(["notepad.exe"])
        self.assertIn("Done", result)

    @patch("assistant.actions.os.startfile", create=True)
    def test_execute_folder_opens_existing_path(self, mock_startfile) -> None:
        action = parse_action("open project folder")
        assert action is not None

        result = execute_action(action)

        mock_startfile.assert_called_once()
        opened_path = Path(mock_startfile.call_args.args[0])
        self.assertTrue(opened_path.exists())
        self.assertIn("Done", result)

    @patch("assistant.actions.os.startfile", create=True)
    def test_execute_special_windows_location_uses_startfile(self, mock_startfile) -> None:
        action = parse_action("open this pc")
        assert action is not None

        result = execute_action(action)

        mock_startfile.assert_called_once_with("shell:MyComputerFolder")
        self.assertIn("Done", result)

    @patch("assistant.actions.os.startfile", create=True)
    def test_try_open_unrestricted_file(self, mock_startfile) -> None:
        """Test opening an arbitrary file via try_open_unrestricted."""
        from assistant.actions import try_open_unrestricted
        
        result = try_open_unrestricted("C:\\Users\\test\\document.pdf")
        
        mock_startfile.assert_called_once_with("C:\\Users\\test\\document.pdf")
        self.assertIn("Done", result)

    @patch("assistant.actions.os.startfile", create=True)
    def test_try_open_unrestricted_folder(self, mock_startfile) -> None:
        """Test opening an arbitrary folder via try_open_unrestricted."""
        from assistant.actions import try_open_unrestricted
        
        result = try_open_unrestricted("D:\\Projects")
        
        mock_startfile.assert_called_once()
        self.assertIn("Done", result)

    @patch("assistant.actions.subprocess.Popen")
    @patch("assistant.actions.os.startfile", side_effect=OSError("Not a file"))
    def test_try_open_unrestricted_app_fallback(self, mock_startfile, mock_popen) -> None:
        """Test opening an app when startfile fails."""
        from assistant.actions import try_open_unrestricted
        
        result = try_open_unrestricted("notepad.exe")
        
        mock_startfile.assert_called_once()
        mock_popen.assert_called_once_with(["notepad.exe"])
        self.assertIn("Done", result)

    def test_try_open_unrestricted_rejects_shell_commands(self) -> None:
        """Test that try_open_unrestricted rejects shell control characters."""
        from assistant.actions import try_open_unrestricted, ActionError
        
        with self.assertRaises(ActionError) as context:
            try_open_unrestricted("file.txt | delete")
        
        self.assertIn("shell control", str(context.exception))

    def test_try_open_unrestricted_rejects_denied_system_executables(self) -> None:
        """Regression test: the unrestricted-launch path must enforce the same
        denylist as validate_app_target(), so cmd/powershell/regedit/etc cannot
        be launched just because they weren't in the allowlisted-apps flow.
        """
        from assistant.actions import try_open_unrestricted, ActionError

        denied_targets = [
            "cmd",
            "cmd.exe",
            "powershell",
            "powershell.exe",
            "PowerShell.EXE",
            "pwsh.exe",
            "regedit",
            "regedit.exe",
            "reg.exe",
            "wscript.exe",
            "cscript.exe",
            "C:\\Windows\\System32\\cmd.exe",
        ]
        for target in denied_targets:
            with self.assertRaises(ActionError, msg=f"Should have blocked: {target}"):
                try_open_unrestricted(target)

    @patch("assistant.actions.subprocess.Popen")
    @patch("assistant.actions.os.startfile", create=True, side_effect=OSError("Not a file"))
    def test_try_open_unrestricted_rejects_denied_executable_on_subprocess_fallback(
        self, mock_startfile, mock_popen
    ) -> None:
        """Regression test: the denylist must also apply on the subprocess.Popen
        fallback path (when os.startfile fails), not just the initial check.
        """
        from assistant.actions import try_open_unrestricted, ActionError

        with self.assertRaises(ActionError):
            try_open_unrestricted("cmd.exe")

        mock_popen.assert_not_called()

    @patch("assistant.actions.os.startfile", create=True)
    def test_execute_unrestricted_action(self, mock_startfile) -> None:
        """Test executing an unrestricted action."""
        from assistant.actions import PendingAction
        
        action = PendingAction(
            kind="unrestricted",
            target="C:\\test\\file.txt",
            description="Open test file",
        )
        
        result = execute_action(action)
        
        self.assertIn("Done", result)


if __name__ == "__main__":
    unittest.main()
