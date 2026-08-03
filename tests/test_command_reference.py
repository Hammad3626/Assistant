import unittest

from assistant.command_reference import command_reference_text


class CommandReferenceTests(unittest.TestCase):
    def test_reference_includes_core_categories(self) -> None:
        reference = command_reference_text()

        self.assertIn("Command reference", reference)
        self.assertIn("Basics:", reference)
        self.assertIn("about, architecture", reference)
        self.assertIn("safety, permissions", reference)
        self.assertIn("roadmap, next steps", reference)
        self.assertIn("safety snapshot scripts", reference)
        self.assertIn("launch commands", reference)
        self.assertIn("Memory:", reference)
        self.assertIn("Tasks:", reference)
        self.assertIn("Safe local actions:", reference)
        self.assertIn("shell commands", reference)
        self.assertIn("run shell", reference)
        self.assertIn("script allowlist design", reference)
        self.assertIn("script review checklist <request number>", reference)
        self.assertIn("verify script review checklist <request number>", reference)
        self.assertIn("script allowlist preflight <request number>", reference)
        self.assertIn("models, list models", reference)
        self.assertIn("delete task", reference)
        self.assertIn("task trash", reference)
        self.assertIn("bulk write command design", reference)
        self.assertIn("bulk restore command design", reference)
        self.assertIn("launch file in <folder> <relative path>", reference)
        self.assertIn("trust file type source <extension>", reference)
        self.assertIn("trust file type thumbprint <extension>", reference)
        self.assertIn("trust file type issuer <extension>", reference)
        self.assertIn("trust file type validity <extension>", reference)
        self.assertIn("trust file type revocation <extension>", reference)

    def test_reference_mentions_safety_limits(self) -> None:
        reference = command_reference_text()

        self.assertIn("actions require confirmation", reference)
        self.assertIn("raw arbitrary shell commands are not enabled", reference)
        self.assertIn("future confirmed commands", reference)
        self.assertIn("explicit file-type allowlisting", reference)
        self.assertIn("trusted source roots", reference)
        self.assertIn("thumbprints", reference)
        self.assertIn("certificate dates", reference)
        self.assertIn("revocation-status checks", reference)
        self.assertIn("hash pinning", reference)
        self.assertIn("no-run flags", reference)
