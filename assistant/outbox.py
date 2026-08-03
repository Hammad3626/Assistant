"""Local draft outbox for messages, emails, and network requests.

Drafts are intentionally local-only. This module does not send messages, send
emails, or perform network requests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_OUTBOX_PATH = Path("data/outbox.json")
ALLOWED_REQUEST_METHODS = {"GET", "POST"}


class OutboxError(RuntimeError):
    """Raised when local outbox drafts cannot be read or written."""


@dataclass(frozen=True)
class OutboxDraft:
    kind: str
    target: str
    body: str
    created_at: str
    subject: str | None = None
    method: str | None = None

    def display_text(self) -> str:
        if self.kind == "email":
            subject = self.subject or "(no subject)"
            return f"email to {self.target} subject '{subject}': {self.body}"
        if self.kind == "network_request":
            method = self.method or "GET"
            return f"network request {method} {self.target}: {self.body}"
        return f"message to {self.target}: {self.body}"


class OutboxStore:
    """Append-only local draft outbox."""

    def __init__(self, path: str | Path = DEFAULT_OUTBOX_PATH) -> None:
        self.path = Path(path)

    def draft_message(self, recipient: str, body: str) -> OutboxDraft:
        clean_recipient = _clean_required_text(recipient, "Recipient")
        clean_body = _clean_required_text(body, "Message body")
        draft = OutboxDraft(
            kind="message",
            target=clean_recipient,
            body=clean_body,
            created_at=_utc_now_iso(),
        )
        self._append(draft)
        return draft

    def draft_email(self, recipient: str, subject: str, body: str) -> OutboxDraft:
        clean_recipient = _clean_required_text(recipient, "Recipient")
        clean_subject = _clean_required_text(subject, "Email subject")
        clean_body = _clean_required_text(body, "Email body")
        draft = OutboxDraft(
            kind="email",
            target=clean_recipient,
            subject=clean_subject,
            body=clean_body,
            created_at=_utc_now_iso(),
        )
        self._append(draft)
        return draft

    def draft_network_request(self, method: str, url: str, note: str = "") -> OutboxDraft:
        clean_method = method.strip().upper()
        if clean_method not in ALLOWED_REQUEST_METHODS:
            raise OutboxError("Network request draft method must be GET or POST.")
        clean_url = _validate_url(url)
        clean_note = " ".join(note.strip().split()) if note.strip() else "(no request body or note)"
        draft = OutboxDraft(
            kind="network_request",
            target=clean_url,
            method=clean_method,
            body=clean_note,
            created_at=_utc_now_iso(),
        )
        self._append(draft)
        return draft

    def list_drafts(self) -> list[OutboxDraft]:
        raw = self._read_raw()
        drafts_raw = raw.get("drafts", [])
        if not isinstance(drafts_raw, list):
            raise OutboxError("Outbox file has invalid 'drafts' value.")

        drafts: list[OutboxDraft] = []
        for item in drafts_raw:
            if not isinstance(item, dict):
                continue
            draft = _draft_from_raw(item)
            if draft is not None:
                drafts.append(draft)
        return drafts

    def summary(self, limit: int = 10) -> str:
        drafts = self.list_drafts()
        if not drafts:
            return "Outbox drafts: none. Nothing has been sent."

        lines = ["Outbox drafts (local only, not sent):"]
        for index, draft in enumerate(drafts[-limit:], start=1):
            lines.append(f"{index}. [{draft.kind}] {draft.display_text()} ({draft.created_at})")
        if len(drafts) > limit:
            lines.append(f"Showing latest {limit} of {len(drafts)} draft(s).")
        return "\n".join(lines)

    def clear(self) -> int:
        drafts = self.list_drafts()
        self._write_all([])
        return len(drafts)

    def _append(self, draft: OutboxDraft) -> None:
        drafts = self.list_drafts()
        drafts.append(draft)
        self._write_all(drafts)

    def _read_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"drafts": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise OutboxError(f"Invalid outbox JSON: {self.path}") from exc
        except OSError as exc:
            raise OutboxError(f"Could not read outbox: {self.path}") from exc
        if not isinstance(raw, dict):
            raise OutboxError("Outbox file must contain a JSON object.")
        return raw

    def _write_all(self, drafts: list[OutboxDraft]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {"drafts": [_draft_to_raw(draft) for draft in drafts]}
        try:
            self.path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise OutboxError(f"Could not write outbox: {self.path}") from exc


def blocked_send_text() -> str:
    return (
        "Sending is not enabled. I can create a local draft instead: "
        "draft message to <recipient>: <text>, draft email to <recipient> subject <subject>: <text>, "
        "or draft network request GET <url>."
    )


def _clean_required_text(text: str, label: str) -> str:
    clean = " ".join(text.strip().split())
    if not clean:
        raise OutboxError(f"{label} cannot be empty.")
    return clean


def _validate_url(url: str) -> str:
    clean = url.strip()
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OutboxError("Network request draft URL must start with http:// or https://.")
    return clean


def _draft_to_raw(draft: OutboxDraft) -> dict[str, str | None]:
    return {
        "kind": draft.kind,
        "target": draft.target,
        "subject": draft.subject,
        "method": draft.method,
        "body": draft.body,
        "created_at": draft.created_at,
    }


def _draft_from_raw(raw: dict[str, Any]) -> OutboxDraft | None:
    kind = raw.get("kind")
    target = raw.get("target")
    body = raw.get("body")
    created_at = raw.get("created_at")
    subject = raw.get("subject")
    method = raw.get("method")
    if not all(isinstance(value, str) for value in (kind, target, body, created_at)):
        return None
    return OutboxDraft(
        kind=kind,
        target=target,
        subject=subject if isinstance(subject, str) else None,
        method=method if isinstance(method, str) else None,
        body=body,
        created_at=created_at,
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
