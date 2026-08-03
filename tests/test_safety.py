import unittest

from assistant.safety import permission_dashboard_text, safety_text


class SafetyTests(unittest.TestCase):
    def test_safety_text_lists_boundaries(self) -> None:
        text = safety_text("Allowed apps: calculator. Allowed folders: downloads.")

        self.assertIn("Safety and permissions", text)
        self.assertIn("Requires confirmation:", text)
        self.assertIn("Raw arbitrary shell commands", text)
        self.assertIn("named safe shell command", text)
        self.assertIn("Edit named safe shell command allowlists", text)
        self.assertIn("confirmed bulk write and restore command designs", text)
        self.assertIn("Launch files in Windows only after confirmation", text)
        self.assertIn("trusted source roots", text)
        self.assertIn("script allowlisting design gates", text)
        self.assertIn("Permanent file deletion", text)
        self.assertIn("Voice input uses the local Vosk model", text)
        self.assertIn("Preview and correct spoken action commands", text)

    def test_permission_dashboard_lists_gated_features(self) -> None:
        text = permission_dashboard_text("Allowed apps: calculator. Allowed folders: downloads.")

        self.assertIn("Permissions dashboard", text)
        self.assertIn("Apps and folders: confirmation-gated", text)
        self.assertIn("Arbitrary files/documents: confirmation-gated with explicit file-type allowlist", text)
        self.assertIn("trusted source roots", text)
        self.assertIn("Shell commands: named allowlist with guided editor", text)
        self.assertIn("Voice: local optional with preview", text)
        self.assertIn("Bulk file modification: dry-run, backup, approval, review, rollback-plan, hashed signed preflight, verified checklist, and design only", text)
        self.assertIn("Messages, email, network: draft-only", text)
        self.assertIn("Scripts: review-only with allowlist design, checklist manifests, and signed export", text)
        self.assertIn("Blocked until explicit safety design", text)
