"""Privacy-preserving JSONL audit summaries for voice commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_VOICE_AUDIT_PATH = Path("data/voice_action_audit.jsonl")


class VoiceAuditError(RuntimeError):
    """Raised when the local voice audit log cannot be read or written."""


@dataclass(frozen=True)
class VoiceAuditEntry:
    event: str
    command_text: str
    confidence_level: str
    action_description: str
    result: str
    created_at: str


@dataclass(frozen=True)
class VoiceAuditRetentionPreview:
    total_entries: int
    keep_latest: int
    remove_count: int

    def summary(self) -> str:
        return (
            "Voice action audit retention preview\n"
            "No changes were made.\n"
            "Audio is never stored; retention only affects local text summaries.\n"
            f"Total entries: {self.total_entries}\n"
            f"Keep latest: {self.keep_latest}\n"
            f"Would remove: {self.remove_count}"
        )


@dataclass(frozen=True)
class VoiceAuditRetentionResult:
    total_entries: int
    kept_entries: int
    removed_entries: int
    backup_dir: Path | None

    def summary(self) -> str:
        if self.removed_entries <= 0:
            return (
                "Voice action audit retention applied\n"
                "No entries were removed.\n"
                f"Total entries: {self.total_entries}\n"
                f"Keep latest: {self.kept_entries}"
            )
        return (
            "Voice action audit retention applied\n"
            "A local backup was written before the audit file was changed.\n"
            "Audio was not backed up or stored.\n"
            f"Total entries before: {self.total_entries}\n"
            f"Kept entries: {self.kept_entries}\n"
            f"Removed entries: {self.removed_entries}\n"
            f"Backup folder: {self.backup_dir}"
        )


class VoiceActionAuditStore:
    """Append-only local summaries for voice actions; audio is never stored."""

    def __init__(
        self,
        path: str | Path = DEFAULT_VOICE_AUDIT_PATH,
        enabled: bool = True,
    ) -> None:
        self.path = Path(path)
        self.enabled = enabled

    def record(
        self,
        event: str,
        command_text: str,
        confidence_level: str | None,
        action_description: str = "",
        result: str = "",
    ) -> None:
        if not self.enabled:
            return

        entry = {
            "event": event,
            "command_text": command_text.strip(),
            "confidence_level": confidence_level or "unknown",
            "action_description": action_description.strip(),
            "result": result.strip(),
            "created_at": _utc_now_iso(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 10) -> list[VoiceAuditEntry]:
        if not self.path.exists() or limit <= 0:
            return []

        try:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            raise VoiceAuditError(f"Could not read voice action audit log: {self.path}") from exc

        entries: list[VoiceAuditEntry] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                raw: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            entry = _entry_from_raw(raw)
            if entry:
                entries.append(entry)
        return entries

    def filtered(
        self,
        event: str | None = None,
        confidence_level: str | None = None,
        limit: int = 10,
    ) -> list[VoiceAuditEntry]:
        """Return recent entries filtered by event or confidence level."""
        entries = self.recent(limit=1_000_000)
        if event:
            entries = [entry for entry in entries if entry.event == event]
        if confidence_level:
            entries = [
                entry for entry in entries if entry.confidence_level == confidence_level
            ]
        if limit <= 0:
            return []
        return entries[-limit:]

    def summary(
        self,
        limit: int = 10,
        event: str | None = None,
        confidence_level: str | None = None,
    ) -> str:
        entries = self.filtered(event=event, confidence_level=confidence_level, limit=limit)
        if not entries:
            if event or confidence_level:
                filters = _filter_text(event, confidence_level)
                return (
                    f"No saved voice action audit entries matched {filters}.\n"
                    "Audio is never stored; only local text summaries are saved when voice mode runs."
                )
            return (
                "No saved voice action audit entries.\n"
                "Audio is never stored; only local text summaries are saved when voice mode runs."
            )

        title = "Recent voice action audit entries"
        if event or confidence_level:
            title += f" matching {_filter_text(event, confidence_level)}"
        lines = [
            f"{title}:",
            "Audio is never stored; entries contain recognized text and safety status only.",
        ]
        for entry in entries:
            detail = f"{entry.event}: '{entry.command_text}' ({entry.confidence_level})"
            if entry.action_description:
                detail += f" -> {entry.action_description}"
            if entry.result:
                detail += f" => {entry.result}"
            lines.append(detail)
        return "\n".join(lines)

    def export(
        self,
        output_dir: str | Path = "exports/voice-audit-exports",
        event: str | None = None,
        confidence_level: str | None = None,
    ) -> Path:
        """Write matching text-only voice audit entries to a local export folder."""
        entries = self.filtered(event=event, confidence_level=confidence_level, limit=1_000_000)
        export_root = Path(output_dir)
        export_dir = _next_export_dir(export_root)
        try:
            export_dir.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise VoiceAuditError(f"Could not create voice audit export: {export_dir}") from exc
        manifest = {
            "schema": "voice_action_audit_export_v1",
            "created_at": _utc_now_iso(),
            "source_path": str(self.path),
            "filters": {
                "event": event or "",
                "confidence_level": confidence_level or "",
            },
            "entry_count": len(entries),
            "privacy": "Text summaries only. Audio and recognizer payloads are not stored.",
            "entries": [entry.__dict__ for entry in entries],
        }
        try:
            (export_dir / "voice_action_audit.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise VoiceAuditError(f"Could not write voice audit export: {export_dir}") from exc
        return export_dir

    def retention_preview(self, keep_latest: int) -> VoiceAuditRetentionPreview:
        """Preview how many text audit entries would be kept or removed."""
        keep_latest = _validate_keep_latest(keep_latest)
        total_entries = len(self.recent(limit=1_000_000))
        return VoiceAuditRetentionPreview(
            total_entries=total_entries,
            keep_latest=keep_latest,
            remove_count=max(0, total_entries - keep_latest),
        )

    def prune_keep_latest(
        self,
        keep_latest: int,
        backup_dir: str | Path = "exports/voice-audit-retention",
    ) -> VoiceAuditRetentionResult:
        """Keep the latest text audit entries after writing a local backup."""
        keep_latest = _validate_keep_latest(keep_latest)
        entries = self.recent(limit=1_000_000)
        total_entries = len(entries)
        remove_count = max(0, total_entries - keep_latest)
        if remove_count <= 0:
            return VoiceAuditRetentionResult(
                total_entries=total_entries,
                kept_entries=total_entries,
                removed_entries=0,
                backup_dir=None,
            )

        export_root = Path(backup_dir)
        backup_path = _next_export_dir(export_root, prefix="voice-audit-retention")
        try:
            backup_path.mkdir(parents=True, exist_ok=False)
            original_text = self.path.read_text(encoding="utf-8-sig") if self.path.exists() else ""
            (backup_path / "voice_action_audit_before.jsonl").write_text(
                original_text,
                encoding="utf-8",
            )
            kept_entries = entries[-keep_latest:]
            manifest = {
                "schema": "voice_action_audit_retention_backup_v1",
                "created_at": _utc_now_iso(),
                "source_path": str(self.path),
                "total_entries_before": total_entries,
                "kept_entries": len(kept_entries),
                "removed_entries": remove_count,
                "privacy": "Text summaries only. Audio and recognizer payloads are not stored.",
            }
            (backup_path / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                "".join(
                    json.dumps(entry.__dict__, ensure_ascii=False) + "\n"
                    for entry in kept_entries
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            raise VoiceAuditError(
                f"Could not apply voice audit retention safely: {self.path}"
            ) from exc

        return VoiceAuditRetentionResult(
            total_entries=total_entries,
            kept_entries=keep_latest,
            removed_entries=remove_count,
            backup_dir=backup_path,
        )

    def clear(self) -> int:
        count = len(self.recent(limit=1_000_000))
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")
        return count


def _entry_from_raw(raw: dict[str, Any]) -> VoiceAuditEntry | None:
    fields = {
        "event",
        "command_text",
        "confidence_level",
        "action_description",
        "result",
        "created_at",
    }
    if not all(isinstance(raw.get(field), str) for field in fields):
        return None
    return VoiceAuditEntry(
        event=raw["event"],
        command_text=raw["command_text"],
        confidence_level=raw["confidence_level"],
        action_description=raw["action_description"],
        result=raw["result"],
        created_at=raw["created_at"],
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _validate_keep_latest(keep_latest: int) -> int:
    if keep_latest < 1:
        raise VoiceAuditError("Retention keep count must be at least 1.")
    return keep_latest


def _next_export_dir(export_root: Path, prefix: str = "voice-audit") -> Path:
    base = export_root / f"{prefix}-{_timestamp_slug()}"
    if not base.exists():
        return base
    for index in range(2, 100):
        candidate = export_root / f"{base.name}-{index}"
        if not candidate.exists():
            return candidate
    raise VoiceAuditError("Could not allocate a unique voice audit export folder.")


def _filter_text(event: str | None, confidence_level: str | None) -> str:
    parts = []
    if event:
        parts.append(f"event={event}")
    if confidence_level:
        parts.append(f"confidence={confidence_level}")
    return ", ".join(parts) if parts else "all entries"
