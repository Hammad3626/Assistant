import unittest

from assistant.gui_settings import (
    GUI_MEMORY_FIELDS,
    GUI_MODEL_FIELDS,
    GUI_PANEL_NAMES,
    GUI_SETTING_FIELDS,
    GUI_TASK_FIELDS,
    GUI_VOICE_FIELDS,
    apply_gui_settings,
    settings_saved_text,
)
from assistant.settings import AssistantSettings, SettingsError


class GuiSettingsTests(unittest.TestCase):
    def test_fields_include_common_safe_settings(self) -> None:
        keys = {field.key for field in GUI_SETTING_FIELDS}

        self.assertIn("assistant_name", keys)
        self.assertIn("history_enabled", keys)

        model_keys = {field.key for field in GUI_MODEL_FIELDS}
        voice_keys = {field.key for field in GUI_VOICE_FIELDS}
        memory_keys = {field.key for field in GUI_MEMORY_FIELDS}
        task_keys = {field.key for field in GUI_TASK_FIELDS}

        self.assertIn("model", model_keys)
        self.assertIn("use_llm", model_keys)
        self.assertIn("voice_enabled", voice_keys)
        self.assertIn("speak_enabled", voice_keys)
        self.assertIn("memory_path", memory_keys)
        self.assertIn("tasks_path", task_keys)

    def test_panel_names_include_requested_settings_areas(self) -> None:
        self.assertEqual(
            GUI_PANEL_NAMES,
            ("General", "Apps", "Folders", "Models", "Voice", "Memory", "Tasks"),
        )

    def test_apply_gui_settings_validates_and_updates_values(self) -> None:
        settings = apply_gui_settings(
            AssistantSettings(),
            {
                "assistant_name": "Friday",
                "use_llm": False,
                "num_gpu": "0",
                "speech_volume": "75",
            },
        )

        self.assertEqual(settings.assistant_name, "Friday")
        self.assertFalse(settings.use_llm)
        self.assertEqual(settings.num_gpu, 0)
        self.assertEqual(settings.speech_volume, 75)

    def test_apply_gui_settings_rejects_invalid_types(self) -> None:
        with self.assertRaises(SettingsError):
            apply_gui_settings(AssistantSettings(), {"voice_timeout": "slow"})

    def test_settings_saved_text_mentions_restart(self) -> None:
        text = settings_saved_text("config/settings.json")

        self.assertIn("Settings saved", text)
        self.assertIn("Restart", text)


if __name__ == "__main__":
    unittest.main()
