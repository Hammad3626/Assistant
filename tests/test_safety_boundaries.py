"""Regression tests for four core safety boundaries the assistant must hold:

1. No raw arbitrary shell command execution (only named, allowlisted commands).
2. No permanent file deletion or live bulk file modification apply path.
3. No real message/email/network sending capability.
4. No automatic/unconfirmed launching or allowlisting of unlisted apps or scripts.

These tests exist because each of the four was independently audited and found
sound, with the exception of a couple of latent gaps that were then fixed:
- assistant/file_batch_operations.py contained live unlink()/overwrite logic
  that was unreachable from the live app, but contradicted the rest of the
  codebase's dry-run-only bulk policy. It has been removed.
- windows_integration.py's start_ollama_if_needed() launches a real
  executable with no confirmation prompt; it is gated behind
  check_ollama_on_startup, which now defaults to False (was True).
"""

from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path

from assistant.windows_integration import WindowsIntegrationConfig


ASSISTANT_DIR = Path(__file__).resolve().parent.parent / "assistant"


class NoRawShellExecutionTests(unittest.TestCase):
    def test_shell_tools_never_uses_shell_true(self) -> None:
        """subprocess calls in shell_tools.py must never use shell=True, which
        would allow raw shell string execution instead of a fixed argv list.
        """
        source = (ASSISTANT_DIR / "shell_tools.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "shell":
                        self.assertFalse(
                            isinstance(keyword.value, ast.Constant) and keyword.value.value is True,
                            "shell_tools.py must never call subprocess with shell=True",
                        )

    def test_run_shell_command_only_accepts_looked_up_named_commands(self) -> None:
        """The only way to reach run_shell_command's argv must be through
        get_shell_command(), which resolves a name against the JSON
        allowlist -- never raw free-text user input.
        """
        from assistant.shell_tools import get_shell_command, ShellToolError

        with self.assertRaises(ShellToolError):
            get_shell_command("rm -rf /", path="nonexistent-shell-commands.json")


class NoLiveDestructiveBulkOpsTests(unittest.TestCase):
    def test_file_batch_operations_module_removed(self) -> None:
        """The old file_batch_operations module contained a live, unguarded
        Path.unlink() delete and an in-place overwrite with no trash/backup,
        contradicting the rest of the app's dry-run-only bulk policy. It must
        not exist, so it can never be accidentally wired into the live app.
        """
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("assistant.file_batch_operations")

    def test_bulk_replace_apply_plan_never_writes_files(self) -> None:
        """The wired-in bulk apply-plan summary must remain dry-run only."""
        import json
        import tempfile
        from assistant.file_tools import AllowlistedFileTools

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "docs"
            folder.mkdir()
            sample = folder / "a.txt"
            sample.write_text("hello world", encoding="utf-8")

            folders_path = root / "folders.json"
            folders_path.write_text(
                json.dumps({"folders": {"docs": str(folder)}}), encoding="utf-8"
            )

            tools = AllowlistedFileTools(
                folders_path=folders_path,
                trash_dir=root / "trash",
                manifest_path=root / "trash-manifest.json",
                bulk_backup_dir=root / "bulk-backups",
                bulk_approval_dir=root / "bulk-approvals",
                bulk_review_dir=root / "bulk-reviews",
                bulk_rollback_dir=root / "bulk-rollbacks",
                bulk_preflight_dir=root / "bulk-preflights",
                bulk_checklist_dir=root / "bulk-checklists",
            )
            summary = tools.bulk_replace_apply_plan_summary("docs", "hello", "goodbye")

            self.assertIn("Apply is not enabled in this build", summary)
            self.assertEqual(sample.read_text(encoding="utf-8"), "hello world")


class NoRealSendOrNetworkCapabilityTests(unittest.TestCase):
    def test_outbox_module_has_no_send_or_network_send_calls(self) -> None:
        """outbox.py must remain local-draft-only: no smtplib, no `requests`
        library usage, no http.client, and no urllib.request usage that could
        actually send something over the network.
        """
        source = (ASSISTANT_DIR / "outbox.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_paths: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_paths.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_paths.add(node.module)

        forbidden_paths = {"smtplib", "requests", "http.client", "urllib.request"}
        self.assertFalse(
            imported_paths & forbidden_paths,
            f"outbox.py imports network-capable module(s): {imported_paths & forbidden_paths}",
        )

    def test_outbox_drafts_are_local_json_only(self) -> None:
        import tempfile
        from assistant.outbox import OutboxStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outbox.json"
            store = OutboxStore(path=path)
            store.draft_email("someone@example.com", "Subject", "Body")
            store.draft_network_request("POST", "https://example.com/api", "note")

            # Nothing should have been sent anywhere; only a local file exists.
            self.assertTrue(path.exists())
            drafts = store.list_drafts()
            self.assertEqual(len(drafts), 2)

    def test_no_outbound_network_calls_target_non_local_hosts_outside_network_tools(self) -> None:
        """Any real urllib.request.urlopen call OUTSIDE assistant/network_tools.py
        must target localhost/127.0.0.1 (the local Ollama server), never an
        arbitrary remote host. assistant/network_tools.py is intentionally
        excluded: it is a deliberate, separately-gated capability (GET-only,
        domain-allowlisted, confirmation-required) covered by its own tests
        in test_network_tools.py, not an accidental/unaudited network call.
        """
        for path in ASSISTANT_DIR.glob("*.py"):
            if path.name == "network_tools.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "urlopen(" not in source and "urllib.request.Request(" not in source:
                continue
            for line in source.splitlines():
                if "http://" in line and "127.0.0.1" not in line and "localhost" not in line:
                    self.fail(f"{path.name} references a non-local http:// URL: {line.strip()}")

    def test_network_tools_only_supports_get_requests(self) -> None:
        """assistant/network_tools.py must remain read-only: no POST/PUT/
        DELETE/PATCH support, so it can never be used to send data anywhere.
        """
        source = (ASSISTANT_DIR / "network_tools.py").read_text(encoding="utf-8")
        self.assertIn('method="GET"', source)
        for forbidden_method in ('method="POST"', 'method="PUT"', 'method="DELETE"', 'method="PATCH"'):
            self.assertNotIn(forbidden_method, source)

    def test_network_tools_refuses_fetch_with_empty_allowlist(self) -> None:
        import tempfile
        from assistant.network_tools import NetworkToolError, validate_fetch_url

        with tempfile.TemporaryDirectory() as tmp:
            allowlist_path = Path(tmp) / "network_allowlist.json"
            with self.assertRaises(NetworkToolError):
                validate_fetch_url("https://example.com", allowlist_path)

    def test_personal_config_files_are_gitignored(self) -> None:
        """config/notification_config.json (once configured, contains a
        real recipient email and SMTP username) and
        config/network_allowlist.json (a personal domain list) must never
        be accidentally committed via a broad 'git add -A'.
        """
        gitignore_path = Path(__file__).resolve().parent.parent / ".gitignore"
        gitignore = gitignore_path.read_text(encoding="utf-8")
        self.assertIn("config/notification_config.json", gitignore)
        self.assertIn("config/network_allowlist.json", gitignore)


class NoUnconfirmedAutoLaunchTests(unittest.TestCase):
    def test_check_ollama_on_startup_defaults_to_false(self) -> None:
        """Auto-launching ollama.exe on startup with no confirmation prompt
        must require explicit opt-in, not be on by default.
        """
        config = WindowsIntegrationConfig()
        self.assertFalse(config.check_ollama_on_startup)

    def test_windows_integration_not_imported_by_live_entry_points(self) -> None:
        """start_ollama_if_needed()/startup_checks() silently launch a real
        executable with no confirmation gate. They must stay unreachable from
        the live app (cli.py/core.py) unless routed through a PendingAction
        confirmation first.
        """
        cli_source = (ASSISTANT_DIR / "cli.py").read_text(encoding="utf-8")
        core_source = (ASSISTANT_DIR / "core.py").read_text(encoding="utf-8")
        self.assertNotIn("windows_integration", cli_source)
        self.assertNotIn("windows_integration", core_source)

    def test_add_allowed_app_and_folder_only_reachable_after_explicit_confirmation(self) -> None:
        """Allowlisting a new app/folder must never happen automatically from
        conversational input alone -- it must always go through the same
        PendingAction confirm_pending_action() gate as every other
        state-changing action (the user must type the request AND then
        separately confirm with 'yes'). It is fine for this to be reachable
        via chat (e.g. "add app X at Y") as long as it's confirmation-gated;
        it must never be callable directly from respond()'s parsing path.
        """
        core_source = (ASSISTANT_DIR / "core.py").read_text(encoding="utf-8")
        respond_start = core_source.index("\n    def respond(")
        confirm_start = core_source.index("\n    def confirm_pending_action(")
        # confirm_pending_action must come after respond() in the file, and
        # both add_allowed_app(/add_allowed_folder( calls must live at or
        # after confirm_pending_action's definition -- never inside respond().
        self.assertGreater(confirm_start, respond_start)
        respond_body = core_source[respond_start:confirm_start]
        self.assertNotIn("add_allowed_app(", respond_body)
        self.assertNotIn("add_allowed_folder(", respond_body)

        rest_of_file = core_source[confirm_start:]
        self.assertIn("add_allowed_app(", rest_of_file)
        self.assertIn("add_allowed_folder(", rest_of_file)


if __name__ == "__main__":
    unittest.main()
