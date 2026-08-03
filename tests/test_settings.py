import json
import tempfile
import unittest
from pathlib import Path

from assistant.settings import (
    AssistantSettings,
    SettingsError,
    load_settings,
    parse_setting_value,
    save_settings,
    update_setting,
    update_settings_file,
)


class SettingsTests(unittest.TestCase):
    def test_missing_settings_uses_defaults(self) -> None:
        settings = load_settings("missing-settings-file.json")

        self.assertEqual(settings.model, "smollm2:135m")
        self.assertEqual(settings.num_gpu, 0)
        self.assertTrue(settings.history_enabled)
        self.assertEqual(settings.notes_path, "data/notes.md")
        self.assertEqual(settings.tasks_path, "data/tasks.json")
        self.assertEqual(settings.aliases_path, "config/aliases.json")
        self.assertEqual(settings.voice_input_device, -1)
        self.assertEqual(settings.voice_sample_rate, 16000)
        self.assertTrue(settings.voice_debug_enabled)

    def test_load_settings_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(
                json.dumps({"assistant_name": "Friday", "model": "test-model"}),
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual(settings.assistant_name, "Friday")
        self.assertEqual(settings.model, "test-model")

    def test_save_settings_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            save_settings(AssistantSettings(assistant_name="Friday"), path)

            settings = load_settings(path)

        self.assertEqual(settings.assistant_name, "Friday")


    def test_parse_bool_setting(self) -> None:
        self.assertTrue(parse_setting_value("voice_enabled", "yes"))
        self.assertFalse(parse_setting_value("voice_enabled", "off"))

    def test_parse_int_setting(self) -> None:
        self.assertEqual(parse_setting_value("voice_timeout", "12"), 12)
        self.assertEqual(parse_setting_value("voice_input_device", "2"), 2)
        self.assertEqual(parse_setting_value("voice_sample_rate", "22050"), 22050)

    def test_parse_bool_debug_setting(self) -> None:
        self.assertFalse(parse_setting_value("voice_debug_enabled", "off"))

    def test_unknown_setting_is_rejected(self) -> None:
        with self.assertRaises(SettingsError):
            parse_setting_value("danger", "true")

    def test_update_setting_returns_new_settings(self) -> None:
        settings = update_setting(AssistantSettings(), "assistant_name", "Friday")

        self.assertEqual(settings.assistant_name, "Friday")

    def test_update_settings_file_persists_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            save_settings(AssistantSettings(), path)

            update_settings_file({"assistant_name": "Friday", "voice_enabled": "true"}, path)
            settings = load_settings(path)

        self.assertEqual(settings.assistant_name, "Friday")
        self.assertTrue(settings.voice_enabled)
    def test_invalid_json_raises_settings_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text("not json", encoding="utf-8")

            with self.assertRaises(SettingsError):
                load_settings(path)


if __name__ == "__main__":
    unittest.main()


