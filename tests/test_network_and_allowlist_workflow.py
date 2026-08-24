"""Tests for:
- Feature 6: the read-only, GET-only, domain-allowlisted network fetch tool.
- Feature 4: the curated app/folder allowlist workflow reachable via chat,
  which must always require confirmation and re-uses the existing denylist.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from assistant.core import LocalAssistant
from assistant.network_tools import (
    NetworkToolError,
    add_allowed_domain,
    load_network_allowlist,
    validate_fetch_url,
)


class NetworkToolsTests(unittest.TestCase):
    def test_fetch_blocked_with_empty_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            with self.assertRaises(NetworkToolError):
                validate_fetch_url("https://example.com", path)

    def test_fetch_blocked_for_non_allowlisted_domain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            add_allowed_domain("example.com", path)
            with self.assertRaises(NetworkToolError):
                validate_fetch_url("https://evil.com", path)

    def test_fetch_allowed_for_allowlisted_domain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            add_allowed_domain("example.com", path)
            clean_url = validate_fetch_url("https://example.com/page", path)
            self.assertEqual(clean_url, "https://example.com/page")

    def test_fetch_rejects_non_http_scheme(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            add_allowed_domain("example.com", path)
            with self.assertRaises(NetworkToolError):
                validate_fetch_url("ftp://example.com/file", path)

    def test_add_allowed_domain_persists_and_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            add_allowed_domain("WWW.Example.com", path)
            self.assertEqual(load_network_allowlist(path), ["example.com"])


class NetworkFetchCoreWorkflowTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> LocalAssistant:
        root = Path(temp_dir)
        return LocalAssistant(
            use_llm=False,
            network_allowlist_path=root / "network_allowlist.json",
            data_export_dir=root / "exports",
        )

    def test_fetch_command_requires_allowlisted_domain_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            response = assistant.respond("fetch https://example.com")
            self.assertIsNone(response.pending_action)
            self.assertIn("No domains are allowlisted", response.text)

    def test_allow_network_domain_command_slices_correctly(self) -> None:
        """Regression test for an off-by-one slicing bug: 'allow network
        domain example.com' must add exactly 'example.com', not a mangled
        variant like 'xample.com' with the first character dropped.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            response = assistant.respond("allow network domain example.com")
            self.assertIn("Added 'example.com'", response.text)
            self.assertNotIn("Added 'xample.com'", response.text)
            from assistant.network_tools import load_network_allowlist

            self.assertEqual(load_network_allowlist(assistant.network_allowlist_path), ["example.com"])

    def test_fetch_end_to_end_with_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            assistant.respond("allow network domain example.com")

            response = assistant.respond("fetch https://example.com/page")
            self.assertIsNotNone(response.pending_action)
            assert response.pending_action is not None
            self.assertEqual(response.pending_action.kind, "network_fetch")

            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.headers = {"Content-Type": "text/html"}
            mock_response.read.return_value = b"hello world"
            mock_response.__enter__ = lambda self: mock_response
            mock_response.__exit__ = lambda self, *a: None

            with patch("assistant.network_tools.urllib.request.urlopen", return_value=mock_response):
                result = assistant.confirm_pending_action(response.pending_action)
            self.assertIn("Status: 200", result)
            self.assertIn("hello world", result)

    def test_network_fetch_never_uses_a_write_http_method(self) -> None:
        """Static check: the fetch tool must remain GET-only end to end."""
        import inspect
        from assistant import network_tools

        source = inspect.getsource(network_tools)
        self.assertIn('method="GET"', source)
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            self.assertNotIn(f'method="{method}"', source)


class CuratedAllowlistWorkflowTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> LocalAssistant:
        root = Path(temp_dir)
        return LocalAssistant(
            use_llm=False,
            apps_path=root / "apps.json",
            folders_path=root / "folders.json",
            data_export_dir=root / "exports",
        )

    def test_add_app_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            response = assistant.respond("add app steam at notepad.exe")
            self.assertIsNotNone(response.pending_action)
            assert response.pending_action is not None
            self.assertEqual(response.pending_action.kind, "add_allowed_app")
            self.assertIn("Please confirm", response.text)

    def test_add_app_end_to_end_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            response = assistant.respond("add app steam at notepad.exe")
            result = assistant.confirm_pending_action(response.pending_action)
            self.assertIn("Done: Added 'steam'", result)

            from assistant.actions import load_allowed_apps

            apps = load_allowed_apps(assistant.apps_path)
            self.assertEqual(apps["steam"], "notepad.exe")

    def test_add_app_rejects_denylisted_executable_even_under_friendly_name(self) -> None:
        """Regression test: the curated-allowlist workflow must not become
        a backdoor around the denylist -- 'add app sneaky at cmd.exe' must
        be blocked, both at confirmation time and at execution time.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)

            response = assistant.respond("add app sneaky at cmd.exe")
            self.assertIsNone(response.pending_action)
            self.assertIn("Action error", response.text)

    def test_add_folder_requires_confirmation_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "projects"
            target.mkdir()
            assistant = self._make_assistant(temp_dir)

            response = assistant.respond(f"add folder projects at {target}")
            self.assertIsNotNone(response.pending_action)
            assert response.pending_action is not None
            self.assertEqual(response.pending_action.kind, "add_allowed_folder")

            result = assistant.confirm_pending_action(response.pending_action)
            self.assertIn("Done: Added 'projects'", result)

    def test_add_folder_rejects_nonexistent_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            response = assistant.respond("add folder ghost at totally-nonexistent-xyz")
            self.assertIsNone(response.pending_action)
            self.assertIn("Action error", response.text)

    def test_allowlisting_never_happens_without_explicit_confirmation(self) -> None:
        """respond() alone (before 'yes') must never write to apps.json or
        folders.json -- only confirm_pending_action() may.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            assistant.respond("add app steam at notepad.exe")
            self.assertFalse(assistant.apps_path.exists())


if __name__ == "__main__":
    unittest.main()
