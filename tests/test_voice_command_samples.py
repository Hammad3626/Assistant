import unittest
from unittest.mock import patch

from assistant.actions import parse_action
from assistant.intent_parser import normalize_intent
from assistant.voice_input import normalize_spoken_command


class VoiceCommandSampleTests(unittest.TestCase):
    def _pipeline_command(self, spoken_text: str) -> str:
        normalized_spoken = normalize_spoken_command(spoken_text)
        intent = normalize_intent(normalized_spoken)
        return intent if intent is not None else normalized_spoken

    def test_sample_app_commands(self) -> None:
        for spoken, expected in (
            ("open calculator", "open calculator"),
            ("open google chrome", "open chrome"),
            ("launch calculator app", "open calculator"),
        ):
            with self.subTest(spoken=spoken):
                command = self._pipeline_command(spoken)
                action = parse_action(command)
                self.assertEqual(command, expected)
                self.assertIsNotNone(action)
                assert action is not None
                self.assertEqual(action.kind, "app")

    def test_sample_folder_and_settings_commands(self) -> None:
        import tempfile
        from pathlib import Path
        from assistant.actions import save_allowed_folders

        with tempfile.TemporaryDirectory() as temp_dir:
            downloads_dir = Path(temp_dir) / "Downloads"
            downloads_dir.mkdir()
            folders_path = Path(temp_dir) / "folders.json"
            save_allowed_folders({"downloads": str(downloads_dir)}, folders_path)

            command = self._pipeline_command("show my downloads folder")
            action = parse_action(command, folders_path=folders_path)
            self.assertEqual(command, "open downloads")
            self.assertIsNotNone(action)
            assert action is not None
            self.assertEqual(action.kind, "folder")

        settings_command = self._pipeline_command("open windows settings")
        settings_action = parse_action(settings_command)
        self.assertEqual(settings_command, "open settings")
        self.assertIsNotNone(settings_action)
        assert settings_action is not None
        self.assertEqual(settings_action.kind, "special")

    @patch("assistant.actions._drive_exists", return_value=True)
    def test_sample_drive_command(self, mock_drive_exists) -> None:
        command = self._pipeline_command("open drive d")
        action = parse_action(command)

        self.assertEqual(command, "open D drive")
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.kind, "folder")
        self.assertEqual(action.target, "D:\\")

    def test_sample_file_preview_command(self) -> None:
        command = self._pipeline_command("please open file in project folder README.md")

        self.assertEqual(command, "open file in project folder README.md")
        self.assertIsNone(parse_action(command))

    def test_common_exit_misrecognition_maps_to_exit(self) -> None:
        command = self._pipeline_command("as it")

        self.assertEqual(command, "exit")


if __name__ == "__main__":
    unittest.main()
