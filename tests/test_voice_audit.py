import json
import tempfile
import unittest
from pathlib import Path

from assistant.voice_audit import VoiceActionAuditStore


class VoiceAuditTests(unittest.TestCase):
    def test_missing_voice_audit_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = VoiceActionAuditStore(Path(temp_dir) / "voice.jsonl")

            self.assertEqual(store.recent(), [])
            self.assertIn("No saved voice action audit", store.summary())

    def test_records_text_summary_without_audio_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "voice.jsonl"
            store = VoiceActionAuditStore(path)

            store.record(
                event="action_preview",
                command_text="open calculator",
                confidence_level="low",
                action_description="Open calculator",
                result="Pending confirmation.",
            )

            entries = store.recent()
            raw_text = path.read_text(encoding="utf-8")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].command_text, "open calculator")
        self.assertEqual(entries[0].confidence_level, "low")
        self.assertNotIn("audio", raw_text.lower())
        self.assertNotIn("wav", raw_text.lower())

    def test_disabled_voice_audit_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "voice.jsonl"
            store = VoiceActionAuditStore(path, enabled=False)

            store.record("recognized", "hello", "high")

            self.assertFalse(path.exists())

    def test_filters_by_confidence_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = VoiceActionAuditStore(Path(temp_dir) / "voice.jsonl")
            store.record("recognized", "hello", "high")
            store.record("action_preview", "open calculator", "low")

            low_entries = store.filtered(confidence_level="low")
            preview_entries = store.filtered(event="action_preview")

        self.assertEqual([entry.command_text for entry in low_entries], ["open calculator"])
        self.assertEqual([entry.event for entry in preview_entries], ["action_preview"])

    def test_summary_names_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = VoiceActionAuditStore(Path(temp_dir) / "voice.jsonl")
            store.record("action_preview", "open calculator", "low")

            text = store.summary(confidence_level="low")

        self.assertIn("confidence=low", text)
        self.assertIn("open calculator", text)

    def test_export_writes_local_text_only_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = VoiceActionAuditStore(root / "voice.jsonl")
            store.record("recognized", "hello", "high")
            store.record("action_preview", "open calculator", "low")

            export_dir = store.export(root / "exports", confidence_level="low")
            manifest = json.loads((export_dir / "voice_action_audit.json").read_text())

        self.assertEqual(manifest["schema"], "voice_action_audit_export_v1")
        self.assertEqual(manifest["filters"]["confidence_level"], "low")
        self.assertEqual(manifest["entry_count"], 1)
        self.assertEqual(manifest["entries"][0]["command_text"], "open calculator")
        self.assertNotIn("audio_data", json.dumps(manifest).lower())

    def test_retention_preview_does_not_change_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "voice.jsonl"
            store = VoiceActionAuditStore(path)
            store.record("recognized", "first", "high")
            store.record("recognized", "second", "high")
            before = path.read_text(encoding="utf-8")

            preview = store.retention_preview(keep_latest=1)
            after = path.read_text(encoding="utf-8")

        self.assertEqual(preview.total_entries, 2)
        self.assertEqual(preview.remove_count, 1)
        self.assertEqual(before, after)

    def test_prune_keep_latest_writes_backup_before_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = VoiceActionAuditStore(root / "voice.jsonl")
            store.record("recognized", "first", "high")
            store.record("action_preview", "second", "low")
            store.record("recognized", "third", "high")

            result = store.prune_keep_latest(2, backup_dir=root / "retention")
            entries = store.recent(limit=10)
            backup_dirs = list((root / "retention").glob("voice-audit-retention-*"))
            manifest = json.loads((backup_dirs[0] / "manifest.json").read_text())
            before_backup_exists = (backup_dirs[0] / "voice_action_audit_before.jsonl").exists()

        self.assertEqual(result.removed_entries, 1)
        self.assertEqual([entry.command_text for entry in entries], ["second", "third"])
        self.assertEqual(manifest["schema"], "voice_action_audit_retention_backup_v1")
        self.assertEqual(manifest["removed_entries"], 1)
        self.assertTrue(before_backup_exists)
        self.assertNotIn("audio_data", json.dumps(manifest).lower())


if __name__ == "__main__":
    unittest.main()
