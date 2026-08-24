"""A single, deliberately narrow, pre-approved outbound email notification.

This is NOT a general "send messages/emails to anyone" capability. By
design:
- There is exactly one recipient, one subject template, and one SMTP
  account, all set once via a local config file
  (config/notification_config.json) that must be edited directly on disk.
- There is no conversational command anywhere in this app that can set or
  change the recipient, subject, or SMTP host. If there were, that would
  reopen the "send arbitrary things to arbitrary people" risk this design
  exists to avoid.
- The SMTP password is never stored in the config file. It is read from an
  environment variable whose *name* is stored in the config
  (smtp_password_env_var), so the actual secret lives outside the repo and
  outside anything the assistant ever writes.
- Sending is disabled by default (`enabled: false`) and requires the
  person to explicitly opt in by editing the config file themselves.
- Every send still goes through the normal PendingAction confirmation flow
  in core.py before anything is actually sent.
"""

from __future__ import annotations

import json
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


DEFAULT_NOTIFICATION_CONFIG_PATH = Path("config/notification_config.json")
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_TIMEOUT_SECONDS = 15


class NotificationConfigError(RuntimeError):
    """Raised when the notification config is missing, incomplete, or disabled."""


@dataclass(frozen=True)
class NotificationConfig:
    enabled: bool = False
    recipient: str = ""
    subject_template: str = "Assistant Notification"
    smtp_host: str = ""
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_username: str = ""
    smtp_password_env_var: str = "ASSISTANT_SMTP_PASSWORD"
    use_tls: bool = True


def default_notification_config_payload() -> dict[str, object]:
    return {
        "enabled": False,
        "recipient": "",
        "subject_template": "Assistant Notification",
        "smtp_host": "",
        "smtp_port": DEFAULT_SMTP_PORT,
        "smtp_username": "",
        "smtp_password_env_var": "ASSISTANT_SMTP_PASSWORD",
        "use_tls": True,
    }


def load_notification_config(
    path: str | Path = DEFAULT_NOTIFICATION_CONFIG_PATH,
) -> NotificationConfig:
    config_path = Path(path)
    if not config_path.exists():
        return NotificationConfig()

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise NotificationConfigError(f"Invalid notification config JSON: {config_path}") from exc
    except OSError as exc:
        raise NotificationConfigError(f"Could not read notification config: {config_path}") from exc

    if not isinstance(raw, dict):
        raise NotificationConfigError("Notification config must be a JSON object.")

    defaults = default_notification_config_payload()
    merged = {**defaults, **raw}

    return NotificationConfig(
        enabled=bool(merged.get("enabled", False)),
        recipient=str(merged.get("recipient", "")).strip(),
        subject_template=str(merged.get("subject_template", defaults["subject_template"])),
        smtp_host=str(merged.get("smtp_host", "")).strip(),
        smtp_port=int(merged.get("smtp_port", DEFAULT_SMTP_PORT)),
        smtp_username=str(merged.get("smtp_username", "")).strip(),
        smtp_password_env_var=str(
            merged.get("smtp_password_env_var", "ASSISTANT_SMTP_PASSWORD")
        ).strip()
        or "ASSISTANT_SMTP_PASSWORD",
        use_tls=bool(merged.get("use_tls", True)),
    )


def notification_config_summary(path: str | Path = DEFAULT_NOTIFICATION_CONFIG_PATH) -> str:
    """Safe, password-free summary of the current notification config."""
    try:
        config = load_notification_config(path)
    except NotificationConfigError as exc:
        return f"Notification config error: {exc}"

    if not config.enabled:
        return (
            "Email notifications are disabled. To enable, edit "
            f"{Path(path)} directly (recipient, subject_template, smtp_host, "
            "smtp_port, smtp_username, smtp_password_env_var, enabled: true), "
            "and set the SMTP password in the environment variable named in "
            "smtp_password_env_var. This cannot be configured through chat."
        )
    return (
        "Email notifications: enabled\n"
        f"Recipient: {config.recipient or '(not set)'}\n"
        f"Subject template: {config.subject_template}\n"
        f"SMTP host: {config.smtp_host or '(not set)'}:{config.smtp_port}\n"
        f"SMTP username: {config.smtp_username or '(not set)'}\n"
        f"Password read from environment variable: {config.smtp_password_env_var}"
    )


def _validate_ready_to_send(config: NotificationConfig) -> None:
    if not config.enabled:
        raise NotificationConfigError(
            "Email notifications are disabled. Enable them by editing "
            f"{DEFAULT_NOTIFICATION_CONFIG_PATH} directly; this cannot be done through chat."
        )
    missing = [
        field_name
        for field_name, value in (
            ("recipient", config.recipient),
            ("smtp_host", config.smtp_host),
            ("smtp_username", config.smtp_username),
        )
        if not value
    ]
    if missing:
        raise NotificationConfigError(
            f"Notification config is incomplete, missing: {', '.join(missing)}. "
            f"Edit {DEFAULT_NOTIFICATION_CONFIG_PATH} directly to set them."
        )
    if not os.environ.get(config.smtp_password_env_var):
        raise NotificationConfigError(
            f"SMTP password environment variable '{config.smtp_password_env_var}' is not set."
        )


def send_configured_notification(
    body: str,
    config_path: str | Path = DEFAULT_NOTIFICATION_CONFIG_PATH,
    subject_suffix: str | None = None,
) -> str:
    """Send an email to the single pre-approved, config-defined recipient.

    The recipient, subject template, and SMTP account all come from the
    config file only -- none of them can be supplied by the caller. The
    caller may only supply the message body (and an optional short subject
    suffix, e.g. a date), never the destination.
    """
    config = load_notification_config(config_path)
    _validate_ready_to_send(config)

    password = os.environ[config.smtp_password_env_var]
    subject = config.subject_template
    if subject_suffix:
        subject = f"{subject} - {subject_suffix}"

    message = EmailMessage()
    message["From"] = config.smtp_username
    message["To"] = config.recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=DEFAULT_SMTP_TIMEOUT_SECONDS) as server:
            if config.use_tls:
                server.starttls()
            server.login(config.smtp_username, password)
            server.send_message(message)
    except smtplib.SMTPException as exc:
        raise NotificationConfigError(f"Failed to send notification email: {exc}") from exc
    except OSError as exc:
        raise NotificationConfigError(f"Failed to connect to SMTP server: {exc}") from exc

    return f"Sent notification email to {config.recipient} (subject: {subject})."
