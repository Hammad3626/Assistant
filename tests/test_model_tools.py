import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from assistant.model_tools import ModelToolError, list_ollama_models, update_default_model
from assistant.settings import AssistantSettings, load_settings, save_settings


class ModelToolsTests(unittest.TestCase):
    @patch("assistant.model_tools.urllib.request.urlopen")
    def test_list_ollama_models(self, mock_urlopen) -> None:
        response = Mock()
        response.read.return_value = json.dumps(
            {"models": [{"name": "b-model"}, {"name": "a-model"}]}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        models = list_ollama_models()

        self.assertEqual(models, ["a-model", "b-model"])

    @patch("assistant.model_tools.list_ollama_models", return_value=["smollm2:135m"])
    def test_update_default_model_requires_installed_model(self, mock_list) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            save_settings(AssistantSettings(model="old"), path)

            settings = update_default_model("smollm2:135m", str(path), num_gpu=0)
            loaded = load_settings(path)

        self.assertEqual(settings.model, "smollm2:135m")
        self.assertEqual(loaded.model, "smollm2:135m")

    @patch("assistant.model_tools.list_ollama_models", return_value=["smollm2:135m"])
    def test_update_default_model_rejects_missing_model(self, mock_list) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            save_settings(AssistantSettings(), path)

            with self.assertRaises(ModelToolError):
                update_default_model("missing-model", str(path))


if __name__ == "__main__":
    unittest.main()

