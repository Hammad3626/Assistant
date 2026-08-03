import unittest

from assistant.command_help import command_help_text, help_topics_text


class CommandHelpTests(unittest.TestCase):
    def test_topics_include_common_areas(self) -> None:
        topics = help_topics_text()

        self.assertIn("tasks", topics)
        self.assertIn("memory", topics)
        self.assertIn("actions", topics)
        self.assertIn("models", topics)
        self.assertIn("about", topics)
        self.assertIn("safety", topics)
        self.assertIn("roadmap", topics)
        self.assertIn("launch", topics)
        self.assertIn("shell", topics)

    def test_shell_help_describes_safety_limits(self) -> None:
        text = command_help_text("shell")

        self.assertIn("Help: shell", text)
        self.assertIn("run shell <allowed command name>", text)
        self.assertIn("raw arbitrary shell text", text)

    def test_actions_help_mentions_script_allowlist_design(self) -> None:
        text = command_help_text("actions")

        self.assertIn("script allowlist design", text)
        self.assertIn("script review checklist", text)
        self.assertIn("script allowlist preflight", text)
        self.assertIn("does not allowlist or run scripts", text)

    def test_task_help_includes_examples(self) -> None:
        text = command_help_text("tasks")

        self.assertIn("todo <task>", text)
        self.assertIn("done <task number>", text)
        self.assertIn("delete task <number>", text)
        self.assertIn("restore deleted task <number>", text)

    def test_alias_topic_resolves(self) -> None:
        text = command_help_text("todo")

        self.assertIn("Help: tasks", text)

    def test_unknown_topic_returns_topic_list(self) -> None:
        text = command_help_text("printers")

        self.assertIn("I do not have help", text)
        self.assertIn("Help topics", text)

    def test_files_help_mentions_bulk_design_commands(self) -> None:
        text = command_help_text("files")

        self.assertIn("bulk write command design", text)
        self.assertIn("bulk restore command design", text)
        self.assertIn("launch file in <folder> <relative path>", text)
        self.assertIn("trust file type source <extension>", text)
        self.assertIn("trust file type thumbprint <extension>", text)
        self.assertIn("trust file type issuer <extension>", text)
        self.assertIn("trust file type validity <extension>", text)
        self.assertIn("trust file type revocation <extension>", text)

    def test_safety_help_mentions_script_snapshot_filter(self) -> None:
        text = command_help_text("safety")

        self.assertIn("safety snapshot scripts", text)
        self.assertIn("script review", text)
