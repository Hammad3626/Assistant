import unittest

from assistant.core import LocalAssistant
from assistant.script_allowlist_design import script_allowlist_design_text


class ScriptAllowlistDesignTests(unittest.TestCase):
    def test_design_lists_static_gates_without_enabling_execution(self) -> None:
        text = script_allowlist_design_text()

        self.assertIn("Explicit script allowlist design", text)
        self.assertIn("Status: design only", text)
        self.assertIn("SHA-256 hash", text)
        self.assertIn("Required static review gates", text)
        self.assertIn("Required trust gates", text)
        self.assertIn("confirm script run", text)
        self.assertIn("Blocked in this build", text)
        self.assertIn("run script <allowed script name>", text)

    def test_assistant_design_command_is_read_only(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("script allowlist design")

        self.assertIsNone(response.pending_action)
        self.assertIn("Explicit script allowlist design", response.text)
        self.assertIn("No scripts are allowlisted or executed", response.text)


if __name__ == "__main__":
    unittest.main()
