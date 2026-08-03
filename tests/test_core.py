import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from assistant.core import LocalAssistant
from assistant.audit import ActionAuditStore
from assistant.aliases import save_aliases
from assistant.file_type_allowlist import FileSignerInfo
from assistant.history import HistoryStore
from assistant.launch_requests import LaunchRequestStore
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.outbox import OutboxStore
from assistant.shell_tools import add_shell_command
from assistant.tasks import TasksStore
from assistant.voice_audit import VoiceActionAuditStore


class FakeLlmClient:
    def __init__(self) -> None:
        self.last_prompt: str | None = None
        self.last_memory_context: str | None = None

    def generate(self, prompt: str, memory_context: str | None = None) -> str:
        self.last_prompt = prompt
        self.last_memory_context = memory_context
        return f"fake local answer for: {prompt}"


class FailingLlmClient:
    def generate(self, prompt: str, memory_context: str | None = None) -> str:
        raise RuntimeError("Ollama is not reachable.")


class FakeStatus:
    def summary(self) -> str:
        return "Local assistant status\nAssistant: Test"


class LocalAssistantTests(unittest.TestCase):
    def test_help_lists_available_commands(self) -> None:
        assistant = LocalAssistant()

        response = assistant.respond("help")

        self.assertIn("Available commands", response.text)
        self.assertIn("command reference", response.text)
        self.assertIn("help tasks", response.text)
        self.assertIn("about", response.text)
        self.assertIn("safety", response.text)
        self.assertIn("roadmap", response.text)
        self.assertIn("models", response.text)
        self.assertIn("voice status", response.text)
        self.assertIn("wake status", response.text)
        self.assertIn("paths", response.text)
        self.assertFalse(response.should_exit)

    @patch("assistant.core.voice_status_text", return_value="Voice status\nInput model found: yes")
    def test_voice_status_command(self, mock_voice_status) -> None:
        assistant = LocalAssistant(use_llm=False, voice_model_path="custom-voice-model")

        response = assistant.respond("voice status")

        self.assertIn("Voice status", response.text)
        mock_voice_status.assert_called_once_with("custom-voice-model")

    def test_wake_status_command(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("wake status")

        self.assertIn("Wake voice loop", response.text)
        self.assertIn("--wake --speak", response.text)

    def test_voice_confidence_command(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("voice confidence")

        self.assertIn("Voice confidence reporting", response.text)
        self.assertIn("read-only", response.text)

    def test_voice_safety_drill_command(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("voice safety drill")

        self.assertIn("Voice safety drill", response.text)
        self.assertIn("Read-only simulation", response.text)
        self.assertIn("confirm action", response.text)
        self.assertIsNone(response.pending_action)

    def test_paths_command_lists_local_files(self) -> None:
        assistant = LocalAssistant(
            use_llm=False,
            settings_path="custom-settings.json",
            persona_path="custom-persona.txt",
            voice_model_path="custom-voice-model",
        )

        response = assistant.respond("paths")

        self.assertIn("Local assistant paths", response.text)
        self.assertIn("Settings: custom-settings.json", response.text)
        self.assertIn("Persona: custom-persona.txt", response.text)
        self.assertIn("Voice model: custom-voice-model", response.text)

    @patch("assistant.core.detected_folders_summary", return_value="Detected Windows folders (read-only):")
    def test_detected_folders_command_is_read_only(self, mock_summary) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("detected folders")

        self.assertIn("Detected Windows folders", response.text)
        mock_summary.assert_called_once_with()

    @patch("assistant.core.detected_drives_summary", return_value="Detected Windows drives (read-only):")
    def test_detected_drives_command_is_read_only(self, mock_summary) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("windows drives")

        self.assertIn("Detected Windows drives", response.text)
        mock_summary.assert_called_once_with()

    def test_focused_help_topic(self) -> None:
        assistant = LocalAssistant()

        response = assistant.respond("help tasks")

        self.assertIn("Help: tasks", response.text)
        self.assertIn("todo <task>", response.text)

    def test_about_command_lists_architecture(self) -> None:
        assistant = LocalAssistant(name="Eva", use_llm=False)

        response = assistant.respond("architecture")

        self.assertIn("About Eva", response.text)
        self.assertIn("Architecture:", response.text)
        self.assertIn("Ollama", response.text)

    def test_safety_command_lists_permissions(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("permissions")

        self.assertIn("Safety and permissions", response.text)
        self.assertIn("Requires confirmation:", response.text)
        self.assertIn("Blocked:", response.text)

    def test_permissions_dashboard_lists_safety_limited_features(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("permissions dashboard")

        self.assertIn("Permissions dashboard", response.text)
        self.assertIn("Shell commands: named allowlist with guided editor", response.text)
        self.assertIn("Bulk file modification: dry-run, backup, approval, review, rollback-plan, hashed signed preflight, verified checklist, and design only", response.text)
        self.assertIn("Messages, email, network: draft-only", response.text)

    def test_roadmap_command_lists_next_steps(self) -> None:
        assistant = LocalAssistant(name="Eva", use_llm=False)

        response = assistant.respond("next steps")

        self.assertIn("Eva roadmap", response.text)
        self.assertIn("Working now:", response.text)
        self.assertIn("Recommended next upgrades:", response.text)

    def test_script_allowlist_design_command_is_read_only(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("design script allowlist")

        self.assertIsNone(response.pending_action)
        self.assertIn("Explicit script allowlist design", response.text)
        self.assertIn("No scripts are allowlisted or executed", response.text)

    def test_launch_commands_lists_startup_commands(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("launch commands")

        self.assertIn("Launch commands", response.text)
        self.assertIn("python -m assistant.cli", response.text)
        self.assertIn("python -m assistant.gui", response.text)

    def test_command_reference_lists_categories(self) -> None:
        assistant = LocalAssistant()

        response = assistant.respond("command reference")

        self.assertIn("Command reference", response.text)
        self.assertIn("Memory:", response.text)
        self.assertIn("Safe local actions:", response.text)
        self.assertFalse(response.should_exit)

    def test_exit_marks_session_done(self) -> None:
        assistant = LocalAssistant()

        response = assistant.respond("exit")

        self.assertEqual(response.text, "Goodbye.")
        self.assertTrue(response.should_exit)

    def test_unknown_command_is_safe_refusal(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("delete my downloads")

        self.assertIn("do not know how", response.text)
        self.assertFalse(response.should_exit)

    def test_unknown_typo_suggests_command_without_llm(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("memoris")

        self.assertIn("Did you mean", response.text)
        self.assertIn("memories", response.text)
        self.assertFalse(response.should_exit)

    def test_unknown_typo_suggests_command_before_llm(self) -> None:
        assistant = LocalAssistant(llm_client=FakeLlmClient())

        response = assistant.respond("opne calculator")

        self.assertIn("Did you mean", response.text)
        self.assertIn("open calculator", response.text)

    def test_allowed_action_requires_confirmation(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("open calculator")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)

    @patch("assistant.actions._drive_exists", return_value=True)
    def test_windows_drive_action_requires_confirmation(self, mock_drive_exists) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("open D drive")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)
        assert response.pending_action is not None
        self.assertEqual(response.pending_action.kind, "folder")
        self.assertEqual(response.pending_action.target, "D:\\")

    def test_windows_special_actions_require_confirmation(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        this_pc = assistant.respond("open this pc")
        settings = assistant.respond("open settings")

        self.assertIn("Please confirm", this_pc.text)
        self.assertIn("Please confirm", settings.text)
        assert this_pc.pending_action is not None
        assert settings.pending_action is not None
        self.assertEqual(this_pc.pending_action.kind, "special")
        self.assertEqual(settings.pending_action.target, "ms-settings:")

    def test_chrome_action_requires_confirmation(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("open chrome")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)
        assert response.pending_action is not None
        self.assertTrue(response.pending_action.target.lower().endswith("chrome.exe"))

    def test_natural_open_phrase_uses_existing_confirmation_gate(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("open google chrome")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)
        assert response.pending_action is not None
        self.assertEqual(response.pending_action.kind, "app")

    @patch("assistant.actions._drive_exists", return_value=True)
    def test_natural_drive_phrase_requires_confirmation(self, mock_drive_exists) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("open drive d")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)
        assert response.pending_action is not None
        self.assertEqual(response.pending_action.target, "D:\\")

    def test_natural_memory_and_task_phrases_use_existing_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = LocalAssistant(
                use_llm=False,
                memory_store=MemoryStore(Path(temp_dir) / "memory.json"),
                tasks_store=TasksStore(Path(temp_dir) / "tasks.json"),
            )

            memory_response = assistant.respond("save memory that I prefer short answers")
            task_response = assistant.respond("remind me to call dentist")
            tasks_response = assistant.respond("show my tasks")

        self.assertIn("Remembered: I prefer short answers", memory_response.text)
        self.assertEqual(task_response.text, "Added task: call dentist")
        self.assertIn("call dentist", tasks_response.text)

    def test_lists_allowed_actions(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("actions")

        self.assertIn("Allowed apps", response.text)
        self.assertIsNone(response.pending_action)

    def test_unlisted_launch_attempt_is_blocked_with_request_guidance(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("open mystery app")

        self.assertIn("Unlisted apps, scripts, files, and folders cannot open", response.text)
        self.assertIsNone(response.pending_action)

    def test_launch_request_commands_save_local_review_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "report.pdf"
            document.write_text("local test", encoding="utf-8")
            folder = root / "archive"
            folder.mkdir()
            store = LaunchRequestStore(
                root / "launch_requests.json",
                file_type_allowlist_path=root / "file_types.json",
            )
            assistant = LocalAssistant(use_llm=False, launch_request_store=store)

            app_response = assistant.respond("request app paint: mspaint.exe")
            script_response = assistant.respond("request script review cleanup: tools/cleanup.py")
            file_response = assistant.respond(f"request file review report: {document}")
            folder_response = assistant.respond(f"request folder review archive: {folder}")
            list_response = assistant.respond("launch requests")

        self.assertIn("Launch request saved locally, not run", app_response.text)
        self.assertIn("Script review request saved locally, not run", script_response.text)
        self.assertIn("File review request saved locally, not run", file_response.text)
        self.assertIn("file-type:", file_response.text)
        self.assertIn("Launch eligibility: blocked", file_response.text)
        self.assertIn("Folder review request saved locally, not run", folder_response.text)
        self.assertIn("Launch requests (local review only; nothing was run):", list_response.text)
        self.assertIn("mspaint.exe", list_response.text)
        self.assertIn("cleanup.py", list_response.text)
        self.assertIn("report.pdf", list_response.text)
        self.assertIn("archive", list_response.text)

    def test_script_review_checklist_commands_write_review_files_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            marker = root / "should_not_exist.txt"
            script.write_text(
                f"print('review only, no write to {marker}')\n",
                encoding="utf-8",
            )
            store = LaunchRequestStore(root / "launch_requests.json")
            assistant = LocalAssistant(
                use_llm=False,
                launch_request_store=store,
                script_checklist_dir=root / "script-checklists",
            )

            review_response = assistant.respond(f"request script review cleanup: {script}")
            checklist_response = assistant.respond("script review checklist 1")
            verify_response = assistant.respond("verify script review checklist 1")
            checklist_dirs = list((root / "script-checklists").glob("script-checklist-*"))
            manifest_exists = (checklist_dirs[0] / "manifest.json").exists() if checklist_dirs else False
            checklist_exists = (checklist_dirs[0] / "checklist.md").exists() if checklist_dirs else False

        self.assertFalse(marker.exists())
        self.assertIn("Script review request saved locally, not run", review_response.text)
        self.assertIn("Next review step: script review checklist 1", review_response.text)
        self.assertIn("Script operator checklist created", checklist_response.text)
        self.assertIn("No script was run", checklist_response.text)
        self.assertIsNone(checklist_response.pending_action)
        self.assertIn("Script checklist verification", verify_response.text)
        self.assertIn("Status: verified", verify_response.text)
        self.assertIsNone(verify_response.pending_action)
        self.assertEqual(len(checklist_dirs), 1)
        self.assertTrue(manifest_exists)
        self.assertTrue(checklist_exists)

    def test_script_allowlist_preflight_command_writes_review_record_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "cleanup.py"
            marker = root / "should_not_exist.txt"
            script.write_text(
                f"print('review only, no write to {marker}')\n",
                encoding="utf-8",
            )
            store = LaunchRequestStore(root / "launch_requests.json")
            assistant = LocalAssistant(
                use_llm=False,
                launch_request_store=store,
                script_checklist_dir=root / "script-checklists",
                script_preflight_dir=root / "script-preflights",
            )

            assistant.respond(f"request script review cleanup: {script}")
            assistant.respond("script review checklist 1")
            response = assistant.respond("script allowlist preflight 1")
            preflight_dirs = list((root / "script-preflights").glob("script-allowlist-preflight-*"))
            manifest_exists = (preflight_dirs[0] / "manifest.json").exists() if preflight_dirs else False

        self.assertFalse(marker.exists())
        self.assertIn("Script allowlist preflight created", response.text)
        self.assertIn("Preflight status: preflight_ready", response.text)
        self.assertIn("No script was run", response.text)
        self.assertIn("No script allowlist entry was created", response.text)
        self.assertIsNone(response.pending_action)
        self.assertEqual(len(preflight_dirs), 1)
        self.assertTrue(manifest_exists)

    def test_file_type_allowlist_commands_affect_file_review_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "report.pdf"
            document.write_text("local test", encoding="utf-8")
            store = LaunchRequestStore(
                root / "launch_requests.json",
                file_type_allowlist_path=root / "file_types.json",
            )
            assistant = LocalAssistant(
                use_llm=False,
                launch_request_store=store,
                file_type_allowlist_path=root / "file_types.json",
            )

            before_text = assistant.respond("file type allowlist")
            allow_text = assistant.respond("allow file type pdf")
            file_text = assistant.respond(f"request file review report: {document}")

        self.assertIn("File type allowlist: none", before_text.text)
        self.assertIn("File type allowlisted: .pdf", allow_text.text)
        self.assertIn("Launch eligibility: file type is explicitly allowlisted", file_text.text)

    def test_launch_file_is_blocked_until_file_type_is_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            response = assistant.respond("launch file in workspace report.pdf")

        self.assertIn("File launch blocked", response.text)
        self.assertIn("allow file type .pdf", response.text)
        self.assertIsNone(response.pending_action)

    @patch("assistant.core.os.startfile", create=True)
    def test_launch_file_requires_confirmation_and_opens_after_confirm(self, mock_startfile) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            response = assistant.respond("launch file in workspace report.pdf")
            assert response.pending_action is not None
            result = assistant.confirm_pending_action(response.pending_action)

        self.assertIn("Please confirm", response.text)
        self.assertEqual(response.pending_action.kind, "file_launch")
        self.assertIn("Done: Opened file in Windows", result)
        mock_startfile.assert_called_once()

    def test_file_type_trust_commands_update_and_clear_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            assistant = LocalAssistant(
                use_llm=False,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            source_text = assistant.respond(f"trust file type source .pdf: {root}")
            signer_text = assistant.respond("trust file type signer .pdf: Microsoft")
            thumbprint_text = assistant.respond(
                "trust file type thumbprint .pdf: 11223344556677889900AABBCCDDEEFF00112233"
            )
            issuer_text = assistant.respond("trust file type issuer .pdf: Microsoft Root")
            validity_text = assistant.respond("trust file type validity .pdf: required")
            revocation_text = assistant.respond("trust file type revocation .pdf: ocsp")
            policy_text = assistant.respond("file type trust .pdf")
            clear_text = assistant.respond("clear file type trust .pdf")

        self.assertIn("Updated trusted sources for .pdf", source_text.text)
        self.assertIn("Updated trusted signer tokens for .pdf", signer_text.text)
        self.assertIn("Updated pinned signer thumbprints for .pdf", thumbprint_text.text)
        self.assertIn("Updated trusted issuer tokens for .pdf", issuer_text.text)
        self.assertIn("Updated certificate validity requirement for .pdf", validity_text.text)
        self.assertIn("Updated certificate revocation check requirement for .pdf", revocation_text.text)
        self.assertIn("mode: ocsp", revocation_text.text)
        self.assertIn("Trust policy for .pdf", policy_text.text)
        self.assertIn("Pinned certificate thumbprints", policy_text.text)
        self.assertIn("Trusted issuer tokens", policy_text.text)
        self.assertIn("Certificate validity requirement: required", policy_text.text)
        self.assertIn("Certificate revocation check: required (mode: ocsp)", policy_text.text)
        self.assertIn("Cleared trust policy for .pdf", clear_text.text)

    def test_launch_file_blocks_when_source_trust_policy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            trusted = root / "trusted"
            trusted.mkdir()
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            assistant.respond(f"trust file type source .pdf: {trusted}")
            response = assistant.respond("launch file in workspace report.pdf")

        self.assertIn("File launch blocked by trust checks", response.text)
        self.assertIn("trusted source", response.text)

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(
            subject="CN=Microsoft Corporation",
            thumbprint="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            issuer="CN=Microsoft Root CA",
            not_before=datetime.now(UTC) - timedelta(days=1),
            not_after=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    def test_launch_file_blocks_when_thumbprint_trust_policy_fails(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            assistant.respond(
                "trust file type thumbprint .pdf: 11223344556677889900AABBCCDDEEFF00112233"
            )
            response = assistant.respond("launch file in workspace report.pdf")

        self.assertIn("File launch blocked by trust checks", response.text)
        self.assertIn("thumbprint", response.text)

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(
            subject="CN=Microsoft Corporation",
            thumbprint="11223344556677889900AABBCCDDEEFF00112233",
            issuer="CN=Unknown Issuer",
            not_before=datetime.now(UTC) - timedelta(days=1),
            not_after=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    def test_launch_file_blocks_when_issuer_trust_policy_fails(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            assistant.respond("trust file type issuer .pdf: Microsoft Root")
            response = assistant.respond("launch file in workspace report.pdf")

        self.assertIn("File launch blocked by trust checks", response.text)
        self.assertIn("issuer", response.text)

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(
            subject="CN=Microsoft Corporation",
            thumbprint="11223344556677889900AABBCCDDEEFF00112233",
            issuer="CN=Microsoft Root CA",
            not_before=datetime.now(UTC) + timedelta(days=1),
            not_after=datetime.now(UTC) + timedelta(days=2),
        ),
    )
    def test_launch_file_blocks_when_certificate_validity_requirement_fails(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            assistant.respond("trust file type validity .pdf: required")
            response = assistant.respond("launch file in workspace report.pdf")

        self.assertIn("File launch blocked by trust checks", response.text)
        self.assertIn("not currently valid", response.text)

    @patch(
        "assistant.file_type_allowlist._authenticode_revocation_status",
        return_value=(False, "Revoked"),
    )
    def test_launch_file_blocks_when_certificate_revocation_check_fails(self, _mock_revocation) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            assistant.respond("trust file type revocation .pdf: required")
            response = assistant.respond("launch file in workspace report.pdf")

        self.assertIn("File launch blocked by trust checks", response.text)
        self.assertIn("Signed-file review", response.text)
        self.assertIn("mode: online", response.text)
        self.assertIn("revocation", response.text)
        self.assertIn("revocation mode online blocked launch", response.text.lower())
        self.assertIn("Windows online chain revocation must succeed", response.text)

    @patch(
        "assistant.file_type_allowlist._authenticode_revocation_status",
        return_value=(True, "good (ocsp)"),
    )
    def test_launch_file_allowed_review_includes_revocation_mode(self, _mock_revocation) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "report.pdf"
            target.write_text("local test", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_type_allowlist_path=root / "file_types.json",
            )

            assistant.respond("allow file type pdf")
            assistant.respond("trust file type revocation .pdf: ocsp")
            response = assistant.respond("launch file in workspace report.pdf")

        self.assertIn("Signed-file review for .pdf", response.text)
        self.assertIn("mode: ocsp", response.text)
        self.assertIn("Revocation mode ocsp allowed launch", response.text)
        self.assertIn("OCSP endpoint must be advertised", response.text)
        self.assertIn("Launch status: allowed by current trust policy", response.text)
        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)

    def test_safety_snapshot_summarizes_launch_and_shell_reviews_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = LaunchRequestStore(root / "launch_requests.json")
            shell_commands_path = root / "shell_commands.json"
            assistant = LocalAssistant(
                use_llm=False,
                launch_request_store=store,
                shell_commands_path=shell_commands_path,
            )

            assistant.respond("request app paint: mspaint.exe")
            assistant.respond("request script review cleanup: tools/cleanup.py")
            assistant.respond("add shell command python check: python --version")
            response = assistant.respond("safety snapshot")
            launch_response = assistant.respond("safety snapshot launch")
            shell_response = assistant.respond("safety snapshot shell")
            script_response = assistant.respond("safety snapshot scripts")

        self.assertIn("Safety snapshot", response.text)
        self.assertIn("Launch review requests: 2", response.text)
        self.assertIn("Shell allowlist review records: 1", response.text)
        self.assertIn("signature valid", response.text)
        self.assertIn("No apps, scripts, files, folders, or shell commands were opened or run", response.text)
        self.assertIn("Safety snapshot: launch requests", launch_response.text)
        self.assertNotIn("Shell allowlist review records", launch_response.text)
        self.assertIn("Safety snapshot: shell reviews", shell_response.text)
        self.assertNotIn("Launch review requests", shell_response.text)
        self.assertIn("Safety snapshot: script reviews", script_response.text)
        self.assertIn("Script review requests: 1", script_response.text)
        self.assertNotIn("Shell allowlist review records", script_response.text)

    def test_script_drift_snapshot_threshold_rejects_out_of_range_values(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        too_low = assistant.respond("safety snapshot scripts drift threshold 0")
        too_high = assistant.respond("safety snapshot scripts drift threshold 4")
        not_a_number = assistant.respond("safety snapshot scripts drift threshold abc")

        for response in (too_low, too_high, not_a_number):
            self.assertIn("Launch request error", response.text)
            self.assertIn("whole number from 1 to 3", response.text)

    def test_script_drift_snapshot_threshold_accepts_in_range_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = LaunchRequestStore(root / "launch_requests.json")
            assistant = LocalAssistant(
                use_llm=False,
                launch_request_store=store,
                shell_commands_path=root / "shell_commands.json",
            )

            response = assistant.respond("safety snapshot scripts drift threshold 2")

        self.assertIn("Safety snapshot: script drift warnings", response.text)
        self.assertIn("threshold: >= 2 warning type(s)", response.text)

    def test_shell_commands_lists_allowlist(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("shell commands")

        self.assertIn("Safe shell commands", response.text)
        self.assertIn("python version", response.text)

    def test_shell_command_guide_describes_safe_editor(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("shell command guide")

        self.assertIn("Safe shell command allowlist guide", response.text)
        self.assertIn("shell command wizard", response.text)
        self.assertIn("static review notes", response.text)
        self.assertIn("signed review metadata", response.text)

    def test_shell_command_wizard_saves_next_valid_command_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shell_commands_path = Path(temp_dir) / "shell_commands.json"
            assistant = LocalAssistant(use_llm=False, shell_commands_path=shell_commands_path)

            start_response = assistant.respond("shell command wizard")
            save_response = assistant.respond("python check: python --version")
            run_response = assistant.respond("run shell python check")

        self.assertIn("Safe shell command wizard", start_response.text)
        self.assertIn("Saved safe shell command", save_response.text)
        self.assertIn("Static review notes", save_response.text)
        self.assertIn("Static risk score", save_response.text)
        self.assertIn("Signed review metadata", save_response.text)
        self.assertIsNone(save_response.pending_action)
        self.assertIn("Please confirm", run_response.text)
        self.assertIsNotNone(run_response.pending_action)

    def test_shell_command_wizard_can_cancel_without_saving(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shell_commands_path = Path(temp_dir) / "shell_commands.json"
            assistant = LocalAssistant(use_llm=False, shell_commands_path=shell_commands_path)

            assistant.respond("shell command wizard")
            cancel_response = assistant.respond("cancel")
            after_cancel_response = assistant.respond("python check: python --version")

        self.assertIn("Cancelled shell command wizard", cancel_response.text)
        self.assertIn("do not know how", after_cancel_response.text)

    def test_shell_wizard_add_one_shot_saves_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shell_commands_path = Path(temp_dir) / "shell_commands.json"
            assistant = LocalAssistant(use_llm=False, shell_commands_path=shell_commands_path)

            response = assistant.respond("shell wizard add python check: python --version")

        self.assertIn("Saved safe shell command", response.text)
        self.assertIn("Static review notes", response.text)
        self.assertIn("Static risk score", response.text)
        self.assertIn("Signed review metadata", response.text)
        self.assertIsNone(response.pending_action)

    def test_run_shell_command_requires_confirmation(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("run shell python version")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)
        self.assertEqual(response.pending_action.kind, "shell_command")

    def test_add_shell_command_saves_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shell_commands_path = Path(temp_dir) / "shell_commands.json"
            assistant = LocalAssistant(use_llm=False, shell_commands_path=shell_commands_path)

            add_response = assistant.respond("add shell command python check: python --version")
            run_response = assistant.respond("run shell python check")

        self.assertIn("Saved safe shell command", add_response.text)
        self.assertIn("Nothing was run", add_response.text)
        self.assertIn("Static review notes", add_response.text)
        self.assertIn("Static risk score", add_response.text)
        self.assertIn("Signed review metadata", add_response.text)
        self.assertIsNone(add_response.pending_action)
        self.assertIn("Please confirm", run_response.text)
        self.assertIsNotNone(run_response.pending_action)

    def test_shell_review_checklist_writes_local_files_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shell_commands_path = root / "shell_commands.json"
            assistant = LocalAssistant(
                use_llm=False,
                shell_commands_path=shell_commands_path,
                data_export_dir=root / "exports",
            )
            assistant.respond("add shell command python check: python --version")

            response = assistant.respond("shell review checklist python check")
            verify_response = assistant.respond("verify shell checklist python check")
            checklist_dirs = list((root / "exports" / "shell-review-checklists").glob("shell-checklist-*"))
            manifest_exists = (checklist_dirs[0] / "manifest.json").exists() if checklist_dirs else False
            checklist_exists = (checklist_dirs[0] / "checklist.md").exists() if checklist_dirs else False

        self.assertIn("Shell operator checklist created", response.text)
        self.assertIn("No shell command was run", response.text)
        self.assertIsNone(response.pending_action)
        self.assertIn("Shell checklist verification", verify_response.text)
        self.assertIn("Status: verified", verify_response.text)
        self.assertIsNone(verify_response.pending_action)
        self.assertEqual(len(checklist_dirs), 1)
        self.assertTrue(manifest_exists)
        self.assertTrue(checklist_exists)

    def test_remove_shell_command_updates_allowlist_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shell_commands_path = Path(temp_dir) / "shell_commands.json"
            assistant = LocalAssistant(use_llm=False, shell_commands_path=shell_commands_path)
            assistant.respond("add shell command python check: python --version")

            remove_response = assistant.respond("remove shell command python check")
            run_response = assistant.respond("run shell python check")

        self.assertIn("Removed safe shell command", remove_response.text)
        self.assertIn("Signed review metadata", remove_response.text)
        self.assertIsNone(remove_response.pending_action)
        self.assertIn("Shell command error", run_response.text)

    def test_add_shell_command_rejects_inline_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shell_commands_path = Path(temp_dir) / "shell_commands.json"
            assistant = LocalAssistant(use_llm=False, shell_commands_path=shell_commands_path)

            response = assistant.respond("add shell command unsafe: python -c print(1)")

        self.assertIn("Shell command error", response.text)
        self.assertIn("Inline Python code", response.text)

    @patch("assistant.core.run_shell_command", return_value="Shell command finished with exit code 0")
    def test_confirm_pending_shell_command_runs_named_command(self, mock_run_shell) -> None:
        assistant = LocalAssistant(use_llm=False)
        response = assistant.respond("run shell python version")
        assert response.pending_action is not None

        result = assistant.confirm_pending_action(response.pending_action)

        self.assertIn("exit code 0", result)
        mock_run_shell.assert_called_once()

    def test_unknown_shell_command_is_rejected(self) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("run shell del downloads")

        self.assertIn("Shell command error", response.text)
        self.assertIsNone(response.pending_action)

    def test_alias_resolves_to_builtin_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            aliases_path = Path(temp_dir) / "aliases.json"
            save_aliases({"show my memory": "memories"}, aliases_path)
            assistant = LocalAssistant(
                use_llm=False,
                aliases_path=aliases_path,
                memory_store=MemoryStore(Path(temp_dir) / "memory.json"),
            )

            response = assistant.respond("show my memory")

        self.assertIn("No saved memories", response.text)

    def test_alias_resolves_to_safe_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            aliases_path = Path(temp_dir) / "aliases.json"
            save_aliases({"open math": "open calculator"}, aliases_path)
            assistant = LocalAssistant(use_llm=False, aliases_path=aliases_path)

            response = assistant.respond("open math")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)

    def test_note_command_saves_local_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            notes_store = NotesStore(Path(temp_dir) / "notes.md")
            assistant = LocalAssistant(use_llm=False, notes_store=notes_store)

            save_response = assistant.respond("note buy printer paper")
            list_response = assistant.respond("notes")

        self.assertEqual(save_response.text, "Noted: buy printer paper")
        self.assertIn("buy printer paper", list_response.text)

    def test_rename_memory_command_updates_one_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_store = MemoryStore(Path(temp_dir) / "memory.json")
            assistant = LocalAssistant(use_llm=False, memory_store=memory_store)
            assistant.respond("remember old preference")

            response = assistant.respond("rename memory 1 to new preference")
            memories = assistant.respond("memories")

        self.assertEqual(response.text, "Renamed memory 1: new preference")
        self.assertIn("new preference", memories.text)
        self.assertNotIn("old preference", memories.text)

    def test_delete_memory_requires_confirmation_and_uses_trash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_store = MemoryStore(Path(temp_dir) / "memory.json")
            assistant = LocalAssistant(use_llm=False, memory_store=memory_store)
            assistant.respond("remember keep tea stocked")

            response = assistant.respond("delete memory 1")
            assert response.pending_action is not None
            result = assistant.confirm_pending_action(response.pending_action)
            trash = assistant.respond("memory trash")
            restore = assistant.respond("restore memory 1")
            memories = assistant.respond("memories")

        self.assertEqual(response.pending_action.kind, "memory_delete")
        self.assertIn("Please confirm", response.text)
        self.assertEqual(result, "Done: Moved memory 1 to trash: keep tea stocked.")
        self.assertIn("Memory trash:", trash.text)
        self.assertEqual(restore.text, "Restored memory 1: keep tea stocked")
        self.assertIn("keep tea stocked", memories.text)

    def test_search_command_finds_local_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_store = MemoryStore(root / "memory.json")
            notes_store = NotesStore(root / "notes.md")
            tasks_store = TasksStore(root / "tasks.json")
            history_store = HistoryStore(root / "history.jsonl")
            assistant = LocalAssistant(
                use_llm=False,
                memory_store=memory_store,
                notes_store=notes_store,
                tasks_store=tasks_store,
                history_store=history_store,
            )
            assistant.respond("remember I like quiet keyboards")
            assistant.respond("note buy quiet switches")
            assistant.respond("todo replace quiet fan")
            assistant.record_turn("quiet mode", "Done.")

            response = assistant.respond("search quiet")

        self.assertIn("[memory]", response.text)
        self.assertIn("[note]", response.text)
        self.assertIn("[task]", response.text)
        self.assertIn("[history]", response.text)

    def test_file_tool_commands_are_read_only_and_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "notes.txt").write_text("quiet keyboard\ntea list\n", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                data_export_dir=root / "exports",
                action_audit_store=ActionAuditStore(root / "audit.jsonl"),
            )

            help_response = assistant.respond("file tools")
            list_response = assistant.respond("list files in workspace")
            search_response = assistant.respond("search files in workspace for quiet")
            name_search_response = assistant.respond("find files in workspace for notes")
            read_response = assistant.respond("read file in workspace notes.txt")
            open_response = assistant.respond("open file in workspace notes.txt")
            replace_plan_response = assistant.respond("preview replace in workspace find quiet with silent")
            rename_plan_response = assistant.respond("preview rename files in workspace replace notes with journal")
            apply_safety_response = assistant.respond("bulk apply safety")
            replace_apply_response = assistant.respond(
                "bulk replace apply plan in workspace find quiet with silent"
            )
            rename_apply_response = assistant.respond(
                "bulk rename apply plan in workspace replace notes with journal"
            )
            replace_backup_response = assistant.respond(
                "backup bulk replace in workspace find quiet with silent"
            )
            rename_backup_response = assistant.respond(
                "backup bulk rename in workspace replace notes with journal"
            )
            replace_approval_response = assistant.respond(
                "approve bulk replace in workspace find quiet with silent files 1"
            )
            rename_approval_response = assistant.respond(
                "approve bulk rename in workspace replace notes with journal files all"
            )
            apply_review_response = assistant.respond("bulk apply review")
            rollback_plan_response = assistant.respond("bulk rollback plan")
            write_preflight_response = assistant.respond("bulk write preflight")
            write_checklist_response = assistant.respond("bulk write checklist")
            restore_checklist_response = assistant.respond("bulk restore checklist")
            write_checklist_verify_response = assistant.respond("verify bulk write checklist")
            restore_checklist_verify_response = assistant.respond("verify bulk restore checklist")
            write_design_response = assistant.respond("bulk write command design")
            restore_design_response = assistant.respond("bulk restore command design")
            audit_response = assistant.respond("action audit")
            blocked_response = assistant.respond("read file in workspace ../secret.txt")
            blocked_open_response = assistant.respond("open file in workspace ../secret.txt")
            notes_text_after_plans = (workspace / "notes.txt").read_text(encoding="utf-8")
            bulk_backups = list((root / "exports" / "bulk-file-backups").glob("bulk-*"))
            bulk_approvals = list((root / "exports" / "bulk-file-approvals").glob("bulk-*"))
            bulk_reviews = list((root / "exports" / "bulk-apply-reviews").glob("bulk-*"))
            bulk_rollbacks = list((root / "exports" / "bulk-rollback-plans").glob("bulk-*"))
            bulk_preflights = list((root / "exports" / "bulk-write-preflights").glob("bulk-*"))
            bulk_checklists = list((root / "exports" / "bulk-review-checklists").glob("bulk-*"))

        self.assertIn("Safe file tools", help_response.text)
        self.assertIn("notes.txt", list_response.text)
        self.assertIn("notes.txt:1", search_response.text)
        self.assertIn("Filename search results", name_search_response.text)
        self.assertIn("notes.txt", name_search_response.text)
        self.assertIn("quiet keyboard", read_response.text)
        self.assertIn("Safe file open preview", open_response.text)
        self.assertIn("Bulk replace dry run", replace_plan_response.text)
        self.assertIn("No files were changed", replace_plan_response.text)
        self.assertIn("Bulk rename dry run", rename_plan_response.text)
        self.assertIn("notes.txt -> journal.txt", rename_plan_response.text)
        self.assertIn("Bulk apply safety", apply_safety_response.text)
        self.assertIn("Apply is not enabled in this build", apply_safety_response.text)
        self.assertIn("Bulk replace apply safety plan", replace_apply_response.text)
        self.assertIn("Backup requirement", replace_apply_response.text)
        self.assertIn("Bulk rename apply safety plan", rename_apply_response.text)
        self.assertIn("Per-file approval requirement", rename_apply_response.text)
        self.assertIn("Bulk replace backup created", replace_backup_response.text)
        self.assertIn("Hash algorithm: sha256", replace_backup_response.text)
        self.assertIn("Bulk rename backup created", rename_backup_response.text)
        self.assertIn("Bulk replace approval saved", replace_approval_response.text)
        self.assertIn("Hash algorithm: sha256", replace_approval_response.text)
        self.assertIn("Bulk rename approval saved", rename_approval_response.text)
        self.assertIn("Bulk apply review created", apply_review_response.text)
        self.assertIn("Review status: review_ready", apply_review_response.text)
        self.assertIn("Approved file source hashes match", apply_review_response.text)
        self.assertIn("Bulk rollback plan created", rollback_plan_response.text)
        self.assertIn("Restore is not enabled", rollback_plan_response.text)
        self.assertIn("Bulk write preflight created", write_preflight_response.text)
        self.assertIn("Preflight status: preflight_ready", write_preflight_response.text)
        self.assertIn("Manifest hashes verified", write_preflight_response.text)
        self.assertIn("Signed review metadata", write_preflight_response.text)
        self.assertIn("Bulk write operator checklist created", write_checklist_response.text)
        self.assertIn("No files were written", write_checklist_response.text)
        self.assertIn("Bulk restore operator checklist created", restore_checklist_response.text)
        self.assertIn("No files were written", restore_checklist_response.text)
        self.assertIn("Bulk write checklist verification", write_checklist_verify_response.text)
        self.assertIn("Status: verified", write_checklist_verify_response.text)
        self.assertIn("does not grant permission", write_checklist_verify_response.text)
        self.assertIn("Bulk restore checklist verification", restore_checklist_verify_response.text)
        self.assertIn("Status: verified", restore_checklist_verify_response.text)
        self.assertIn("Confirmed bulk write command design", write_design_response.text)
        self.assertIn("No files are written", write_design_response.text)
        self.assertIn("Confirmed bulk restore command design", restore_design_response.text)
        self.assertIn("No files are restored", restore_design_response.text)
        self.assertIn("Bulk apply review", audit_response.text)
        self.assertIn("Bulk rollback plan", audit_response.text)
        self.assertIn("Bulk write preflight", audit_response.text)
        self.assertIn("Bulk write checklist verification", audit_response.text)
        self.assertEqual(len(bulk_backups), 2)
        self.assertEqual(len(bulk_approvals), 2)
        self.assertEqual(len(bulk_reviews), 1)
        self.assertEqual(len(bulk_rollbacks), 1)
        self.assertEqual(len(bulk_preflights), 1)
        self.assertEqual(len(bulk_checklists), 2)
        self.assertIn("File tools error", blocked_response.text)
        self.assertIn("File tools error", blocked_open_response.text)
        self.assertEqual(notes_text_after_plans, "quiet keyboard\ntea list\n")

    def test_file_delete_requires_confirmation_and_restores_from_trash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "notes.txt"
            target.write_text("quiet keyboard\n", encoding="utf-8")
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_trash_dir=root / "trash",
                file_trash_manifest_path=root / "manifest.json",
            )

            delete_response = assistant.respond("delete file in workspace notes.txt")
            assert delete_response.pending_action is not None
            result = assistant.confirm_pending_action(delete_response.pending_action)
            trash_response = assistant.respond("file trash")
            restore_response = assistant.respond("restore file 1")
            restored_exists = target.exists()

        self.assertIn("Please confirm", delete_response.text)
        self.assertEqual(delete_response.pending_action.kind, "file_delete")
        self.assertIn("Moved file to assistant trash: workspace/notes.txt", result)
        self.assertIn("File trash:", trash_response.text)
        self.assertIn("Restored file 1: workspace/notes.txt", restore_response.text)
        self.assertTrue(restored_exists)

    def test_file_delete_blocks_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            folders_path = root / "folders.json"
            from assistant.actions import save_allowed_folders

            save_allowed_folders({"workspace": str(workspace)}, folders_path)
            assistant = LocalAssistant(
                use_llm=False,
                folders_path=folders_path,
                file_trash_dir=root / "trash",
                file_trash_manifest_path=root / "manifest.json",
            )

            response = assistant.respond("delete file in workspace ../secret.txt")

        self.assertIn("File path must stay inside", response.text)
        self.assertIsNone(response.pending_action)

    def test_task_commands_add_list_and_complete_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)

            add_response = assistant.respond("todo call dentist")
            list_response = assistant.respond("tasks")
            done_response = assistant.respond("done 1")
            empty_response = assistant.respond("tasks")

        self.assertEqual(add_response.text, "Added task: call dentist")
        self.assertIn("1. call dentist", list_response.text)
        self.assertEqual(done_response.text, "Completed task: call dentist")
        self.assertEqual(empty_response.text, "No open tasks.")

    def test_task_command_accepts_due_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)

            add_response = assistant.respond("todo call dentist due 2026-07-05")
            list_response = assistant.respond("tasks")

        self.assertEqual(add_response.text, "Added task: call dentist")
        self.assertIn("call dentist (due 2026-07-05)", list_response.text)

    def test_due_date_view_commands_return_task_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)
            future_date = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()

            assistant.respond(f"todo call dentist due {future_date}")
            response = assistant.respond("upcoming")

        self.assertIn("Upcoming tasks", response.text)
        self.assertIn(f"call dentist (due {future_date})", response.text)

    def test_task_stats_and_due_soon_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)
            future_date = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()

            assistant.respond(f"todo call dentist due {future_date}")
            stats_response = assistant.respond("task stats")
            due_soon_response = assistant.respond("due soon")

        self.assertIn("Task stats", stats_response.text)
        self.assertIn("Open tasks: 1", stats_response.text)
        self.assertIn("Due soon", due_soon_response.text)

    def test_task_rename_and_due_date_update_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)

            assistant.respond("todo call dentist")
            rename_response = assistant.respond("rename task 1 to call doctor")
            due_response = assistant.respond("due 1 2026-07-05")
            clear_response = assistant.respond("clear due 1")

        self.assertIn("Renamed task 1: call doctor", rename_response.text)
        self.assertIn("Updated due date for task 1", due_response.text)
        self.assertIn("Cleared due date for task 1: call doctor", clear_response.text)

    def test_delete_task_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)
            assistant.respond("todo call dentist")

            response = assistant.respond("delete task 1")

        self.assertIn("Please confirm", response.text)
        self.assertIsNotNone(response.pending_action)
        self.assertEqual(response.pending_action.kind, "task_delete")

    def test_confirm_pending_task_delete_removes_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)
            assistant.respond("todo call dentist")
            response = assistant.respond("delete task 1")
            assert response.pending_action is not None

            result = assistant.confirm_pending_action(response.pending_action)
            tasks_response = assistant.respond("tasks")

        self.assertEqual(result, "Done: Moved task 1 to trash: call dentist.")
        self.assertEqual(tasks_response.text, "No open tasks.")

    def test_task_trash_and_restore_deleted_task_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)
            assistant.respond("todo call dentist due 2026-07-05")
            delete_response = assistant.respond("delete task 1")
            assert delete_response.pending_action is not None
            assistant.confirm_pending_action(delete_response.pending_action)

            trash_response = assistant.respond("task trash")
            restore_response = assistant.respond("restore deleted task 1")
            tasks_response = assistant.respond("tasks")

        self.assertIn("Task trash:", trash_response.text)
        self.assertIn("call dentist (due 2026-07-05)", trash_response.text)
        self.assertIn("Restored deleted task 1: call dentist (due 2026-07-05)", restore_response.text)
        self.assertIn("call dentist (due 2026-07-05)", tasks_response.text)

    def test_restore_completed_task_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)
            assistant.respond("todo call dentist due 2026-07-05")
            assistant.respond("done 1")

            response = assistant.respond("restore task 1")
            tasks_response = assistant.respond("tasks")

        self.assertIn("Restored task 1: call dentist (due 2026-07-05)", response.text)
        self.assertIn("call dentist (due 2026-07-05)", tasks_response.text)

    def test_completed_and_all_task_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
            assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)

            assistant.respond("todo call dentist")
            assistant.respond("todo buy tea")
            assistant.respond("done 1")
            completed_response = assistant.respond("completed tasks")
            all_response = assistant.respond("all tasks")

        self.assertIn("Completed tasks", completed_response.text)
        self.assertIn("call dentist", completed_response.text)
        self.assertIn("[done] call dentist", all_response.text)
        self.assertIn("[open] buy tea", all_response.text)

    def test_briefing_command_summarizes_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_store = MemoryStore(root / "memory.json")
            notes_store = NotesStore(root / "notes.md")
            tasks_store = TasksStore(root / "tasks.json")
            assistant = LocalAssistant(
                use_llm=False,
                memory_store=memory_store,
                notes_store=notes_store,
                tasks_store=tasks_store,
            )
            assistant.respond("remember I prefer short answers")
            assistant.respond("note buy tea")
            assistant.respond("todo call dentist")

            response = assistant.respond("briefing")

        self.assertIn("Local briefing", response.text)
        self.assertIn("Saved memories: 1", response.text)
        self.assertIn("call dentist", response.text)
        self.assertIn("buy tea", response.text)

    def test_data_report_command_summarizes_local_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_store = MemoryStore(root / "memory.json")
            notes_store = NotesStore(root / "notes.md")
            tasks_store = TasksStore(root / "tasks.json")
            history_store = HistoryStore(root / "history.jsonl")
            audit_store = ActionAuditStore(root / "audit.jsonl")
            outbox_store = OutboxStore(root / "outbox.json")
            assistant = LocalAssistant(
                use_llm=False,
                memory_store=memory_store,
                notes_store=notes_store,
                tasks_store=tasks_store,
                outbox_store=outbox_store,
                history_store=history_store,
                action_audit_store=audit_store,
            )
            assistant.respond("remember I prefer short answers")
            assistant.respond("note buy tea")
            assistant.respond("todo call dentist")
            assistant.record_turn("hello", "Hello.")

            response = assistant.respond("data report")

        self.assertIn("Local assistant data report", response.text)
        self.assertIn("Memory: 1", response.text)
        self.assertIn("Notes: 1", response.text)
        self.assertIn("Open tasks: 1", response.text)
        self.assertIn("Outbox drafts: 0", response.text)
        self.assertIn("History: 2", response.text)

    def test_outbox_draft_commands_save_local_drafts_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox_store = OutboxStore(Path(temp_dir) / "outbox.json")
            assistant = LocalAssistant(use_llm=False, outbox_store=outbox_store)

            message_response = assistant.respond("draft message to Alex: running late")
            email_response = assistant.respond(
                "draft email to alex@example.com subject Hello: quick local note"
            )
            request_response = assistant.respond(
                "draft network request GET https://example.com health check"
            )
            list_response = assistant.respond("outbox")

        self.assertIn("Draft saved locally, not sent", message_response.text)
        self.assertIn("message to Alex: running late", message_response.text)
        self.assertIn("email to alex@example.com subject 'Hello'", email_response.text)
        self.assertIn("request not made", request_response.text)
        self.assertIn("Outbox drafts (local only, not sent):", list_response.text)
        self.assertIn("message to Alex", list_response.text)
        self.assertIn("network request GET https://example.com", list_response.text)

    def test_outbox_blocks_direct_sending_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox_store = OutboxStore(Path(temp_dir) / "outbox.json")
            assistant = LocalAssistant(use_llm=False, outbox_store=outbox_store)

            response = assistant.respond("send message to Alex: hello")

        self.assertIn("Sending is not enabled", response.text)
        self.assertEqual(outbox_store.list_drafts(), [])

    def test_outbox_rejects_invalid_network_request_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = LocalAssistant(
                use_llm=False,
                outbox_store=OutboxStore(Path(temp_dir) / "outbox.json"),
            )

            response = assistant.respond("draft network request DELETE https://example.com")

        self.assertIn("Outbox error", response.text)

    @patch("assistant.core.collect_status_from_stores", return_value=FakeStatus())
    def test_status_command_returns_local_status(self, mock_status) -> None:
        assistant = LocalAssistant(use_llm=False)

        response = assistant.respond("status")

        self.assertIn("Local assistant status", response.text)
        self.assertIn("Assistant: Test", response.text)

    def test_export_data_command_writes_local_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_store = MemoryStore(root / "memory.json")
            notes_store = NotesStore(root / "notes.md")
            tasks_store = TasksStore(root / "tasks.json")
            history_store = HistoryStore(root / "history.jsonl")
            audit_store = ActionAuditStore(root / "audit.jsonl")
            outbox_store = OutboxStore(root / "outbox.json")
            assistant = LocalAssistant(
                use_llm=False,
                memory_store=memory_store,
                notes_store=notes_store,
                tasks_store=tasks_store,
                outbox_store=outbox_store,
                history_store=history_store,
                action_audit_store=audit_store,
                data_export_dir=root / "exports",
            )
            assistant.respond("remember I prefer short answers")
            assistant.respond("note buy tea")
            assistant.respond("todo call dentist")

            response = assistant.respond("export data")
            exports = list((root / "exports").glob("assistant-data-*"))

            self.assertIn("Exported local assistant data to:", response.text)
            self.assertEqual(len(exports), 1)
            self.assertTrue((exports[0] / "report.json").exists())

    def test_export_safety_reviews_command_writes_local_audit_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shell_commands_path = root / "shell_commands.json"
            add_shell_command("python check", ["python", "--version"], shell_commands_path)
            assistant = LocalAssistant(
                use_llm=False,
                shell_commands_path=shell_commands_path,
                data_export_dir=root / "exports",
            )

            response = assistant.respond("export safety reviews")
            exports = list((root / "exports" / "safety-review-exports").glob("safety-review-*"))
            manifest_exists = (exports[0] / "safety_reviews.json").exists() if exports else False

        self.assertIn("Signed safety review export created", response.text)
        self.assertIn("No commands were run", response.text)
        self.assertEqual(len(exports), 1)
        self.assertTrue(manifest_exists)

    def test_backups_command_lists_local_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export_root = root / "exports"
            (export_root / "assistant-data-20260702-010000").mkdir(parents=True)
            assistant = LocalAssistant(use_llm=False, data_export_dir=export_root)

            response = assistant.respond("backups")

        self.assertIn("Local backups:", response.text)
        self.assertIn("assistant-data-20260702-010000", response.text)

    def test_unknown_question_can_use_llm(self) -> None:
        assistant = LocalAssistant(llm_client=FakeLlmClient())

        response = assistant.respond("explain local models")

        self.assertIn("fake local answer", response.text)
        self.assertFalse(response.should_exit)


    def test_memory_question_returns_saved_memories_without_llm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_llm = FakeLlmClient()
            assistant = LocalAssistant(
                llm_client=fake_llm,
                memory_store=MemoryStore(Path(temp_dir) / "memory.json"),
            )

            assistant.respond("remember I prefer short answers")
            response = assistant.respond("what do you know about how I like answers")

        self.assertIn("I prefer short answers", response.text)
        self.assertIsNone(fake_llm.last_prompt)
    def test_saved_memory_is_passed_to_llm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_llm = FakeLlmClient()
            assistant = LocalAssistant(
                llm_client=fake_llm,
                memory_store=MemoryStore(Path(temp_dir) / "memory.json"),
            )

            assistant.respond("remember I prefer short answers")
            response = assistant.respond("how should you answer me")

        self.assertIn("fake local answer", response.text)
        self.assertIsNotNone(fake_llm.last_memory_context)
        self.assertIn("I prefer short answers", fake_llm.last_memory_context or "")


    def test_history_command_returns_recent_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = LocalAssistant(
                use_llm=False,
                history_store=HistoryStore(Path(temp_dir) / "history.jsonl"),
            )
            assistant.record_turn("hello", "Hello.")

            response = assistant.respond("history")

        self.assertIn("Recent conversation history", response.text)
        self.assertIn("user: hello", response.text)

    def test_clear_history_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant = LocalAssistant(
                use_llm=False,
                history_store=HistoryStore(Path(temp_dir) / "history.jsonl"),
            )
            assistant.record_turn("hello", "Hello.")

            response = assistant.respond("clear history")

        self.assertIn("Cleared", response.text)

    def test_action_audit_command_returns_recent_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_store = ActionAuditStore(Path(temp_dir) / "audit.jsonl")
            assistant = LocalAssistant(use_llm=False, action_audit_store=audit_store)
            response = assistant.respond("open calculator")
            assert response.pending_action is not None
            audit_store.record(
                response.pending_action,
                status="cancelled",
                requested_by="no",
                result="Cancelled.",
            )

            response = assistant.respond("action audit")

        self.assertIn("Recent action audit entries", response.text)
        self.assertIn("cancelled", response.text)

    def test_voice_audit_command_returns_text_only_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_store = VoiceActionAuditStore(Path(temp_dir) / "voice.jsonl")
            assistant = LocalAssistant(use_llm=False, voice_action_audit_store=voice_store)
            voice_store.record(
                "action_preview",
                "open calculator",
                "low",
                action_description="Open calculator",
                result="Pending confirmation.",
            )

            response = assistant.respond("voice audit")

        self.assertIn("Recent voice action audit entries", response.text)
        self.assertIn("open calculator", response.text)
        self.assertIn("Audio is never stored", response.text)

    def test_voice_audit_command_filters_by_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_store = VoiceActionAuditStore(Path(temp_dir) / "voice.jsonl")
            assistant = LocalAssistant(use_llm=False, voice_action_audit_store=voice_store)
            voice_store.record("recognized", "hello", "high")
            voice_store.record("action_preview", "open calculator", "low")

            response = assistant.respond("voice audit confidence low")

        self.assertIn("confidence=low", response.text)
        self.assertIn("open calculator", response.text)
        self.assertNotIn("hello", response.text)

    def test_export_voice_audit_writes_local_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voice_store = VoiceActionAuditStore(root / "voice.jsonl")
            assistant = LocalAssistant(
                use_llm=False,
                voice_action_audit_store=voice_store,
                data_export_dir=root / "exports",
            )
            voice_store.record("action_preview", "open calculator", "low")

            response = assistant.respond("export voice audit confidence low")
            exports = list((root / "exports" / "voice-audit-exports").glob("voice-audit-*"))
            manifest_exists = (exports[0] / "voice_action_audit.json").exists() if exports else False

        self.assertIn("Voice action audit export created", response.text)
        self.assertIn("No audio was exported", response.text)
        self.assertTrue(manifest_exists)

    def test_voice_audit_retention_preview_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "voice.jsonl"
            voice_store = VoiceActionAuditStore(path)
            assistant = LocalAssistant(use_llm=False, voice_action_audit_store=voice_store)
            voice_store.record("recognized", "first", "high")
            voice_store.record("recognized", "second", "high")
            before = path.read_text(encoding="utf-8")

            response = assistant.respond("voice audit retention keep 1")
            after = path.read_text(encoding="utf-8")

        self.assertIn("Voice action audit retention preview", response.text)
        self.assertIn("No changes were made", response.text)
        self.assertIn("Would remove: 1", response.text)
        self.assertIsNone(response.pending_action)
        self.assertEqual(before, after)

    def test_confirmed_voice_audit_prune_keeps_latest_and_backs_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voice_store = VoiceActionAuditStore(root / "voice.jsonl")
            assistant = LocalAssistant(
                use_llm=False,
                voice_action_audit_store=voice_store,
                data_export_dir=root / "exports",
            )
            voice_store.record("recognized", "first", "high")
            voice_store.record("recognized", "second", "high")

            response = assistant.respond("prune voice audit keep 1")
            assert response.pending_action is not None
            result = assistant.confirm_pending_action(response.pending_action)
            entries = voice_store.recent(limit=10)
            backups = list((root / "exports" / "voice-audit-retention").glob("voice-audit-retention-*"))

        self.assertEqual(response.pending_action.kind, "voice_audit_prune")
        self.assertIn("Please confirm", response.text)
        self.assertIn("Voice action audit retention applied", result)
        self.assertIn("Backup folder", result)
        self.assertEqual([entry.command_text for entry in entries], ["second"])
        self.assertTrue(backups)

    def test_llm_failure_returns_actionable_message(self) -> None:
        assistant = LocalAssistant(llm_client=FailingLlmClient())

        response = assistant.respond("explain local models")

        self.assertIn("Ollama is not reachable", response.text)
        self.assertIn("--no-llm", response.text)
        self.assertFalse(response.should_exit)


if __name__ == "__main__":
    unittest.main()
