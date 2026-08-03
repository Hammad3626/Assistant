import unittest
from unittest.mock import patch

from assistant.core import LocalAssistant


class ModelCommandTests(unittest.TestCase):
    @patch("assistant.core.list_ollama_models", return_value=["a-model", "b-model"])
    def test_models_command_lists_installed_models(self, mock_list) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("models")

        self.assertIn("Configured model: disabled", response.text)
        self.assertIn("Installed Ollama models:", response.text)
        self.assertIn("- a-model", response.text)

    @patch("assistant.core.list_ollama_models", return_value=["smollm2:135m"])
    def test_models_command_uses_current_llm_model(self, mock_list) -> None:
        class FakeClient:
            model = "smollm2:135m"

        assistant = LocalAssistant(llm_client=FakeClient())

        response = assistant.respond("list models")

        self.assertIn("Configured model: smollm2:135m", response.text)

    @patch("assistant.core.list_ollama_models")
    def test_models_command_reports_ollama_error(self, mock_list) -> None:
        from assistant.model_tools import ModelToolError

        mock_list.side_effect = ModelToolError("Ollama is not reachable.")
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("ollama models")

        self.assertIn("Model error: Ollama is not reachable.", response.text)
