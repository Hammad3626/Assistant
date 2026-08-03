import unittest

from assistant.ollama_client import OllamaClient


class OllamaClientTests(unittest.TestCase):
    def test_build_prompt_uses_custom_system_prompt(self) -> None:
        prompt = OllamaClient._build_prompt(
            "hello",
            memory_context="- likes short answers",
            system_prompt="Custom system prompt.",
        )

        self.assertIn("Custom system prompt.", prompt)
        self.assertIn("likes short answers", prompt)
        self.assertIn("User: hello", prompt)


if __name__ == "__main__":
    unittest.main()

