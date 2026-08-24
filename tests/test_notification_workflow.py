"""Tests for the deliberately narrow, pre-approved email notification.

Key invariants under test:
- Disabled by default; requires explicit config-file opt-in.
- No conversational command can set/change recipient, subject, or SMTP host.
- Password is never stored in the config file, only an env var name.
- Sending always goes through PendingAction confirmation.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from assistant.core import LocalAssistant
from assistant.notifications import (
    NotificationConfigError,
    load_notification_config,
    notification_config_summary,
    send_configured_notification,
)


class NotificationConfigTests(unittest.TestCase):
    def test_default_config_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_notification_config(Path(temp_dir) / "nope.json")
            self.assertFalse(config.enabled)

    def test_send_blocked_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notification_config.json"
            with self.assertRaises(NotificationConfigError):
                send_configured_notification("body", path)

    def test_send_blocked_when_config_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notification_config.json"
            path.write_text(json.dumps({"enabled": True, "recipient": "me@example.com"}))
            with self.assertRaises(NotificationConfigError) as ctx:
                send_configured_notification("body", path)
            self.assertIn("smtp_host", str(ctx.exception))

    def test_send_blocked_when_password_env_var_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notification_config.json"
            path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "recipient": "me@example.com",
                        "smtp_host": "smtp.example.com",
                        "smtp_username": "bot@example.com",
                        "smtp_password_env_var": "TOTALLY_UNSET_XYZ_VAR",
                    }
                )
            )
            os.environ.pop("TOTALLY_UNSET_XYZ_VAR", None)
            with self.assertRaises(NotificationConfigError) as ctx:
                send_configured_notification("body", path)
            self.assertIn("TOTALLY_UNSET_XYZ_VAR", str(ctx.exception))

    def test_config_summary_never_includes_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notification_config.json"
            path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "recipient": "me@example.com",
                        "smtp_host": "smtp.example.com",
                        "smtp_username": "bot@example.com",
                        "smtp_password_env_var": "SOME_VAR",
                    }
                )
            )
            os.environ["SOME_VAR"] = "super-secret-password"
            try:
                summary = notification_config_summary(path)
            finally:
                del os.environ["SOME_VAR"]
            self.assertNotIn("super-secret-password", summary)

    def test_send_succeeds_with_full_config_and_mocked_smtp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notification_config.json"
            path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "recipient": "me@example.com",
                        "smtp_host": "smtp.example.com",
                        "smtp_username": "bot@example.com",
                        "smtp_password_env_var": "PW_VAR_XYZ",
                    }
                )
            )
            os.environ["PW_VAR_XYZ"] = "secret"
            try:
                mock_server = MagicMock()
                mock_server.__enter__ = lambda self: mock_server
                mock_server.__exit__ = lambda self, *a: None
                with patch("assistant.notifications.smtplib.SMTP", return_value=mock_server):
                    result = send_configured_notification("hello", path)
                self.assertIn("me@example.com", result)
                self.assertTrue(mock_server.send_message.called)
                sent_message = mock_server.send_message.call_args[0][0]
                self.assertEqual(str(sent_message["To"]), "me@example.com")
            finally:
                del os.environ["PW_VAR_XYZ"]

    def test_send_never_allows_caller_to_override_recipient(self) -> None:
        """The function signature itself must not accept a recipient
        argument -- the only thing a caller can influence is the body and
        an optional subject suffix.
        """
        import inspect

        signature = inspect.signature(send_configured_notification)
        self.assertNotIn("recipient", signature.parameters)
        self.assertNotIn("to", signature.parameters)


class NotificationCoreWorkflowTests(unittest.TestCase):
    def _make_assistant(self, temp_dir: str) -> LocalAssistant:
        root = Path(temp_dir)
        return LocalAssistant(
            use_llm=False,
            notification_config_path=root / "notification_config.json",
            data_export_dir=root / "exports",
        )

    def test_send_daily_summary_blocked_when_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            response = assistant.respond("send daily summary email")
            self.assertIsNone(response.pending_action)
            self.assertIn("disabled", response.text.lower())

    def test_no_conversational_command_can_set_recipient(self) -> None:
        """There must be no NL command anywhere that sets/changes the
        notification recipient -- config file editing is the only path.
        """
        core_source = Path("assistant/core.py").read_text(encoding="utf-8")
        for forbidden_phrase in ("set notification recipient", "set email recipient", "configure notification"):
            self.assertNotIn(forbidden_phrase, core_source)

    def test_send_daily_summary_end_to_end_with_mocked_smtp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            assistant.notification_config_path.parent.mkdir(parents=True, exist_ok=True)
            assistant.notification_config_path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "recipient": "me@example.com",
                        "smtp_host": "smtp.example.com",
                        "smtp_username": "bot@example.com",
                        "smtp_password_env_var": "PW_VAR_ABC",
                    }
                )
            )
            os.environ["PW_VAR_ABC"] = "secret"
            try:
                assistant.tasks_store.add("Buy milk")

                response = assistant.respond("send daily summary email")
                self.assertIsNotNone(response.pending_action)
                assert response.pending_action is not None
                self.assertEqual(response.pending_action.kind, "send_notification")
                self.assertIn("me@example.com", response.text)
                self.assertIn("Buy milk", response.pending_action.target)

                mock_server = MagicMock()
                mock_server.__enter__ = lambda self: mock_server
                mock_server.__exit__ = lambda self, *a: None
                with patch("assistant.notifications.smtplib.SMTP", return_value=mock_server):
                    result = assistant.confirm_pending_action(response.pending_action)
                self.assertIn("Sent notification email to me@example.com", result)
            finally:
                del os.environ["PW_VAR_ABC"]

    def test_send_does_not_happen_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = self._make_assistant(temp_dir)
            assistant.notification_config_path.parent.mkdir(parents=True, exist_ok=True)
            assistant.notification_config_path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "recipient": "me@example.com",
                        "smtp_host": "smtp.example.com",
                        "smtp_username": "bot@example.com",
                        "smtp_password_env_var": "PW_VAR_DEF",
                    }
                )
            )
            os.environ["PW_VAR_DEF"] = "secret"
            try:
                with patch("assistant.notifications.smtplib.SMTP") as mock_smtp:
                    assistant.respond("send daily summary email")
                    mock_smtp.assert_not_called()
            finally:
                del os.environ["PW_VAR_DEF"]


if __name__ == "__main__":
    unittest.main()
