"""Check local text-only voice action audit summaries."""

from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.voice_audit import VoiceActionAuditStore


def main() -> int:
    print("Local PC Assistant voice action audit check")

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "voice_action_audit.jsonl"
        store = VoiceActionAuditStore(path)
        store.record(
            event="action_preview",
            command_text="open calculator",
            confidence_level="low",
            action_description="Open calculator",
            result="Pending confirmation.",
        )
        store.record(
            event="recognized",
            command_text="hello",
            confidence_level="high",
            result="Recognized.",
        )
        response = LocalAssistant(use_llm=False, voice_action_audit_store=store).respond(
            "voice audit"
        )
        filtered = LocalAssistant(use_llm=False, voice_action_audit_store=store).respond(
            "voice audit confidence low"
        )
        exported = LocalAssistant(
            use_llm=False,
            voice_action_audit_store=store,
            data_export_dir=Path(temp_dir) / "exports",
        ).respond("export voice audit event action_preview")
        retention_assistant = LocalAssistant(
            use_llm=False,
            voice_action_audit_store=store,
            data_export_dir=Path(temp_dir) / "exports",
        )
        retention_preview = retention_assistant.respond("voice audit retention keep 1")
        prune_response = retention_assistant.respond("prune voice audit keep 1")
        prune_result = ""
        if prune_response.pending_action is not None:
            prune_result = retention_assistant.confirm_pending_action(prune_response.pending_action)
        pruned_entries = store.recent(limit=10)
        raw_text = path.read_text(encoding="utf-8")
        empty_path = Path(temp_dir) / "empty_voice_action_audit.jsonl"
        empty = LocalAssistant(
            use_llm=False,
            voice_action_audit_store=VoiceActionAuditStore(empty_path),
        ).respond("voice audit")

    print(response.text)
    required = ("Recent voice action audit entries", "open calculator", "Audio is never stored")
    missing = [text for text in required if text not in response.text]
    if missing:
        print(f"ERROR: Voice audit summary missing: {', '.join(missing)}")
        return 1
    blocked_terms = ("audio", "wav", "pcm")
    lower_raw = raw_text.lower()
    if "audio" in lower_raw or "wav" in lower_raw or "pcm" in lower_raw:
        print("ERROR: Voice audit raw record contains audio-related payload fields.")
        return 1

    if "confidence=low" not in filtered.text or "hello" in filtered.text:
        print("ERROR: Voice audit confidence filter did not return the expected entries.")
        return 1
    if "Voice action audit export created" not in exported.text or "No audio was exported" not in exported.text:
        print("ERROR: Voice audit export did not report a local no-audio export.")
        return 1
    if "No changes were made" not in retention_preview.text or "Would remove: 1" not in retention_preview.text:
        print("ERROR: Voice audit retention preview did not report the expected dry run.")
        return 1
    if prune_response.pending_action is None or "Voice action audit retention applied" not in prune_result:
        print("ERROR: Voice audit retention prune did not require confirmation and apply cleanly.")
        return 1
    if [entry.command_text for entry in pruned_entries] != ["hello"]:
        print("ERROR: Voice audit retention did not keep the latest entry only.")
        return 1
    if "No saved voice action audit entries" not in empty.text:
        print("ERROR: Empty voice audit message is missing.")
        return 1

    print("OK: Voice action audit stores local text summaries only and supports confirmed retention.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
