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

    def test_gui_setting_fields_have_proper_types(self) -> None:
        for field in GUI_SETTING_FIELDS:
            self.assertIn(field.kind, ("text", "bool", "int"))
            self.assertTrue(len(field.label) > 0)
            self.assertTrue(len(field.key) > 0)

    def test_gui_model_fields_include_all_llm_settings(self) -> None:
        keys = {field.key for field in GUI_MODEL_FIELDS}

        self.assertEqual(keys, {"model", "use_llm", "num_gpu"})

    def test_gui_voice_fields_include_all_voice_settings(self) -> None:
        keys = {field.key for field in GUI_VOICE_FIELDS}

        self.assertIn("voice_enabled", keys)
        self.assertIn("voice_model_path", keys)
        self.assertIn("voice_timeout", keys)
        self.assertIn("speak_enabled", keys)
        self.assertIn("speech_rate", keys)
        self.assertIn("speech_volume", keys)

    def test_apply_gui_settings_handles_string_to_int_conversion(self) -> None:
        settings = apply_gui_settings(
            AssistantSettings(),
            {"num_gpu": "2", "voice_timeout": "30", "speech_rate": "100"},
        )

        self.assertEqual(settings.num_gpu, 2)
        self.assertEqual(settings.voice_timeout, 30)
        self.assertEqual(settings.speech_rate, 100)

    def test_apply_gui_settings_handles_string_to_bool_conversion(self) -> None:
        settings = apply_gui_settings(
            AssistantSettings(),
            {"use_llm": "true", "voice_enabled": "false"},
        )

        self.assertTrue(settings.use_llm)
        self.assertFalse(settings.voice_enabled)

    def test_apply_gui_settings_rejects_invalid_integer_values(self) -> None:
        with self.assertRaises(SettingsError):
            apply_gui_settings(AssistantSettings(), {"speech_rate": "not_a_number"})

    def test_gui_panel_names_has_correct_order(self) -> None:
        # Verify order matches expected workflow: general → apps → folders → models → voice → storage
        expected_start = ("General", "Apps", "Folders")
        self.assertEqual(GUI_PANEL_NAMES[:3], expected_start)

    def test_settings_saved_text_includes_settings_path(self) -> None:
        path = "data/custom-settings.json"
        text = settings_saved_text(path)

        self.assertIn(path, text)

    def test_all_fields_have_labels(self) -> None:
        all_fields = (
            GUI_SETTING_FIELDS
            + GUI_MODEL_FIELDS
            + GUI_VOICE_FIELDS
            + GUI_MEMORY_FIELDS
            + GUI_TASK_FIELDS
        )
        for field in all_fields:
            self.assertGreater(len(field.label), 0)
            self.assertTrue(any(c.isupper() for c in field.label))

    def test_apply_gui_settings_updates_multiple_fields_at_once(self) -> None:
        settings = apply_gui_settings(
            AssistantSettings(),
            {
                "assistant_name": "Cortana",
                "use_llm": True,
                "model": "neural:100b",
                "voice_enabled": True,
                "speech_volume": "80",
            },
        )

        self.assertEqual(settings.assistant_name, "Cortana")
        self.assertTrue(settings.use_llm)
        self.assertEqual(settings.model, "neural:100b")
        self.assertTrue(settings.voice_enabled)
        self.assertEqual(settings.speech_volume, 80)

    def test_gui_memory_fields_reference_storage_location(self) -> None:
        keys = {field.key for field in GUI_MEMORY_FIELDS}
        self.assertIn("memory_path", keys)

    def test_gui_task_fields_reference_storage_location(self) -> None:
        keys = {field.key for field in GUI_TASK_FIELDS}
        self.assertIn("tasks_path", keys)


if __name__ == "__main__":
    unittest.main()
