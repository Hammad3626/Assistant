"""Tests for the revocation commands that complete the curated allowlist
workflows built earlier: 'remove app', 'remove folder', 'remove network
domain'. Unlike granting access (add/allow), revoking is the safe
direction, so these are immediate -- no confirmation required.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistant.actions import (
    ActionError,
    load_allowed_apps,
    load_allowed_folders,
    remove_allowed_app,
    remove_allowed_folder,
    save_allowed_apps,
    save_allowed_folders,
)
from assistant.core import LocalAssistant
from assistant.network_tools import (
    NetworkToolError,
    add_allowed_domain,
    load_network_allowlist,
    remove_allowed_domain,
)


class RemoveAllowedAppUnitTests(unittest.TestCase):
    def test_remove_existing_app(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "apps.json"
            save_allowed_apps({"steam": "steam.exe", "notepad": "notepad.exe"}, path)

            apps = remove_allowed_app("steam", path)

            self.assertNotIn("steam", apps)
            self.assertIn("notepad", apps)
            self.assertNotIn("steam", load_allowed_apps(path))

    def test_remove_nonexistent_app_raises_with_available_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "apps.json"
            save_allowed_apps({"notepad": "notepad.exe"}, path)

            with self.assertRaises(ActionError) as ctx:
                remove_allowed_app("ghost", path)
            self.assertIn("notepad", str(ctx.exception))


class RemoveAllowedFolderUnitTests(unittest.TestCase):
    def test_remove_existing_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            path = Path(temp_dir) / "folders.json"
            save_allowed_folders({"workspace": str(workspace)}, path)

            folders = remove_allowed_folder("workspace", path)

            self.assertNotIn("workspace", folders)
            self.assertNotIn("workspace", load_allowed_folders(path))

    def test_remove_nonexistent_folder_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "folders.json"
            save_allowed_folders({}, path)

            with self.assertRaises(ActionError):
                remove_allowed_folder("ghost", path)


class RemoveAllowedDomainUnitTests(unittest.TestCase):
    def test_remove_existing_domain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            add_allowed_domain("example.com", path)

            domains = remove_allowed_domain("example.com", path)

            self.assertEqual(domains, [])
            self.assertEqual(load_network_allowlist(path), [])

    def test_remove_nonexistent_domain_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            with self.assertRaises(NetworkToolError):
                remove_allowed_domain("example.com", path)

    def test_remove_normalizes_domain_the_same_as_add(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network_allowlist.json"
            add_allowed_domain("WWW.Example.com", path)

            domains = remove_allowed_domain("example.com", path)
            self.assertEqual(domains, [])


class RemoveCommandsCoreWorkflowTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> LocalAssistant:
        root = Path(temp_dir)
        return LocalAssistant(
            use_llm=False,
            apps_path=root / "apps.json",
            folders_path=root / "folders.json",
            network_allowlist_path=root / "network_allowlist.json",
            data_export_dir=root / "exports",
        )

    def test_remove_app_no_confirmation_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            add_response = assistant.respond("add app steam at notepad.exe")
            assistant.confirm_pending_action(add_response.pending_action)

            response = assistant.respond("remove app steam")

            self.assertIsNone(response.pending_action)
            self.assertIn("Removed 'steam'", response.text)

    def test_remove_folder_no_confirmation_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "projects"
            target.mkdir()
            assistant = self._make_assistant(temp_dir)
            add_response = assistant.respond(f"add folder projects at {target}")
            assistant.confirm_pending_action(add_response.pending_action)

            response = assistant.respond("remove folder projects")

            self.assertIsNone(response.pending_action)
            self.assertIn("Removed 'projects'", response.text)

    def test_remove_network_domain_no_confirmation_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            assistant.respond("allow network domain example.com")

            response = assistant.respond("remove network domain example.com")

            self.assertIsNone(response.pending_action)
            self.assertIn("Removed 'example.com'", response.text)

            fetch_response = assistant.respond("fetch https://example.com")
            self.assertIsNone(fetch_response.pending_action)

    def test_remove_app_command_does_not_collide_with_add_app(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            response = assistant.respond("remove app steam")
            self.assertIsNone(response.pending_action)
            self.assertIn("Action error", response.text)


if __name__ == "__main__":
    unittest.main()
