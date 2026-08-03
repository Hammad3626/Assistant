import unittest

from assistant.command_suggestions import suggest_commands, unknown_command_text


class CommandSuggestionTests(unittest.TestCase):
    def test_suggests_close_builtin_command(self) -> None:
        self.assertIn("memories", suggest_commands("memoris"))

    def test_suggests_safe_action_typo(self) -> None:
        self.assertIn("open calculator", suggest_commands("opne calculator"))

    def test_suggests_argument_command_template(self) -> None:
        self.assertEqual(suggest_commands("remeber I like quiet fans"), ["remember <fact>"])

    def test_suggests_shell_command_template(self) -> None:
        self.assertEqual(suggest_commands("run python version"), ["run shell <allowed command name>"])

    def test_does_not_suggest_for_normal_question(self) -> None:
        self.assertEqual(suggest_commands("explain local models"), [])

    def test_unknown_text_includes_reference_hint(self) -> None:
        text = unknown_command_text("memoris")

        self.assertIn("Did you mean", text)
        self.assertIn("command reference", text)
