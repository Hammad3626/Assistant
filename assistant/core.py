"""Core command handling for the local assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from assistant.actions import PendingAction, describe_allowed_actions, execute_action, parse_action
from assistant.about import about_text
from assistant.aliases import DEFAULT_ALIASES_PATH, AliasError, resolve_alias
from assistant.audit import ActionAuditStore, AuditError
from assistant.briefing import BriefingError, build_briefing
from assistant.command_help import command_help_text
from assistant.command_reference import command_reference_text
from assistant.command_suggestions import suggest_commands, unknown_command_text
from assistant.data_tools import backups_summary, build_report_from_stores, export_data_from_stores
from assistant.file_tools import (
    DEFAULT_FILE_TRASH_DIR,
    DEFAULT_FILE_TRASH_MANIFEST,
    AllowlistedFileTools,
    FileToolError,
    file_tools_help_text,
)
from assistant.file_type_allowlist import (
    DEFAULT_FILE_TYPE_ALLOWLIST_PATH,
    FileTypeAllowlistError,
    FileTypeAllowlistStore,
    normalize_file_extension,
)
from assistant.history import HistoryError, HistoryStore
from assistant.intent_parser import normalize_intent
from assistant.launch_commands import launch_commands_text
from assistant.launch_requests import (
    DEFAULT_LAUNCH_REQUESTS_PATH,
    DEFAULT_SCRIPT_ALLOWLIST_SIMULATION_DIR,
    DEFAULT_SCRIPT_CHECKLIST_DIR,
    DEFAULT_SCRIPT_EXECUTION_READINESS_DIR,
    DEFAULT_SCRIPT_PREFLIGHT_DIR,
    DEFAULT_SCRIPT_RUN_SIMULATION_DIR,
    LaunchRequestError,
    LaunchRequestStore,
    blocked_unlisted_launch_text,
)
from assistant.memory import MemoryError, MemoryStore
from assistant.model_tools import ModelToolError, list_ollama_models
from assistant.notes import NotesError, NotesStore
from assistant.ollama_client import OllamaClient
from assistant.outbox import DEFAULT_OUTBOX_PATH, OutboxError, OutboxStore, blocked_send_text
from assistant.path_report import format_path_report
from assistant.roadmap import roadmap_text
from assistant.safety import permission_dashboard_text, safety_text
from assistant.safety_snapshot import safety_snapshot_text
from assistant.safety_reviews import SafetyReviewExportError, export_safety_reviews, safety_review_export_summary
from assistant.search import LocalSearch, LocalSearchError
from assistant.settings import AssistantSettings
from assistant.system_index import IndexedItem, SystemIndex
from assistant.index_store import IndexStore, PreferencesStore
from assistant.system_search import SystemSearch
from assistant.script_allowlist_design import script_allowlist_design_text
from assistant.shell_tools import (
    DEFAULT_SHELL_COMMANDS_PATH,
    ShellToolError,
    add_shell_command,
    create_shell_review_checklist,
    get_shell_command,
    parse_shell_command_request,
    remove_shell_command,
    run_shell_command,
    latest_shell_review_metadata,
    shell_command_signed_review_text,
    shell_command_static_review_notes,
    shell_command_wizard_text,
    shell_commands_summary,
    verify_shell_review_checklist,
)
from assistant.status import collect_status_from_stores
from assistant.tasks import TasksError, TasksStore
from assistant.voice_status import voice_status_text
from assistant.voice_input import voice_confidence_status_text, wake_status_text
from assistant.voice_audit import VoiceActionAuditStore, VoiceAuditError
from assistant.voice_safety_drill import voice_safety_drill_text
from assistant.windows_detection import detected_drives_summary, detected_folders_summary, detected_locations_summary


@dataclass(frozen=True)
class AssistantResponse:
    """Structured response returned by the assistant core."""

    text: str
    should_exit: bool = False
    pending_action: PendingAction | None = None


class LocalAssistant:
    """Deterministic local assistant core with optional local LLM fallback."""

    def __init__(
        self,
        name: str = "Jarvis",
        llm_client: OllamaClient | None = None,
        use_llm: bool = True,
        memory_store: MemoryStore | None = None,
        notes_store: NotesStore | None = None,
        tasks_store: TasksStore | None = None,
        history_store: HistoryStore | None = None,
        action_audit_store: ActionAuditStore | None = None,
        voice_action_audit_store: VoiceActionAuditStore | None = None,
        outbox_store: OutboxStore | None = None,
        launch_request_store: LaunchRequestStore | None = None,
        aliases_path: str | Path = DEFAULT_ALIASES_PATH,
        folders_path: str | Path = "config/folders.json",
        file_trash_dir: str | Path = DEFAULT_FILE_TRASH_DIR,
        file_trash_manifest_path: str | Path = DEFAULT_FILE_TRASH_MANIFEST,
        shell_commands_path: str | Path = DEFAULT_SHELL_COMMANDS_PATH,
        script_checklist_dir: str | Path = DEFAULT_SCRIPT_CHECKLIST_DIR,
        script_preflight_dir: str | Path = DEFAULT_SCRIPT_PREFLIGHT_DIR,
        script_execution_readiness_dir: str | Path = DEFAULT_SCRIPT_EXECUTION_READINESS_DIR,
        script_run_simulation_dir: str | Path = DEFAULT_SCRIPT_RUN_SIMULATION_DIR,
        script_allowlist_simulation_dir: str | Path = DEFAULT_SCRIPT_ALLOWLIST_SIMULATION_DIR,
        file_type_allowlist_path: str | Path = DEFAULT_FILE_TYPE_ALLOWLIST_PATH,
        data_export_dir: str | Path = "exports",
        voice_model_path: str | Path | None = None,
        settings_path: str | Path = "config/settings.json",
        persona_path: str | Path = "config/persona.txt",
    ) -> None:
        self.name = name
        self.llm_client = llm_client
        self.use_llm = use_llm
        self.memory_store = memory_store or MemoryStore()
        self.notes_store = notes_store or NotesStore()
        self.tasks_store = tasks_store or TasksStore()
        self.history_store = history_store or HistoryStore()
        self.action_audit_store = action_audit_store or ActionAuditStore()
        self.voice_action_audit_store = voice_action_audit_store or VoiceActionAuditStore()
        self.outbox_store = outbox_store or OutboxStore(DEFAULT_OUTBOX_PATH)
        self.file_type_allowlist_store = FileTypeAllowlistStore(file_type_allowlist_path)
        self.launch_request_store = launch_request_store or LaunchRequestStore(
            DEFAULT_LAUNCH_REQUESTS_PATH,
            file_type_allowlist_path=file_type_allowlist_path,
        )
        self.aliases_path = aliases_path
        self.folders_path = Path(folders_path)
        self.file_trash_dir = Path(file_trash_dir)
        self.file_trash_manifest_path = Path(file_trash_manifest_path)
        self.shell_commands_path = Path(shell_commands_path)
        self.script_checklist_dir = Path(script_checklist_dir)
        self.script_preflight_dir = Path(script_preflight_dir)
        self.script_execution_readiness_dir = Path(script_execution_readiness_dir)
        self.script_run_simulation_dir = Path(script_run_simulation_dir)
        self.script_allowlist_simulation_dir = Path(script_allowlist_simulation_dir)
        self.data_export_dir = Path(data_export_dir)
        self.voice_model_path = voice_model_path
        self.settings_path = settings_path
        self.persona_path = persona_path
        self.shell_command_wizard_active = False
        
        # System indexing (lazy loaded)
        self.system_index: SystemIndex | None = None
        self.system_search: SystemSearch | None = None
        self.preferences_store: PreferencesStore | None = None
        self.index_store: IndexStore | None = None
        
        # Pending search result for execution when user confirms
        self.pending_search_item: IndexedItem | None = None
        self.pending_search_query: str | None = None

    def _build_system_index_text(self) -> str:
        """Build or rebuild the system index."""
        try:
            from assistant.index_builder import IndexBuilder
            builder = IndexBuilder()
            return builder.build_index_interactive()
        except Exception as exc:
            return f"Index build failed: {exc}. Make sure system indexing is enabled in settings."

    def _system_index_stats_text(self) -> str:
        """Get statistics about the current system index."""
        try:
            from assistant.index_builder import IndexBuilder
            builder = IndexBuilder()
            return builder.get_index_stats()
        except Exception as exc:
            return f"Index stats failed: {exc}. Try running 'scan system' first."

    def respond(self, user_text: str) -> AssistantResponse:
        """Return a response for one user message."""
        normalized = user_text.strip().lower()

        if not normalized:
            return AssistantResponse("Please type a command, or type 'help'.")

        if self.shell_command_wizard_active:
            return AssistantResponse(self._handle_shell_command_wizard_text(user_text))

        try:
            resolved_text = resolve_alias(user_text, self.aliases_path)
        except AliasError as exc:
            return AssistantResponse(f"Alias error: {exc}")
        if resolved_text != user_text.strip():
            user_text = resolved_text
            normalized = resolved_text.strip().lower()

        intent_text = normalize_intent(user_text)
        if intent_text is not None:
            user_text = intent_text
            normalized = intent_text.strip().lower()

        if normalized in {"exit", "quit", "bye"}:
            return AssistantResponse("Goodbye.", should_exit=True)

        # Handle confirmation of pending search result
        if normalized == "yes" and self.pending_search_item is not None:
            full_path = str(self.pending_search_item.full_path)
            query = self.pending_search_query or "unknown item"
            
            try:
                action = PendingAction(
                    kind="unrestricted",
                    target=full_path,
                    description=f"Open: {self.pending_search_item.name}",
                )
                result = execute_action(action)
                
                # Record access if successful
                if self.preferences_store is not None and "Action failed" not in result:
                    try:
                        self.preferences_store.record_access(self.pending_search_item.id)
                    except Exception:
                        pass  # Silently fail if recording access fails
                
                # Clear pending search
                self.pending_search_item = None
                self.pending_search_query = None
                
                return AssistantResponse(result)
            except Exception as e:
                self.pending_search_item = None
                self.pending_search_query = None
                return AssistantResponse(f"Error opening item: {e}")

        if normalized in {"help", "commands", "what can you do"}:
            return AssistantResponse(self._help_text())

        if normalized.startswith("help "):
            return AssistantResponse(command_help_text(user_text.strip()[5:]))

        if normalized in {"command reference", "full help", "command list"}:
            return AssistantResponse(command_reference_text())

        if normalized in {"about", "about assistant", "architecture", "system architecture"}:
            return AssistantResponse(about_text(self.name))

        if normalized in {"safety", "permissions", "security", "privacy"}:
            return AssistantResponse(self._safety_text())

        if normalized in {"permissions dashboard", "safety dashboard", "capability dashboard"}:
            return AssistantResponse(self._permission_dashboard_text())

        if normalized in {
            "safety snapshot",
            "review snapshot",
            "launch and shell snapshot",
            "shell and launch snapshot",
        }:
            return AssistantResponse(self._safety_snapshot_text())

        if normalized in {"safety snapshot launch", "launch safety snapshot", "launch review snapshot"}:
            return AssistantResponse(self._safety_snapshot_text(review_type="launch"))

        if normalized in {"safety snapshot shell", "shell safety snapshot", "shell review snapshot"}:
            return AssistantResponse(self._safety_snapshot_text(review_type="shell"))

        if normalized in {
            "safety snapshot scripts",
            "safety snapshot script",
            "script safety snapshot",
            "script review snapshot",
            "scripts safety snapshot",
        }:
            return AssistantResponse(self._safety_snapshot_text(review_type="scripts"))

        if normalized in {
            "safety snapshot scripts drift",
            "safety snapshot script drift",
            "script drift snapshot",
            "script drift safety snapshot",
            "scripts drift snapshot",
        }:
            return AssistantResponse(self._safety_snapshot_text(review_type="scripts-drift"))

        if normalized in {
            "safety snapshot scripts drift signature",
            "script drift snapshot signature",
            "scripts drift signature",
        }:
            return AssistantResponse(self._safety_snapshot_text(review_type="scripts-drift-signature"))

        if normalized in {
            "safety snapshot scripts drift hash",
            "script drift snapshot hash",
            "scripts drift hash",
        }:
            return AssistantResponse(self._safety_snapshot_text(review_type="scripts-drift-hash"))

        if normalized in {
            "safety snapshot scripts drift path",
            "script drift snapshot path",
            "scripts drift path",
        }:
            return AssistantResponse(self._safety_snapshot_text(review_type="scripts-drift-path"))

        for prefix in (
            "safety snapshot scripts drift threshold ",
            "script drift snapshot threshold ",
            "scripts drift threshold ",
        ):
            if normalized.startswith(prefix):
                return AssistantResponse(
                    self._script_drift_threshold_snapshot_text(user_text.strip()[len(prefix):])
                )

        if normalized in {"roadmap", "next steps", "project roadmap", "what next"}:
            return AssistantResponse(roadmap_text(self.name))

        if normalized in {"launch commands", "start commands", "startup commands", "how do i launch"}:
            return AssistantResponse(launch_commands_text())

        if normalized in {"actions", "allowed actions", "what can you open"}:
            return AssistantResponse(describe_allowed_actions())

        if normalized in {"launch requests", "app requests", "script requests"}:
            return AssistantResponse(self._launch_requests_text())

        if normalized in {
            "script allowlist design",
            "script allowlisting design",
            "design script allowlist",
            "script allowlist safety",
        }:
            return AssistantResponse(script_allowlist_design_text())

        if normalized in {
            "file type allowlist",
            "filetype allowlist",
            "file launch allowlist",
            "allowed file types",
        }:
            return AssistantResponse(self._file_type_allowlist_text())

        if normalized.startswith("allow file type "):
            return AssistantResponse(self._allow_file_type_text(user_text.strip()[16:]))

        if normalized.startswith("file type trust "):
            return AssistantResponse(self._file_type_trust_text(user_text.strip()[16:]))

        if normalized.startswith("trust file type source "):
            return AssistantResponse(self._set_file_type_source_trust_text(user_text.strip()[23:]))

        if normalized.startswith("trust file type signer "):
            return AssistantResponse(self._set_file_type_signer_trust_text(user_text.strip()[23:]))

        if normalized.startswith("trust file type thumbprint "):
            return AssistantResponse(self._set_file_type_thumbprint_trust_text(user_text.strip()[27:]))

        if normalized.startswith("trust file type issuer "):
            return AssistantResponse(self._set_file_type_issuer_trust_text(user_text.strip()[23:]))

        if normalized.startswith("trust file type validity "):
            return AssistantResponse(self._set_file_type_validity_trust_text(user_text.strip()[25:]))

        if normalized.startswith("trust file type revocation "):
            return AssistantResponse(self._set_file_type_revocation_trust_text(user_text.strip()[27:]))

        if normalized.startswith("disallow file type "):
            return AssistantResponse(self._disallow_file_type_text(user_text.strip()[19:]))

        if normalized.startswith("clear file type trust "):
            return AssistantResponse(self._clear_file_type_trust_text(user_text.strip()[22:]))

        if normalized.startswith("remove file type "):
            return AssistantResponse(self._disallow_file_type_text(user_text.strip()[17:]))

        if normalized.startswith("request app "):
            return AssistantResponse(self._request_app_text(user_text.strip()[12:]))

        if normalized.startswith("request script review "):
            return AssistantResponse(self._request_script_review_text(user_text.strip()[22:]))

        if normalized.startswith("script review checklist "):
            return AssistantResponse(self._script_review_checklist_text(user_text.strip()[24:]))

        if normalized.startswith("verify script review checklist "):
            return AssistantResponse(self._verify_script_review_checklist_text(user_text.strip()[31:]))

        if normalized.startswith("script allowlist preflight "):
            return AssistantResponse(self._script_allowlist_preflight_text(user_text.strip()[27:]))

        if normalized.startswith("script execution readiness "):
            return AssistantResponse(self._script_execution_readiness_text(user_text.strip()[27:]))

        if normalized.startswith("script readiness "):
            return AssistantResponse(self._script_execution_readiness_text(user_text.strip()[17:]))

        if normalized.startswith("confirm script run simulation "):
            return AssistantResponse(self._confirm_script_run_simulation_text(user_text.strip()[30:]))

        if normalized.startswith("script run simulation "):
            return AssistantResponse(self._confirm_script_run_simulation_text(user_text.strip()[22:]))

        if normalized.startswith("script allowlist entry simulation "):
            return AssistantResponse(self._script_allowlist_entry_simulation_text(user_text.strip()[34:]))

        if normalized.startswith("allowlist entry simulation "):
            return AssistantResponse(self._script_allowlist_entry_simulation_text(user_text.strip()[27:]))

        if normalized.startswith("request file review "):
            return AssistantResponse(self._request_file_review_text(user_text.strip()[20:]))

        if normalized.startswith("request document review "):
            return AssistantResponse(self._request_file_review_text(user_text.strip()[24:]))

        if normalized.startswith("request folder review "):
            return AssistantResponse(self._request_folder_review_text(user_text.strip()[22:]))

        if normalized in {"shell commands", "safe shell", "allowed shell commands"}:
            return AssistantResponse(self._shell_commands_text())

        if normalized in {"shell command guide", "shell allowlist guide", "safe shell guide"}:
            return AssistantResponse(self._shell_command_guide_text())

        if normalized in {"shell command wizard", "shell wizard", "safe shell wizard", "add shell command wizard"}:
            return AssistantResponse(self._start_shell_command_wizard_text())

        if normalized.startswith("shell review checklist "):
            return AssistantResponse(self._shell_review_checklist_text(user_text.strip()[23:]))

        if normalized.startswith("shell checklist "):
            return AssistantResponse(self._shell_review_checklist_text(user_text.strip()[16:]))

        if normalized.startswith("verify shell checklist "):
            return AssistantResponse(self._verify_shell_review_checklist_text(user_text.strip()[23:]))

        if normalized.startswith("shell checklist verify "):
            return AssistantResponse(self._verify_shell_review_checklist_text(user_text.strip()[23:]))

        if normalized.startswith("shell wizard add "):
            return AssistantResponse(self._add_shell_command_text(user_text.strip()[17:]))

        if normalized.startswith("add shell command "):
            return AssistantResponse(self._add_shell_command_text(user_text.strip()[18:]))

        if normalized.startswith("remove shell command "):
            return AssistantResponse(self._remove_shell_command_text(user_text.strip()[21:]))

        if normalized in {"outbox", "drafts", "show drafts"}:
            return AssistantResponse(self._outbox_text())

        if normalized in {"settings", "show settings"}:
            return AssistantResponse(self._settings_text())

        if normalized in {"status", "health", "system status"}:
            return AssistantResponse(self._status_text())

        if normalized in {"models", "list models", "ollama models", "local models"}:
            return AssistantResponse(self._models_text())

        if normalized in {"voice status", "voice setup", "check voice"}:
            return AssistantResponse(voice_status_text(self.voice_model_path))

        if normalized in {"voice confidence", "voice confidence status", "speech confidence"}:
            return AssistantResponse(voice_confidence_status_text())

        if normalized in {"voice safety drill", "voice drill", "low confidence voice drill"}:
            return AssistantResponse(voice_safety_drill_text())

        if normalized in {"wake status", "wake voice", "wake mode"}:
            return AssistantResponse(wake_status_text())

        if normalized in {"scan system", "build index", "index system"}:
            return AssistantResponse(self._build_system_index_text())

        if normalized in {"index stats", "index status", "system index status"}:
            return AssistantResponse(self._system_index_stats_text())

        if normalized in {"paths", "file paths", "data paths", "where is my data"}:
            return AssistantResponse(self._paths_text())

        if normalized in {"detected folders", "windows folders", "folder detection"}:
            return AssistantResponse(detected_folders_summary())

        if normalized in {"detected drives", "windows drives", "drive detection"}:
            return AssistantResponse(detected_drives_summary())

        if normalized in {"detected locations", "windows locations", "folder and drive detection"}:
            return AssistantResponse(detected_locations_summary())

        if normalized in {"file tools", "local files", "allowed files"}:
            return AssistantResponse(file_tools_help_text(self.folders_path))

        if normalized in {"bulk apply safety", "bulk apply plan", "bulk file apply safety"}:
            return AssistantResponse(self._bulk_apply_safety_text())

        if normalized in {"bulk apply review", "review bulk apply", "bulk file apply review"}:
            return AssistantResponse(self._bulk_apply_review_text())

        if normalized in {"bulk rollback plan", "bulk restore plan", "rollback bulk plan"}:
            return AssistantResponse(self._bulk_rollback_plan_text())

        if normalized in {"bulk write preflight", "bulk apply preflight", "preflight bulk write"}:
            return AssistantResponse(self._bulk_write_preflight_text())

        if normalized in {"bulk write checklist", "bulk write operator checklist", "bulk operator write checklist"}:
            return AssistantResponse(self._bulk_write_operator_checklist_text())

        if normalized in {
            "verify bulk write checklist",
            "bulk write checklist verify",
            "verify bulk operator write checklist",
        }:
            return AssistantResponse(self._verify_bulk_write_operator_checklist_text())

        if normalized in {"bulk restore checklist", "bulk restore operator checklist", "bulk operator restore checklist"}:
            return AssistantResponse(self._bulk_restore_operator_checklist_text())

        if normalized in {
            "verify bulk restore checklist",
            "bulk restore checklist verify",
            "verify bulk operator restore checklist",
        }:
            return AssistantResponse(self._verify_bulk_restore_operator_checklist_text())

        if normalized in {
            "bulk write command design",
            "confirmed bulk write design",
            "design bulk write command",
            "bulk write design",
        }:
            return AssistantResponse(self._bulk_write_command_design_text())

        if normalized in {
            "bulk restore command design",
            "confirmed bulk restore design",
            "design bulk restore command",
            "bulk restore design",
        }:
            return AssistantResponse(self._bulk_restore_command_design_text())

        if normalized in {"data report", "privacy report", "local data"}:
            return AssistantResponse(self._data_report_text())

        if normalized in {"export data", "backup data", "local backup"}:
            return AssistantResponse(self._export_data_text())

        if normalized in {"export safety reviews", "safety review export", "export safety audit", "export signed reviews"}:
            return AssistantResponse(self._export_safety_reviews_text())

        if normalized in {"backups", "list backups", "show backups"}:
            return AssistantResponse(self._backups_text())

        if normalized in {"briefing", "daily briefing", "good morning"}:
            return AssistantResponse(self._briefing_text())

        if normalized in {"memories", "memory", "show memories"}:
            return AssistantResponse(self._memory_text())

        if self._is_memory_question(normalized):
            return AssistantResponse(self._memory_text())

        if normalized in {"memory trash", "deleted memories", "show memory trash"}:
            return AssistantResponse(self._memory_trash_text())

        if normalized.startswith("restore memory "):
            return AssistantResponse(self._restore_memory_text(user_text.strip()[15:]))

        if normalized.startswith("restore deleted memory "):
            return AssistantResponse(self._restore_memory_text(user_text.strip()[23:]))

        if normalized.startswith("rename memory "):
            return AssistantResponse(self._rename_memory_text(user_text.strip()[14:]))

        if normalized.startswith("delete memory "):
            return self._delete_memory_response(user_text.strip()[14:])

        if normalized in {"notes", "show notes"}:
            return AssistantResponse(self._notes_text())

        if normalized.startswith("note "):
            return AssistantResponse(self._add_note_text(user_text.strip()[5:]))

        if normalized.startswith("take note "):
            return AssistantResponse(self._add_note_text(user_text.strip()[10:]))

        if normalized.startswith("draft message to "):
            return AssistantResponse(self._draft_message_text(user_text.strip()[17:]))

        if normalized.startswith("draft email to "):
            return AssistantResponse(self._draft_email_text(user_text.strip()[15:]))

        if normalized.startswith("draft network request "):
            return AssistantResponse(self._draft_network_request_text(user_text.strip()[22:]))

        if normalized.startswith(("send ", "email ", "message ", "post ", "request ")):
            return AssistantResponse(blocked_send_text())

        if normalized in {"tasks", "todo list", "show tasks"}:
            return AssistantResponse(self._tasks_text())

        if normalized in {"completed tasks", "done tasks"}:
            return AssistantResponse(self._completed_tasks_text())

        if normalized in {"all tasks", "task history"}:
            return AssistantResponse(self._all_tasks_text())

        if normalized in {"due today", "tasks due today", "today tasks"}:
            return AssistantResponse(self._due_today_text())

        if normalized in {"overdue", "overdue tasks"}:
            return AssistantResponse(self._overdue_tasks_text())

        if normalized in {"upcoming", "upcoming tasks"}:
            return AssistantResponse(self._upcoming_tasks_text())

        if normalized in {"due soon", "tasks due soon"}:
            return AssistantResponse(self._due_soon_tasks_text())

        if normalized in {"task stats", "todo stats", "task summary"}:
            return AssistantResponse(self._task_stats_text())

        if normalized in {"task trash", "deleted tasks", "show task trash"}:
            return AssistantResponse(self._task_trash_text())

        if normalized.startswith("todo "):
            return AssistantResponse(self._add_task_text(user_text.strip()[5:]))

        if normalized.startswith("task "):
            return AssistantResponse(self._add_task_text(user_text.strip()[5:]))

        if normalized.startswith("done "):
            return AssistantResponse(self._complete_task_text(user_text.strip()[5:]))

        if normalized.startswith("complete task "):
            return AssistantResponse(self._complete_task_text(user_text.strip()[14:]))

        if normalized.startswith("delete task "):
            return self._delete_task_response(user_text.strip()[12:])

        if normalized.startswith("restore task "):
            return AssistantResponse(self._restore_task_text(user_text.strip()[13:]))

        if normalized.startswith("reopen task "):
            return AssistantResponse(self._restore_task_text(user_text.strip()[12:]))

        if normalized.startswith("restore deleted task "):
            return AssistantResponse(self._restore_deleted_task_text(user_text.strip()[21:]))

        if normalized.startswith("rename task "):
            return AssistantResponse(self._rename_task_text(user_text.strip()[12:]))

        if normalized.startswith("due "):
            return AssistantResponse(self._set_task_due_date_text(user_text.strip()[4:]))

        if normalized.startswith("clear due "):
            return AssistantResponse(self._clear_task_due_date_text(user_text.strip()[10:]))

        if normalized.startswith("list files in "):
            return AssistantResponse(self._list_files_text(user_text.strip()[14:]))

        if normalized.startswith("search files in "):
            return AssistantResponse(self._search_files_text(user_text.strip()[16:]))

        if normalized.startswith("find files in "):
            return AssistantResponse(self._find_files_text(user_text.strip()[14:]))

        if normalized.startswith("search file names in "):
            return AssistantResponse(self._find_files_text(user_text.strip()[21:]))

        if normalized.startswith("read file in "):
            return AssistantResponse(self._read_file_text(user_text.strip()[13:]))

        if normalized.startswith("launch file in "):
            return self._launch_file_response(user_text.strip()[15:])

        if normalized.startswith("open file in "):
            return AssistantResponse(self._open_file_preview_text(user_text.strip()[13:]))

        if normalized.startswith("preview file in "):
            return AssistantResponse(self._open_file_preview_text(user_text.strip()[16:]))

        if normalized.startswith("preview replace in "):
            return AssistantResponse(self._preview_replace_text(user_text.strip()[19:]))

        if normalized.startswith("dry run replace in "):
            return AssistantResponse(self._preview_replace_text(user_text.strip()[19:]))

        if normalized.startswith("bulk replace apply plan in "):
            return AssistantResponse(self._bulk_replace_apply_plan_text(user_text.strip()[27:]))

        if normalized.startswith("backup bulk replace in "):
            return AssistantResponse(self._backup_bulk_replace_text(user_text.strip()[23:]))

        if normalized.startswith("approve bulk replace in "):
            return AssistantResponse(self._approve_bulk_replace_text(user_text.strip()[24:]))

        if normalized.startswith("preview rename files in "):
            return AssistantResponse(self._preview_rename_files_text(user_text.strip()[24:]))

        if normalized.startswith("dry run rename files in "):
            return AssistantResponse(self._preview_rename_files_text(user_text.strip()[24:]))

        if normalized.startswith("bulk rename apply plan in "):
            return AssistantResponse(self._bulk_rename_apply_plan_text(user_text.strip()[26:]))

        if normalized.startswith("backup bulk rename in "):
            return AssistantResponse(self._backup_bulk_rename_text(user_text.strip()[22:]))

        if normalized.startswith("approve bulk rename in "):
            return AssistantResponse(self._approve_bulk_rename_text(user_text.strip()[23:]))

        if normalized.startswith("delete file in "):
            return self._delete_file_response(user_text.strip()[15:])

        if normalized in {"file trash", "deleted files", "show file trash"}:
            return AssistantResponse(self._file_trash_text())

        if normalized.startswith("restore file "):
            return AssistantResponse(self._restore_file_text(user_text.strip()[13:]))

        if normalized.startswith("run shell "):
            return self._shell_command_response(user_text.strip()[10:])

        if normalized.startswith("search "):
            return AssistantResponse(self._search_text(user_text.strip()[7:]))

        if normalized.startswith("find "):
            return AssistantResponse(self._search_text(user_text.strip()[5:]))

        if normalized in {"history", "show history", "recent history"}:
            return AssistantResponse(self._history_text())

        if normalized in {"action audit", "actions audit", "audit actions"}:
            return AssistantResponse(self._action_audit_text())

        if normalized.startswith(("prune voice audit", "trim voice audit")):
            return self._voice_audit_retention_response(user_text.strip())

        if normalized.startswith("export voice audit"):
            return AssistantResponse(self._export_voice_action_audit_text(user_text.strip()))

        if normalized.startswith("voice audit"):
            return AssistantResponse(self._voice_action_audit_text(user_text.strip()))

        if normalized in {"voice action audit", "voice actions audit"}:
            return AssistantResponse(self._voice_action_audit_text("voice audit"))

        if normalized in {"clear history", "forget history"}:
            return AssistantResponse(self._clear_history())

        if normalized in {"forget memories", "clear memories"}:
            return AssistantResponse(self._clear_memories())

        if normalized.startswith("remember "):
            return AssistantResponse(self._remember_text(user_text.strip()[9:]))

        if normalized in {"hello", "hi", "hey"}:
            return AssistantResponse(f"Hello. I am {self.name}, running locally.")

        if normalized in {"time", "what time is it"}:
            current_time = datetime.now().strftime("%I:%M %p").lstrip("0")
            return AssistantResponse(f"The local time is {current_time}.")

        if normalized in {"date", "what is the date", "today"}:
            current_date = datetime.now().strftime("%A, %B %d, %Y")
            return AssistantResponse(f"Today is {current_date}.")

        action = parse_action(user_text)
        if action:
            return AssistantResponse(
                f"Please confirm: {action.description}. Type 'yes' to continue.",
                pending_action=action,
            )

        if self._looks_like_unlisted_launch_request(normalized):
            # Allow unrestricted launches if setting is enabled
            try:
                from assistant.settings import load_settings
                settings = load_settings(self.settings_path)
                if settings.allow_unrestricted_launch:
                    unrestricted_action = self._parse_unrestricted_launch(normalized)
                    if unrestricted_action:
                        return AssistantResponse(
                            f"Please confirm: {unrestricted_action.description}. Type 'yes' to continue.",
                            pending_action=unrestricted_action,
                        )
            except Exception:
                pass  # Fall through to blocked message if settings load fails
            
            return AssistantResponse(blocked_unlisted_launch_text())

        suggestions = suggest_commands(user_text)
        if suggestions:
            return AssistantResponse(unknown_command_text(user_text))

        if self.use_llm:
            return self._respond_with_llm(user_text.strip())

        # Try system indexing search as fallback for natural language file/folder/app queries
        # Only attempt search for simple natural language-like queries (not structured commands)
        if self._looks_like_search_query(normalized):
            search_text, pending_action = self._search_and_open_system_item(user_text)
            if not search_text.startswith("Unknown command"):
                return AssistantResponse(search_text, pending_action=pending_action)

        return AssistantResponse(unknown_command_text(user_text))

    def record_turn(self, user_text: str, assistant_text: str) -> None:
        """Record one conversation turn in local history."""
        self.history_store.append("user", user_text)
        self.history_store.append("assistant", assistant_text)

    def confirm_pending_action(self, action: PendingAction) -> str:
        """Execute a confirmed pending action."""
        if action.kind == "task_delete":
            task_number = int(action.target)
            task = self.tasks_store.delete_open(task_number)
            return f"Done: Moved task {task_number} to trash: {task.text}."
        if action.kind == "memory_delete":
            try:
                memory_number = int(action.target)
                memory = self.memory_store.delete(memory_number)
            except (ValueError, MemoryError) as exc:
                return f"Memory error: {exc}"
            return f"Done: Moved memory {memory_number} to trash: {memory.text}."
        if action.kind == "shell_command":
            try:
                command = get_shell_command(action.target, self.shell_commands_path)
                return run_shell_command(command)
            except ShellToolError as exc:
                return f"Shell command error: {exc}"
        if action.kind == "file_delete":
            try:
                folder_name, relative_path = self._parse_pending_file_target(action.target)
                entry = self._file_tools().move_file_to_trash(folder_name, relative_path)
            except FileToolError as exc:
                return f"File tools error: {exc}"
            return f"Done: Moved file to assistant trash: {entry.display_text()}."
        if action.kind == "file_launch":
            try:
                folder_name, relative_path = self._parse_pending_file_target(action.target)
                _, file_path = self._file_tools().resolve_allowlisted_file(folder_name, relative_path)
                extension = _file_extension_for_launch(file_path)
                if not self.file_type_allowlist_store.is_allowed_extension(extension):
                    return (
                        "File launch blocked: file type "
                        f"{extension} is not allowlisted. "
                        f"Use allow file type {extension}, then retry launch file in {folder_name} {relative_path}."
                    )
                trust = self.file_type_allowlist_store.evaluate_trust_signals(extension, file_path)
                if not trust.passed:
                    review_lines = "\n".join(f"- {note}" for note in trust.notes)
                    return (
                        f"File launch blocked by trust checks for {extension}.\n"
                        f"Signed-file review:\n{review_lines}"
                    )
                os.startfile(file_path)  # type: ignore[attr-defined]
            except (FileToolError, FileTypeAllowlistError, OSError) as exc:
                return f"File launch error: {exc}"
            review_lines = "\n".join(f"- {note}" for note in trust.notes)
            return (
                f"Done: Opened file in Windows: {folder_name}/{relative_path}.\n"
                f"Signed-file review for {extension}:\n{review_lines}\n"
                "Launch status: allowed by current trust policy."
            )
        if action.kind == "voice_audit_prune":
            try:
                result = self.voice_action_audit_store.prune_keep_latest(
                    int(action.target),
                    backup_dir=self.data_export_dir / "voice-audit-retention",
                )
            except (ValueError, VoiceAuditError) as exc:
                return f"Voice action audit error: {exc}"
            return result.summary()
        return execute_action(action)

    def _help_text(self) -> str:
        return (
            "Available commands: hello, time, date, help, actions, settings, "
            "about, models, voice status, voice confidence, voice safety drill, voice audit, paths, file tools, briefing, memories, remember, notes, note, tasks, todo, search, history, action audit, exit.\n"
            "Use command reference or full help for a categorized command list.\n"
            "Use help tasks, help memory, or help actions for focused help.\n"
            "Use about or architecture for a local system summary.\n"
            "Use safety or permissions for the local safety rules.\n"
            "Use permissions dashboard for a structured safety-limited feature map.\n"
            "Use roadmap or next steps for the project roadmap.\n"
            "Use launch commands for exact local startup commands.\n"
            "Use launch requests to review unlisted app/script requests without running them.\n"
            "Unknown questions can be answered by a local Ollama model when enabled.\n"
            "Local app/folder actions require confirmation before they run.\n"
            "Safe shell commands require confirmation: use shell commands, shell command guide, add shell command <name>: <argv>, then run shell <name>.\n"
            "Status is read-only: use status or health.\n"
            "Models are read-only: use models or list models.\n"
            "Voice status is read-only: use voice status or check voice.\n"
            "Voice confidence is read-only: use voice confidence to review how spoken confidence is reported.\n"
            "Voice safety drill is read-only: use voice safety drill to simulate low-confidence confirmation without the microphone.\n"
            "Voice audit is local text-only: use voice audit to review recognized voice command summaries without stored audio. Use voice audit retention keep <number> to preview cleanup, then prune voice audit keep <number> with confirmation.\n"
            "Wake voice loop is optional: use wake status for launch details.\n"
            "Paths are read-only: use paths, file paths, or data paths.\n"
            "Windows detection is read-only: use detected folders, detected drives, or detected locations.\n"
            "File tools are allowlisted: use file tools, list files in <folder>, search files in <folder> for <text>, find files in <folder> for <name>, read file in <folder> <relative path>, open file in <folder> <relative path> for a safe preview, launch file in <folder> <relative path> for confirmation-gated Windows open with file-type allowlist checks, preview replace in <folder> find <text> with <text>, preview rename files in <folder> replace <name> with <name>, delete file in <folder> <relative path>, file trash, or restore file <number>.\n"
            "Data report is read-only: use data report or privacy report.\n"
            "Data export is local-only: use export data or backup data.\n"
            "Backups are local: use backups or list backups.\n"
            "Briefing is read-only: use briefing or good morning.\n"
            "Memory is explicit: use remember, memories, rename memory, delete memory, memory trash, restore memory, or forget memories.\n"
            "Notes are local: use note or notes.\n"
            "Tasks are local: use todo, tasks, task stats, due soon, completed tasks, task trash, all tasks, due today, overdue, upcoming, done, restore task, restore deleted task, rename task, due, clear due, or delete task.\n"
            "Search is local: use search or find.\n"
            "History is local: use history or clear history.\n"
            "Action audit is local: use action audit.\n"
            "Aliases are local shortcuts loaded from config/aliases.json."
        )

    def _parse_unrestricted_launch(self, normalized: str) -> PendingAction | None:
        """Parse unrestricted launch request and return action for user confirmation."""
        # Remove launch prefixes and get the target
        # Order matters: longer prefixes should come before shorter ones to match correctly
        prefixes = [
            "open file ",
            "open folder ",
            "open document ",
            "run script ",
            "run unlisted ",
            "open ",
            "launch ",
            "start ",
            "run ",
            "execute ",
        ]
        
        target = None
        for prefix in prefixes:
            if normalized.startswith(prefix):
                target = normalized[len(prefix):].strip()
                break
        
        if not target:
            return None
        
        # Create action description based on target type
        if target.endswith(('.exe', '.bat', '.cmd', '.com', '.ps1')):
            description = f"Launch application: {target}"
        elif any(target.endswith(ext) for ext in ['.txt', '.pdf', '.doc', '.docx', '.xlsx', '.csv', '.json']):
            description = f"Open file: {target}"
        elif target in {'my pc', 'this pc', 'my computer', 'file explorer'}:
            description = f"Open file explorer"
        elif target.lower() in {'settings', 'windows settings'}:
            description = f"Open Windows settings"
        else:
            description = f"Open: {target}"
        
        return PendingAction(
            kind="unrestricted",
            target=target,
            description=description,
        )

    @staticmethod
    def _looks_like_unlisted_launch_request(normalized: str) -> bool:
        return normalized.startswith(
            (
                "open ",
                "launch ",
                "start ",
                "open file ",
                "open folder ",
                "open document ",
                "run script ",
                "run unlisted ",
                "run ",
                "execute ",
            )
        )

    def _settings_text(self) -> str:
        settings = AssistantSettings(
            assistant_name=self.name,
            model=self.llm_client.model if self.llm_client else "disabled",
            use_llm=self.use_llm,
            num_gpu=self.llm_client.num_gpu if self.llm_client else 0,
            notes_path=str(self.notes_store.path),
            tasks_path=str(self.tasks_store.path),
            outbox_path=str(self.outbox_store.path),
            aliases_path=str(self.aliases_path),
        )
        return f"Current settings: {settings.summary()}"

    def _paths_text(self) -> str:
        return format_path_report(
            {
                "Settings": self.settings_path,
                "Persona": self.persona_path,
                "Aliases": self.aliases_path,
                "Memory": self.memory_store.path,
                "Notes": self.notes_store.path,
                "Tasks": self.tasks_store.path,
                "History": self.history_store.path,
                "Action audit": self.action_audit_store.path,
                "Voice action audit": self.voice_action_audit_store.path,
                "Outbox": self.outbox_store.path,
                "Launch requests": self.launch_request_store.path,
                "Exports": self.data_export_dir,
                "Voice model": self.voice_model_path,
            }
        )

    def _safety_text(self) -> str:
        try:
            allowed = describe_allowed_actions()
        except Exception as exc:
            allowed = f"Could not read allowlists: {exc}"
        return safety_text(allowed)

    def _permission_dashboard_text(self) -> str:
        try:
            allowed = describe_allowed_actions()
        except Exception as exc:
            allowed = f"Could not read allowlists: {exc}"
        return permission_dashboard_text(allowed)

    def _safety_snapshot_text(self, review_type: str = "all", drift_threshold: int | None = None) -> str:
        return safety_snapshot_text(
            self.launch_request_store,
            self.shell_commands_path,
            review_type=review_type,
            script_checklist_dir=self.script_checklist_dir,
            script_preflight_dir=self.script_preflight_dir,
            script_execution_readiness_dir=self.script_execution_readiness_dir,
            script_run_simulation_dir=self.script_run_simulation_dir,
            script_allowlist_simulation_dir=self.script_allowlist_simulation_dir,
            drift_warning_threshold=drift_threshold,
        )

    def _script_drift_threshold_snapshot_text(self, text: str) -> str:
        try:
            threshold = _parse_drift_threshold(text)
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return self._safety_snapshot_text(review_type="scripts-drift", drift_threshold=threshold)

    def _shell_commands_text(self) -> str:
        try:
            return shell_commands_summary(self.shell_commands_path)
        except ShellToolError as exc:
            return f"Shell command error: {exc}"

    def _shell_command_guide_text(self) -> str:
        try:
            current = shell_commands_summary(self.shell_commands_path)
        except ShellToolError as exc:
            current = f"Shell command error: {exc}"
        return (
            "Safe shell command allowlist guide\n"
            "Add only simple diagnostic commands written as argv, not shell text.\n"
            "Format: add shell command <name>: <executable> [args...]\n"
            "Guided mode: shell command wizard, then reply with <name>: <executable> [args...]\n"
            "Remove: remove shell command <name>\n"
            "Example: add shell command python path: python -c is blocked, but python --version is allowed.\n"
            "Blocked: cmd, powershell, pwsh, scripts, inline code, pipes, redirection, chaining, destructive tools.\n"
            "Saving a command does not run it and shows static review notes, static risk scoring, and signed review metadata.\n"
            "Running still requires: run shell <name>, then confirmation.\n\n"
            f"{current}"
        )

    def _start_shell_command_wizard_text(self) -> str:
        self.shell_command_wizard_active = True
        try:
            return shell_command_wizard_text(self.shell_commands_path)
        except ShellToolError as exc:
            self.shell_command_wizard_active = False
            return f"Shell command error: {exc}"

    def _handle_shell_command_wizard_text(self, text: str) -> str:
        normalized = text.strip().lower()
        if normalized in {"cancel", "stop", "exit wizard", "quit wizard"}:
            self.shell_command_wizard_active = False
            return "Cancelled shell command wizard. No shell command was saved."
        if normalized in {"help", "guide", "shell command guide"}:
            try:
                return shell_command_wizard_text(self.shell_commands_path)
            except ShellToolError as exc:
                self.shell_command_wizard_active = False
                return f"Shell command error: {exc}"

        result = self._add_shell_command_text(text)
        if not result.startswith("Shell command error:"):
            self.shell_command_wizard_active = False
        return result

    def _add_shell_command_text(self, text: str) -> str:
        try:
            name, argv = parse_shell_command_request(text)
            command = add_shell_command(name, argv, self.shell_commands_path)
        except ShellToolError as exc:
            return f"Shell command error: {exc}"
        return (
            f"Saved safe shell command: {command.name}: {command.display()}\n"
            f"Nothing was run. To run it later: run shell {command.name}\n\n"
            f"{shell_command_static_review_notes(command)}\n\n"
            f"{shell_command_signed_review_text(latest_shell_review_metadata(self.shell_commands_path, 'add', command))}"
        )

    def _remove_shell_command_text(self, text: str) -> str:
        try:
            command = remove_shell_command(text, self.shell_commands_path)
        except ShellToolError as exc:
            return f"Shell command error: {exc}"
        return (
            f"Removed safe shell command: {command.name}: {command.display()}\n"
            "Nothing was run.\n\n"
            f"{shell_command_signed_review_text(latest_shell_review_metadata(self.shell_commands_path, 'remove', command))}"
        )

    def _shell_review_checklist_text(self, text: str) -> str:
        try:
            result = create_shell_review_checklist(
                text,
                commands_path=self.shell_commands_path,
                output_dir=self.data_export_dir / "shell-review-checklists",
            )
            return result.summary
        except ShellToolError as exc:
            return f"Shell command error: {exc}"

    def _verify_shell_review_checklist_text(self, text: str) -> str:
        try:
            result = verify_shell_review_checklist(
                text,
                commands_path=self.shell_commands_path,
                output_dir=self.data_export_dir / "shell-review-checklists",
            )
            return result.summary
        except ShellToolError as exc:
            return f"Shell command error: {exc}"

    def _launch_requests_text(self) -> str:
        try:
            return self.launch_request_store.summary()
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"

    def _file_type_allowlist_text(self) -> str:
        try:
            return self.file_type_allowlist_store.summary()
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"

    def _allow_file_type_text(self, text: str) -> str:
        if not text.strip():
            return "File type allowlist error: allow file type expects: allow file type <extension>"
        try:
            extension = self.file_type_allowlist_store.allow_extension(text)
            summary = self.file_type_allowlist_store.summary()
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return (
            f"File type allowlisted: {extension}."
            " This only marks eligibility for future file launch workflows and does not open files.\n"
            f"{summary}"
        )

    def _file_type_trust_text(self, text: str) -> str:
        extension = text.strip()
        if not extension:
            return "File type allowlist error: file type trust expects: file type trust <extension>"
        try:
            return self.file_type_allowlist_store.trust_policy_summary(extension)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"

    def _set_file_type_source_trust_text(self, text: str) -> str:
        extension_text, separator, sources_text = text.partition(":")
        if not separator:
            return (
                "File type allowlist error: trust file type source expects: "
                "trust file type source <extension>: <source path>[; <source path>...]"
            )
        try:
            policy = self.file_type_allowlist_store.set_trusted_sources(
                extension_text,
                _parse_semicolon_list(sources_text),
            )
            extension = normalize_file_extension(extension_text)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return (
            f"Updated trusted sources for {extension}.\n"
            f"Trusted sources: {', '.join(policy.trusted_sources) if policy.trusted_sources else 'none'}"
        )

    def _set_file_type_signer_trust_text(self, text: str) -> str:
        extension_text, separator, signers_text = text.partition(":")
        if not separator:
            return (
                "File type allowlist error: trust file type signer expects: "
                "trust file type signer <extension>: <signer token>[; <signer token>...]"
            )
        try:
            policy = self.file_type_allowlist_store.set_trusted_signers(
                extension_text,
                _parse_semicolon_list(signers_text),
            )
            extension = normalize_file_extension(extension_text)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return (
            f"Updated trusted signer tokens for {extension}.\n"
            f"Trusted signer tokens: {', '.join(policy.trusted_signers) if policy.trusted_signers else 'none'}"
        )

    def _set_file_type_thumbprint_trust_text(self, text: str) -> str:
        extension_text, separator, thumbprints_text = text.partition(":")
        if not separator:
            return (
                "File type allowlist error: trust file type thumbprint expects: "
                "trust file type thumbprint <extension>: <thumbprint>[; <thumbprint>...]"
            )
        try:
            policy = self.file_type_allowlist_store.set_pinned_thumbprints(
                extension_text,
                _parse_semicolon_list(thumbprints_text),
            )
            extension = normalize_file_extension(extension_text)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return (
            f"Updated pinned signer thumbprints for {extension}.\n"
            f"Pinned thumbprints: {', '.join(policy.pinned_thumbprints) if policy.pinned_thumbprints else 'none'}"
        )

    def _set_file_type_issuer_trust_text(self, text: str) -> str:
        extension_text, separator, issuers_text = text.partition(":")
        if not separator:
            return (
                "File type allowlist error: trust file type issuer expects: "
                "trust file type issuer <extension>: <issuer token>[; <issuer token>...]"
            )
        try:
            policy = self.file_type_allowlist_store.set_trusted_issuers(
                extension_text,
                _parse_semicolon_list(issuers_text),
            )
            extension = normalize_file_extension(extension_text)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return (
            f"Updated trusted issuer tokens for {extension}.\n"
            f"Trusted issuers: {', '.join(policy.trusted_issuers) if policy.trusted_issuers else 'none'}"
        )

    def _set_file_type_validity_trust_text(self, text: str) -> str:
        extension_text, separator, mode_text = text.partition(":")
        if not separator:
            return (
                "File type allowlist error: trust file type validity expects: "
                "trust file type validity <extension>: required|off"
            )

        mode = mode_text.strip().lower()
        if mode in {"required", "on", "true", "strict"}:
            require_valid = True
        elif mode in {"off", "false", "optional", "none"}:
            require_valid = False
        else:
            return "File type allowlist error: validity mode must be required or off."

        try:
            policy = self.file_type_allowlist_store.set_validity_requirement(
                extension_text,
                require_valid,
            )
            extension = normalize_file_extension(extension_text)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return (
            f"Updated certificate validity requirement for {extension}.\n"
            "Certificate validity: "
            + ("required" if policy.require_valid_certificate else "not required")
        )

    def _set_file_type_revocation_trust_text(self, text: str) -> str:
        extension_text, separator, mode_text = text.partition(":")
        if not separator:
            return (
                "File type allowlist error: trust file type revocation expects: "
                "trust file type revocation <extension>: required|off|ocsp|crl|both"
            )

        mode = mode_text.strip().lower()
        if mode in {"required", "on", "true", "strict"}:
            require_revocation = True
            revocation_mode = "online"
        elif mode == "ocsp":
            require_revocation = True
            revocation_mode = "ocsp"
        elif mode == "crl":
            require_revocation = True
            revocation_mode = "crl"
        elif mode in {"both", "ocsp+crl", "crl+ocsp"}:
            require_revocation = True
            revocation_mode = "both"
        elif mode in {"off", "false", "optional", "none"}:
            require_revocation = False
            revocation_mode = "online"
        else:
            return "File type allowlist error: revocation mode must be required, off, ocsp, crl, or both."

        try:
            policy = self.file_type_allowlist_store.set_revocation_requirement(
                extension_text,
                require_revocation,
                revocation_mode=revocation_mode,
            )
            extension = normalize_file_extension(extension_text)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        revocation_text = (
            f"required (mode: {policy.revocation_mode})"
            if policy.require_revocation_check
            else "not required"
        )
        return (
            f"Updated certificate revocation check requirement for {extension}.\n"
            "Certificate revocation check: " + revocation_text
        )

    def _disallow_file_type_text(self, text: str) -> str:
        if not text.strip():
            return "File type allowlist error: disallow file type expects: disallow file type <extension>"
        try:
            extension = self.file_type_allowlist_store.disallow_extension(text)
            summary = self.file_type_allowlist_store.summary()
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return (
            f"File type removed from allowlist: {extension}."
            " Future file launch workflows for this type are blocked again.\n"
            f"{summary}"
        )

    def _clear_file_type_trust_text(self, text: str) -> str:
        extension = text.strip()
        if not extension:
            return "File type allowlist error: clear file type trust expects: clear file type trust <extension>"
        try:
            clean_extension = self.file_type_allowlist_store.clear_trust_policy(extension)
            summary = self.file_type_allowlist_store.trust_policy_summary(clean_extension)
        except FileTypeAllowlistError as exc:
            return f"File type allowlist error: {exc}"
        return f"Cleared trust policy for {clean_extension}.\n{summary}"

    def _request_app_text(self, text: str) -> str:
        if ":" not in text:
            return "Launch request error: request app expects: request app <name>: <exe>"
        name, target = (part.strip() for part in text.split(":", 1))
        try:
            request = self.launch_request_store.request_app(name, target)
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return f"Launch request saved locally, not run: {request.display_text()}"

    def _request_script_review_text(self, text: str) -> str:
        if ":" not in text:
            return (
                "Launch request error: request script review expects: "
                "request script review <name>: <path>"
            )
        name, target = (part.strip() for part in text.split(":", 1))
        try:
            request = self.launch_request_store.request_script_review(name, target)
            script_review_number = self.launch_request_store.script_review_count()
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return (
            f"Script review request saved locally, not run: {request.display_text()}\n"
            f"Next review step: script review checklist {script_review_number}"
        )

    def _script_review_checklist_text(self, text: str) -> str:
        try:
            request_number = _parse_positive_int(text, "script review checklist")
            result = self.launch_request_store.create_script_review_checklist(
                request_number,
                output_dir=self.script_checklist_dir,
            )
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return result.summary

    def _verify_script_review_checklist_text(self, text: str) -> str:
        try:
            request_number = _parse_positive_int(text, "verify script review checklist")
            result = self.launch_request_store.verify_script_review_checklist(
                request_number,
                output_dir=self.script_checklist_dir,
            )
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return result.summary

    def _script_allowlist_preflight_text(self, text: str) -> str:
        try:
            request_number = _parse_positive_int(text, "script allowlist preflight")
            result = self.launch_request_store.create_script_allowlist_preflight(
                request_number,
                checklist_dir=self.script_checklist_dir,
                output_dir=self.script_preflight_dir,
            )
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return result.summary

    def _script_execution_readiness_text(self, text: str) -> str:
        try:
            request_number = _parse_positive_int(text, "script execution readiness")
            result = self.launch_request_store.create_script_execution_readiness_bundle(
                request_number,
                checklist_dir=self.script_checklist_dir,
                preflight_dir=self.script_preflight_dir,
                output_dir=self.script_execution_readiness_dir,
            )
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return result.summary

    def _confirm_script_run_simulation_text(self, text: str) -> str:
        request_text, separator, phrase_text = text.partition(":")
        if not separator:
            return (
                "Launch request error: confirm script run simulation expects: "
                "confirm script run simulation <request number>: confirm script run"
            )
        try:
            request_number = _parse_positive_int(request_text, "confirm script run simulation")
            result = self.launch_request_store.simulate_confirmed_script_run(
                request_number,
                typed_confirmation=phrase_text.strip(),
                readiness_dir=self.script_execution_readiness_dir,
                output_dir=self.script_run_simulation_dir,
            )
            self.action_audit_store.record(
                PendingAction(
                    kind="script_run_simulation",
                    target=str(result.simulation_dir),
                    description=f"Script run simulation for request {request_number}",
                ),
                status="reviewed",
                requested_by="confirm script run simulation",
                result=f"Simulation {result.status}; no script executed.",
            )
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        except AuditError as exc:
            return f"Action audit error: {exc}"
        return result.summary

    def _script_allowlist_entry_simulation_text(self, text: str) -> str:
        request_text, separator, argv_text = text.partition(":")
        if not separator:
            return (
                "Launch request error: script allowlist entry simulation expects: "
                "script allowlist entry simulation <request number>: <interpreter> [args...]"
            )
        try:
            request_number = _parse_positive_int(request_text, "script allowlist entry simulation")
            result = self.launch_request_store.simulate_script_allowlist_entry(
                request_number,
                interpreter_argv_text=argv_text.strip(),
                readiness_dir=self.script_execution_readiness_dir,
                output_dir=self.script_allowlist_simulation_dir,
            )
            self.action_audit_store.record(
                PendingAction(
                    kind="script_allowlist_entry_simulation",
                    target=str(result.simulation_dir),
                    description=f"Script allowlist-entry simulation for request {request_number}",
                ),
                status="reviewed",
                requested_by="script allowlist entry simulation",
                result=f"Simulation {result.status}; no script executed.",
            )
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        except AuditError as exc:
            return f"Action audit error: {exc}"
        return result.summary

    def _request_file_review_text(self, text: str) -> str:
        if ":" not in text:
            return (
                "Launch request error: request file review expects: "
                "request file review <name>: <path>"
            )
        name, target = (part.strip() for part in text.split(":", 1))
        try:
            request = self.launch_request_store.request_file_review(name, target)
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        gate_text = (
            "Launch eligibility: file type is explicitly allowlisted for future launch workflows."
            if request.file_type_allowed_for_launch
            else "Launch eligibility: blocked until this file type is explicitly allowlisted."
        )
        return f"File review request saved locally, not run: {request.display_text()}\n{gate_text}"

    def _request_folder_review_text(self, text: str) -> str:
        if ":" not in text:
            return (
                "Launch request error: request folder review expects: "
                "request folder review <name>: <path>"
            )
        name, target = (part.strip() for part in text.split(":", 1))
        try:
            request = self.launch_request_store.request_folder_review(name, target)
        except LaunchRequestError as exc:
            return f"Launch request error: {exc}"
        return f"Folder review request saved locally, not run: {request.display_text()}"

    @staticmethod
    def _is_memory_question(normalized: str) -> bool:
        memory_phrases = (
            "what do you remember",
            "what do you know about me",
            "what do you know about how i",
            "how do i like",
            "my preferences",
        )
        return any(phrase in normalized for phrase in memory_phrases)

    def _memory_text(self) -> str:
        try:
            return self.memory_store.summary()
        except MemoryError as exc:
            return f"Memory error: {exc}"

    def _data_report_text(self) -> str:
        try:
            return build_report_from_stores(
                self.memory_store,
                self.notes_store,
                self.tasks_store,
                self.outbox_store,
                self.history_store,
                self.action_audit_store,
            ).summary()
        except (MemoryError, NotesError, TasksError, OutboxError, HistoryError, AuditError) as exc:
            return f"Data report error: {exc}"

    def _status_text(self) -> str:
        model = self.llm_client.model if self.llm_client else "disabled"
        try:
            return collect_status_from_stores(
                assistant_name=self.name,
                model=model,
                use_llm=self.use_llm,
                memory_store=self.memory_store,
                notes_store=self.notes_store,
                tasks_store=self.tasks_store,
                outbox_store=self.outbox_store,
                history_store=self.history_store,
                action_audit_store=self.action_audit_store,
            ).summary()
        except (MemoryError, NotesError, TasksError, OutboxError, HistoryError, AuditError, OSError) as exc:
            return f"Status error: {exc}"

    def _models_text(self) -> str:
        configured_model = self.llm_client.model if self.llm_client else "disabled"
        try:
            models = list_ollama_models()
        except ModelToolError as exc:
            return f"Model error: {exc} Start Ollama, then try models again."

        if not models:
            return f"Configured model: {configured_model}\nInstalled Ollama models: none"

        lines = [
            f"Configured model: {configured_model}",
            "Installed Ollama models:",
        ]
        lines.extend(f"- {model}" for model in models)
        return "\n".join(lines)

    def _export_data_text(self) -> str:
        try:
            export_dir = export_data_from_stores(
                self.memory_store,
                self.notes_store,
                self.tasks_store,
                self.outbox_store,
                self.history_store,
                self.action_audit_store,
                output_dir=self.data_export_dir,
            )
        except (MemoryError, NotesError, TasksError, OutboxError, HistoryError, AuditError, OSError) as exc:
            return f"Data export error: {exc}"
        return f"Exported local assistant data to: {export_dir}"

    def _export_safety_reviews_text(self) -> str:
        try:
            export_dir = export_safety_reviews(
                shell_commands_path=self.shell_commands_path,
                bulk_preflight_dir=self.data_export_dir / "bulk-write-preflights",
                launch_requests_path=self.launch_request_store.path,
                script_checklist_dir=self.script_checklist_dir,
                script_preflight_dir=self.script_preflight_dir,
                output_dir=self.data_export_dir / "safety-review-exports",
            )
            return safety_review_export_summary(export_dir)
        except SafetyReviewExportError as exc:
            return f"Safety review export error: {exc}"

    def _backups_text(self) -> str:
        try:
            return backups_summary(self.data_export_dir)
        except OSError as exc:
            return f"Backups error: {exc}"

    def _briefing_text(self) -> str:
        try:
            return build_briefing(
                self.memory_store,
                self.notes_store,
                self.tasks_store,
            ).summary()
        except BriefingError as exc:
            return f"Briefing error: {exc}"

    def _remember_text(self, text: str) -> str:
        try:
            item = self.memory_store.remember(text)
        except MemoryError as exc:
            return f"Memory error: {exc}"
        return f"Remembered: {item.text}"

    def _clear_memories(self) -> str:
        try:
            count = self.memory_store.clear()
        except MemoryError as exc:
            return f"Memory error: {exc}"
        return f"Cleared {count} saved memories."

    def _rename_memory_text(self, text: str) -> str:
        if " to " not in text:
            return "Memory error: rename memory expects: rename memory <number> to <new text>."
        number_text, new_text = (part.strip() for part in text.split(" to ", 1))
        try:
            memory = self.memory_store.rename(int(number_text), new_text)
        except (ValueError, MemoryError) as exc:
            return f"Memory error: {exc}"
        return f"Renamed memory {number_text}: {memory.text}"

    def _delete_memory_response(self, text: str) -> AssistantResponse:
        try:
            memory_number = int(text.strip())
            memories = self.memory_store.list_memories()
            if memory_number < 1 or memory_number > len(memories):
                raise MemoryError(f"Memory number must be between 1 and {len(memories)}.")
            memory = memories[memory_number - 1]
        except (ValueError, MemoryError) as exc:
            return AssistantResponse(f"Memory error: {exc}")

        action = PendingAction(
            kind="memory_delete",
            target=str(memory_number),
            description=f"Move memory {memory_number} to trash: {memory.text}",
        )
        return AssistantResponse(
            f"Please confirm: {action.description}. Type 'yes' to continue.",
            pending_action=action,
        )

    def _memory_trash_text(self) -> str:
        try:
            return self.memory_store.deleted_summary()
        except MemoryError as exc:
            return f"Memory error: {exc}"

    def _restore_memory_text(self, text: str) -> str:
        try:
            memory_number = int(text.strip())
            memory = self.memory_store.restore_deleted(memory_number)
        except (ValueError, MemoryError) as exc:
            return f"Memory error: {exc}"
        return f"Restored memory {memory_number}: {memory.text}"

    def _notes_text(self) -> str:
        try:
            return self.notes_store.summary(limit=10)
        except NotesError as exc:
            return f"Notes error: {exc}"

    def _add_note_text(self, text: str) -> str:
        try:
            item = self.notes_store.add(text)
        except NotesError as exc:
            return f"Notes error: {exc}"
        return f"Noted: {item.text}"

    def _outbox_text(self) -> str:
        try:
            return self.outbox_store.summary()
        except OutboxError as exc:
            return f"Outbox error: {exc}"

    def _draft_message_text(self, text: str) -> str:
        recipient, separator, body = text.partition(":")
        if not separator:
            return "Outbox error: draft message expects: draft message to <recipient>: <text>"
        try:
            draft = self.outbox_store.draft_message(recipient, body)
        except OutboxError as exc:
            return f"Outbox error: {exc}"
        return f"Draft saved locally, not sent: {draft.display_text()}"

    def _draft_email_text(self, text: str) -> str:
        recipient, separator, remainder = text.partition(" subject ")
        if not separator:
            return "Outbox error: draft email expects: draft email to <recipient> subject <subject>: <text>"
        subject, body_separator, body = remainder.partition(":")
        if not body_separator:
            return "Outbox error: draft email expects: draft email to <recipient> subject <subject>: <text>"
        try:
            draft = self.outbox_store.draft_email(recipient, subject, body)
        except OutboxError as exc:
            return f"Outbox error: {exc}"
        return f"Draft saved locally, not sent: {draft.display_text()}"

    def _draft_network_request_text(self, text: str) -> str:
        parts = text.strip().split(maxsplit=2)
        if len(parts) < 2:
            return "Outbox error: draft network request expects: draft network request GET <url> [note]"
        method = parts[0]
        url = parts[1]
        note = parts[2] if len(parts) == 3 else ""
        try:
            draft = self.outbox_store.draft_network_request(method, url, note)
        except OutboxError as exc:
            return f"Outbox error: {exc}"
        return f"Draft saved locally, request not made: {draft.display_text()}"

    def _search_text(self, query: str) -> str:
        search = LocalSearch(
            self.memory_store,
            self.notes_store,
            self.tasks_store,
            self.history_store,
        )
        try:
            return search.summary(query)
        except LocalSearchError as exc:
            return f"Search error: {exc}"

    def _file_tools(self) -> AllowlistedFileTools:
        return AllowlistedFileTools(
            self.folders_path,
            trash_dir=self.file_trash_dir,
            manifest_path=self.file_trash_manifest_path,
            bulk_backup_dir=self.data_export_dir / "bulk-file-backups",
            bulk_approval_dir=self.data_export_dir / "bulk-file-approvals",
            bulk_review_dir=self.data_export_dir / "bulk-apply-reviews",
            bulk_rollback_dir=self.data_export_dir / "bulk-rollback-plans",
            bulk_preflight_dir=self.data_export_dir / "bulk-write-preflights",
            bulk_checklist_dir=self.data_export_dir / "bulk-review-checklists",
        )

    def _list_files_text(self, folder_name: str) -> str:
        try:
            return self._file_tools().list_files_summary(folder_name)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _search_files_text(self, text: str) -> str:
        folder_name, separator, query = text.partition(" for ")
        if not separator:
            return "File tools error: search files expects: search files in <folder> for <text>"
        try:
            return self._file_tools().search_files_summary(folder_name, query)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _find_files_text(self, text: str) -> str:
        folder_name, separator, query = text.partition(" for ")
        if not separator:
            return "File tools error: filename search expects: find files in <folder> for <name text>"
        try:
            return self._file_tools().search_file_names_summary(folder_name, query)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _read_file_text(self, text: str) -> str:
        try:
            folder_name, relative_path = self._file_tools().parse_read_request(text)
            return self._file_tools().read_file_summary(folder_name, relative_path)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _open_file_preview_text(self, text: str) -> str:
        try:
            folder_name, relative_path = self._file_tools().parse_read_request(text)
            return self._file_tools().open_file_preview_summary(folder_name, relative_path)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _launch_file_response(self, text: str) -> AssistantResponse:
        try:
            folder_name, relative_path = self._file_tools().parse_read_request(text)
            _, file_path = self._file_tools().resolve_allowlisted_file(folder_name, relative_path)
            extension = _file_extension_for_launch(file_path)
            if not self.file_type_allowlist_store.is_allowed_extension(extension):
                return AssistantResponse(
                    "File launch blocked: file type "
                    f"{extension} is not allowlisted. "
                    f"Use allow file type {extension}, then retry launch file in {folder_name} {relative_path}. "
                    f"You can still use open file in {folder_name} {relative_path} for a safe preview."
                )
            trust = self.file_type_allowlist_store.evaluate_trust_signals(extension, file_path)
            if not trust.passed:
                review_lines = "\n".join(f"- {note}" for note in trust.notes)
                return AssistantResponse(
                    f"File launch blocked by trust checks for {extension}.\n"
                    f"Signed-file review:\n{review_lines}"
                )
        except (FileToolError, FileTypeAllowlistError) as exc:
            return AssistantResponse(f"File launch error: {exc}")

        action = PendingAction(
            kind="file_launch",
            target=self._pending_file_target(folder_name, relative_path),
            description=f"Open file in Windows: {folder_name}/{relative_path}",
        )
        review_lines = "\n".join(f"- {note}" for note in trust.notes)
        return AssistantResponse(
            f"Signed-file review for {extension}:\n"
            f"{review_lines}\n"
            "Launch status: allowed by current trust policy.\n"
            f"Please confirm: {action.description}. Type 'yes' to continue.",
            pending_action=action,
        )

    def _preview_replace_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" find ")
        if not separator:
            return "File tools error: preview replace expects: preview replace in <folder> find <text> with <text>"
        old_text, with_separator, new_text = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: preview replace expects: preview replace in <folder> find <text> with <text>"
        try:
            return self._file_tools().bulk_replace_plan_summary(folder_name, old_text, new_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _preview_rename_files_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" replace ")
        if not separator:
            return "File tools error: preview rename expects: preview rename files in <folder> replace <name text> with <name text>"
        old_text, with_separator, new_text = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: preview rename expects: preview rename files in <folder> replace <name text> with <name text>"
        try:
            return self._file_tools().bulk_rename_plan_summary(folder_name, old_text, new_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _bulk_apply_safety_text(self) -> str:
        return self._file_tools().bulk_apply_safety_text()

    def _bulk_write_command_design_text(self) -> str:
        return self._file_tools().bulk_write_command_design_text()

    def _bulk_restore_command_design_text(self) -> str:
        return self._file_tools().bulk_restore_command_design_text()

    def _bulk_apply_review_text(self) -> str:
        try:
            review = self._file_tools().create_bulk_apply_review()
            self.action_audit_store.record(
                PendingAction(
                    kind="bulk_apply_review",
                    target=str(review.review_dir),
                    description=review.audit_description,
                ),
                status="reviewed",
                requested_by="bulk apply review",
                result="Review created; no files changed.",
            )
            return review.summary
        except (FileToolError, AuditError) as exc:
            return f"File tools error: {exc}"

    def _bulk_rollback_plan_text(self) -> str:
        try:
            rollback = self._file_tools().create_bulk_rollback_plan()
            self.action_audit_store.record(
                PendingAction(
                    kind="bulk_rollback_plan",
                    target=str(rollback.rollback_dir),
                    description=rollback.audit_description,
                ),
                status="reviewed",
                requested_by="bulk rollback plan",
                result="Rollback plan created; no files changed.",
            )
            return rollback.summary
        except (FileToolError, AuditError) as exc:
            return f"File tools error: {exc}"

    def _bulk_write_preflight_text(self) -> str:
        try:
            preflight = self._file_tools().create_bulk_write_preflight()
            self.action_audit_store.record(
                PendingAction(
                    kind="bulk_write_preflight",
                    target=str(preflight.preflight_dir),
                    description=preflight.audit_description,
                ),
                status="reviewed",
                requested_by="bulk write preflight",
                result="Write preflight created; no files changed.",
            )
            return preflight.summary
        except (FileToolError, AuditError) as exc:
            return f"File tools error: {exc}"

    def _bulk_write_operator_checklist_text(self) -> str:
        try:
            checklist = self._file_tools().create_bulk_write_operator_checklist()
            self.action_audit_store.record(
                PendingAction(
                    kind="bulk_write_operator_checklist",
                    target=str(checklist.checklist_dir),
                    description=checklist.audit_description,
                ),
                status="reviewed",
                requested_by="bulk write checklist",
                result="Write checklist created; no files changed.",
            )
            return checklist.summary
        except (FileToolError, AuditError) as exc:
            return f"File tools error: {exc}"

    def _bulk_restore_operator_checklist_text(self) -> str:
        try:
            checklist = self._file_tools().create_bulk_restore_operator_checklist()
            self.action_audit_store.record(
                PendingAction(
                    kind="bulk_restore_operator_checklist",
                    target=str(checklist.checklist_dir),
                    description=checklist.audit_description,
                ),
                status="reviewed",
                requested_by="bulk restore checklist",
                result="Restore checklist created; no files changed.",
            )
            return checklist.summary
        except (FileToolError, AuditError) as exc:
            return f"File tools error: {exc}"

    def _verify_bulk_write_operator_checklist_text(self) -> str:
        try:
            verification = self._file_tools().verify_bulk_write_operator_checklist()
            self.action_audit_store.record(
                PendingAction(
                    kind="bulk_write_checklist_verification",
                    target=str(verification.checklist_dir or ""),
                    description=verification.audit_description,
                ),
                status="reviewed",
                requested_by="verify bulk write checklist",
                result=f"Checklist verification: {verification.status}; no files changed.",
            )
            return verification.summary
        except (FileToolError, AuditError) as exc:
            return f"File tools error: {exc}"

    def _verify_bulk_restore_operator_checklist_text(self) -> str:
        try:
            verification = self._file_tools().verify_bulk_restore_operator_checklist()
            self.action_audit_store.record(
                PendingAction(
                    kind="bulk_restore_checklist_verification",
                    target=str(verification.checklist_dir or ""),
                    description=verification.audit_description,
                ),
                status="reviewed",
                requested_by="verify bulk restore checklist",
                result=f"Checklist verification: {verification.status}; no files changed.",
            )
            return verification.summary
        except (FileToolError, AuditError) as exc:
            return f"File tools error: {exc}"

    def _bulk_replace_apply_plan_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" find ")
        if not separator:
            return "File tools error: bulk replace apply plan expects: bulk replace apply plan in <folder> find <text> with <text>"
        old_text, with_separator, new_text = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: bulk replace apply plan expects: bulk replace apply plan in <folder> find <text> with <text>"
        try:
            return self._file_tools().bulk_replace_apply_plan_summary(folder_name, old_text, new_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _bulk_rename_apply_plan_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" replace ")
        if not separator:
            return "File tools error: bulk rename apply plan expects: bulk rename apply plan in <folder> replace <name text> with <name text>"
        old_text, with_separator, new_text = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: bulk rename apply plan expects: bulk rename apply plan in <folder> replace <name text> with <name text>"
        try:
            return self._file_tools().bulk_rename_apply_plan_summary(folder_name, old_text, new_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _backup_bulk_replace_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" find ")
        if not separator:
            return "File tools error: backup bulk replace expects: backup bulk replace in <folder> find <text> with <text>"
        old_text, with_separator, new_text = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: backup bulk replace expects: backup bulk replace in <folder> find <text> with <text>"
        try:
            return self._file_tools().backup_bulk_replace_plan(folder_name, old_text, new_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _backup_bulk_rename_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" replace ")
        if not separator:
            return "File tools error: backup bulk rename expects: backup bulk rename in <folder> replace <name text> with <name text>"
        old_text, with_separator, new_text = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: backup bulk rename expects: backup bulk rename in <folder> replace <name text> with <name text>"
        try:
            return self._file_tools().backup_bulk_rename_plan(folder_name, old_text, new_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _approve_bulk_replace_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" find ")
        if not separator:
            return "File tools error: approve bulk replace expects: approve bulk replace in <folder> find <text> with <text> files <numbers|all>"
        old_text, with_separator, remainder = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: approve bulk replace expects: approve bulk replace in <folder> find <text> with <text> files <numbers|all>"
        new_text, files_separator, selection_text = remainder.partition(" files ")
        if not files_separator:
            return "File tools error: approve bulk replace expects: approve bulk replace in <folder> find <text> with <text> files <numbers|all>"
        try:
            return self._file_tools().approve_bulk_replace_plan(folder_name, old_text, new_text, selection_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _approve_bulk_rename_text(self, text: str) -> str:
        folder_name, separator, remainder = text.partition(" replace ")
        if not separator:
            return "File tools error: approve bulk rename expects: approve bulk rename in <folder> replace <name text> with <name text> files <numbers|all>"
        old_text, with_separator, remainder = remainder.partition(" with ")
        if not with_separator:
            return "File tools error: approve bulk rename expects: approve bulk rename in <folder> replace <name text> with <name text> files <numbers|all>"
        new_text, files_separator, selection_text = remainder.partition(" files ")
        if not files_separator:
            return "File tools error: approve bulk rename expects: approve bulk rename in <folder> replace <name text> with <name text> files <numbers|all>"
        try:
            return self._file_tools().approve_bulk_rename_plan(folder_name, old_text, new_text, selection_text)
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _delete_file_response(self, text: str) -> AssistantResponse:
        try:
            folder_name, relative_path = self._file_tools().parse_file_request(text, "delete")
            self._file_tools().validate_trash_candidate(folder_name, relative_path)
        except FileToolError as exc:
            return AssistantResponse(f"File tools error: {exc}")

        action = PendingAction(
            kind="file_delete",
            target=self._pending_file_target(folder_name, relative_path),
            description=f"Move file to assistant trash: {folder_name}/{relative_path}",
        )
        return AssistantResponse(
            f"Please confirm: {action.description}. Type 'yes' to continue.",
            pending_action=action,
        )

    def _file_trash_text(self) -> str:
        try:
            return self._file_tools().file_trash_summary()
        except FileToolError as exc:
            return f"File tools error: {exc}"

    def _restore_file_text(self, entry_number_text: str) -> str:
        try:
            entry_number = int(entry_number_text.strip())
        except ValueError:
            return "File tools error: restore file expects a trash number, for example: restore file 1"

        try:
            entry = self._file_tools().restore_file_from_trash(entry_number)
        except FileToolError as exc:
            return f"File tools error: {exc}"
        return f"Restored file {entry_number}: {entry.display_text()}"

    @staticmethod
    def _pending_file_target(folder_name: str, relative_path: str) -> str:
        return f"{folder_name}\n{relative_path}"

    @staticmethod
    def _parse_pending_file_target(target: str) -> tuple[str, str]:
        folder_name, separator, relative_path = target.partition("\n")
        if not separator or not folder_name or not relative_path:
            raise FileToolError("Invalid pending file action target.")
        return folder_name, relative_path

    def _shell_command_response(self, name: str) -> AssistantResponse:
        try:
            command = get_shell_command(name, self.shell_commands_path)
        except ShellToolError as exc:
            return AssistantResponse(f"Shell command error: {exc}")

        action = PendingAction(
            kind="shell_command",
            target=command.name,
            description=f"Run safe shell command '{command.name}': {command.display()}",
        )
        return AssistantResponse(
            f"Please confirm: {action.description}. Type 'yes' to continue.",
            pending_action=action,
        )

    def _tasks_text(self) -> str:
        try:
            return self.tasks_store.summary()
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _completed_tasks_text(self) -> str:
        try:
            return self.tasks_store.completed_summary()
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _all_tasks_text(self) -> str:
        try:
            return self.tasks_store.all_summary()
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _due_today_text(self) -> str:
        try:
            return self.tasks_store.due_summary("Due today", self.tasks_store.due_today())
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _overdue_tasks_text(self) -> str:
        try:
            return self.tasks_store.due_summary("Overdue", self.tasks_store.overdue())
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _upcoming_tasks_text(self) -> str:
        try:
            return self.tasks_store.due_summary("Upcoming", self.tasks_store.upcoming())
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _due_soon_tasks_text(self) -> str:
        try:
            return self.tasks_store.due_summary("Due soon", self.tasks_store.due_soon())
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _task_stats_text(self) -> str:
        try:
            return self.tasks_store.stats_summary()
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _task_trash_text(self) -> str:
        try:
            return self.tasks_store.deleted_summary()
        except TasksError as exc:
            return f"Tasks error: {exc}"

    def _add_task_text(self, text: str) -> str:
        try:
            task = self.tasks_store.add(text)
        except TasksError as exc:
            return f"Tasks error: {exc}"
        return f"Added task: {task.text}"

    def _complete_task_text(self, task_number_text: str) -> str:
        try:
            task_number = int(task_number_text.strip())
        except ValueError:
            return "Tasks error: done expects a task number, for example: done 1"

        try:
            task = self.tasks_store.complete(task_number)
        except TasksError as exc:
            return f"Tasks error: {exc}"
        return f"Completed task: {task.text}"

    def _delete_task_response(self, task_number_text: str) -> AssistantResponse:
        try:
            task_number = int(task_number_text.strip())
        except ValueError:
            return AssistantResponse(
                "Tasks error: delete task expects a task number, for example: delete task 1"
            )

        try:
            open_tasks = self.tasks_store.open_tasks()
            task = open_tasks[task_number - 1]
        except IndexError:
            open_count = len(self.tasks_store.open_tasks())
            return AssistantResponse(
                f"Tasks error: Open task number must be between 1 and {open_count}."
            )
        except TasksError as exc:
            return AssistantResponse(f"Tasks error: {exc}")

        action = PendingAction(
            kind="task_delete",
            target=str(task_number),
            description=f"Delete task {task_number}: {task.display_text()}",
        )
        return AssistantResponse(
            f"Please confirm: {action.description}. Type 'yes' to continue.",
            pending_action=action,
        )

    def _restore_task_text(self, task_number_text: str) -> str:
        try:
            task_number = int(task_number_text.strip())
        except ValueError:
            return "Tasks error: restore task expects a completed task number, for example: restore task 1"

        try:
            task = self.tasks_store.restore_completed(task_number)
        except TasksError as exc:
            return f"Tasks error: {exc}"
        return f"Restored task {task_number}: {task.display_text()}"

    def _restore_deleted_task_text(self, task_number_text: str) -> str:
        try:
            task_number = int(task_number_text.strip())
        except ValueError:
            return "Tasks error: restore deleted task expects a deleted task number, for example: restore deleted task 1"

        try:
            task = self.tasks_store.restore_deleted(task_number)
        except TasksError as exc:
            return f"Tasks error: {exc}"
        return f"Restored deleted task {task_number}: {task.display_text()}"

    def _rename_task_text(self, text: str) -> str:
        task_number_text, separator, new_text = text.partition(" to ")
        if not separator:
            return "Tasks error: rename task expects: rename task 1 to new text"

        try:
            task_number = int(task_number_text.strip())
        except ValueError:
            return "Tasks error: rename task expects a task number, for example: rename task 1 to call dentist"

        try:
            task = self.tasks_store.rename(task_number, new_text)
        except TasksError as exc:
            return f"Tasks error: {exc}"
        return f"Renamed task {task_number}: {task.display_text()}"

    def _set_task_due_date_text(self, text: str) -> str:
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            return "Tasks error: due expects: due 1 YYYY-MM-DD"

        try:
            task_number = int(parts[0])
        except ValueError:
            return "Tasks error: due expects a task number, for example: due 1 2026-07-05"

        try:
            task = self.tasks_store.set_due_date(task_number, parts[1])
        except TasksError as exc:
            return f"Tasks error: {exc}"
        return f"Updated due date for task {task_number}: {task.display_text()}"

    def _clear_task_due_date_text(self, task_number_text: str) -> str:
        try:
            task_number = int(task_number_text.strip())
        except ValueError:
            return "Tasks error: clear due expects a task number, for example: clear due 1"

        try:
            task = self.tasks_store.set_due_date(task_number, None)
        except TasksError as exc:
            return f"Tasks error: {exc}"
        return f"Cleared due date for task {task_number}: {task.text}"

    def _history_text(self) -> str:
        try:
            return self.history_store.summary(limit=10)
        except HistoryError as exc:
            return f"History error: {exc}"

    def _clear_history(self) -> str:
        try:
            count = self.history_store.clear()
        except HistoryError as exc:
            return f"History error: {exc}"
        return f"Cleared {count} saved history entries."

    def _action_audit_text(self) -> str:
        try:
            return self.action_audit_store.summary(limit=10)
        except AuditError as exc:
            return f"Action audit error: {exc}"

    def _voice_action_audit_text(self, command_text: str = "voice audit") -> str:
        try:
            keep_latest = _parse_voice_audit_retention_keep(command_text)
            if keep_latest is not None:
                return self.voice_action_audit_store.retention_preview(keep_latest).summary()
            event, confidence_level = _parse_voice_audit_filters(command_text)
            return self.voice_action_audit_store.summary(
                limit=10,
                event=event,
                confidence_level=confidence_level,
            )
        except VoiceAuditError as exc:
            return f"Voice action audit error: {exc}"

    def _voice_audit_retention_response(self, command_text: str) -> AssistantResponse:
        try:
            keep_latest = _parse_voice_audit_retention_keep(command_text)
            if keep_latest is None:
                return AssistantResponse(
                    "Use: prune voice audit keep <number>. "
                    "Example: prune voice audit keep 100."
                )
            preview = self.voice_action_audit_store.retention_preview(keep_latest)
        except VoiceAuditError as exc:
            return AssistantResponse(f"Voice action audit error: {exc}")

        action = PendingAction(
            kind="voice_audit_prune",
            target=str(keep_latest),
            description=f"Prune voice action audit to latest {keep_latest} entries",
        )
        return AssistantResponse(
            f"{preview.summary()}\nPlease confirm: {action.description}. Type 'yes' to continue.",
            pending_action=action,
        )

    def _export_voice_action_audit_text(self, command_text: str) -> str:
        try:
            event, confidence_level = _parse_voice_audit_filters(
                command_text.removeprefix("export ").strip()
            )
            export_dir = self.voice_action_audit_store.export(
                output_dir=self.data_export_dir / "voice-audit-exports",
                event=event,
                confidence_level=confidence_level,
            )
            filter_text = _voice_audit_filter_text(event, confidence_level)
            return (
                "Voice action audit export created\n"
                "No audio was exported. No commands were run.\n"
                f"Filters: {filter_text}\n"
                f"Export folder: {export_dir}\n"
                "Manifest: voice_action_audit.json"
            )
        except VoiceAuditError as exc:
            return f"Voice action audit error: {exc}"

    def _llm_memory_context(self) -> str | None:
        try:
            memories = self.memory_store.list_memories()
        except MemoryError:
            return None
        if not memories:
            return None
        return "\n".join(f"- {item.text}" for item in memories)

    def _respond_with_llm(self, user_text: str) -> AssistantResponse:
        client = self.llm_client or OllamaClient()

        try:
            answer = client.generate(user_text, memory_context=self._llm_memory_context())
        except RuntimeError as exc:
            return AssistantResponse(
                f"{exc} Type 'help' for built-in commands, or use --no-llm."
            )

        return AssistantResponse(answer)

    def _looks_like_search_query(self, normalized: str) -> bool:
        """Check if the normalized query looks like a natural language search for files/folders/apps."""
        # Exclude structured commands with colons, slashes, special chars
        if ":" in normalized or "//" in normalized or " and " in normalized:
            return False
        
        # Exclude very short queries (likely not file/folder searches)
        if len(normalized) < 3:
            return False
        
        # Exclude queries with numbers followed by colons (likely commands like "python 3:")
        if any(char.isdigit() for char in normalized[:5]) and ":" in normalized:
            return False
        
        # Exclude queries with multiple spaces followed by colons
        if normalized.count(" ") > 2 and ":" in normalized:
            return False
        
        return True

    def _init_system_indexing(self) -> bool:
        """Initialize system indexing if not already done. Returns True if successful and enabled."""
        try:
            from assistant.settings import load_settings
            settings = load_settings(self.settings_path)
        except Exception:
            return False

        if not settings.system_indexing_enabled:
            return False

        if self.system_index is not None:
            return True  # Already initialized

        try:
            self.index_store = IndexStore(Path(settings.system_index_path))
            self.system_index = self.index_store.load_index()
            self.preferences_store = PreferencesStore(Path(settings.system_index_preferences_path))
            self.system_search = SystemSearch(self.system_index)
            return True
        except Exception:
            return False

    def _search_and_open_system_item(self, query: str) -> tuple[str, PendingAction | None]:
        """Search index for item matching query. Returns (text_response, pending_action)."""
        if not self._init_system_indexing():
            return unknown_command_text(query), None

        if self.system_search is None:
            return unknown_command_text(query), None

        try:
            matches = self.system_search.search(query.strip(), limit=5)
        except Exception:
            return unknown_command_text(query), None

        if not matches:
            return f"No items found matching '{query}'. Try being more specific.", None

        # Single match: offer to open with pending action
        if len(matches) == 1:
            match = matches[0]
            confidence = f"{match.score:.0%}"
            
            # Store for potential execution
            self.pending_search_item = match.item
            self.pending_search_query = query
            
            # Create pending action for unrestricted launch
            action = PendingAction(
                kind="unrestricted",
                target=str(match.item.full_path),
                description=f"Open: {match.item.name}",
            )
            
            return (
                f"Found '{match.item.name}' ({confidence} match). "
                f"Would you like me to open it? (Reply 'yes')",
                action,
            )

        # Multiple matches: present options (no pending action yet)
        options_text = "\n".join(
            f"  {i+1}. {match.item.name} ({match.item.item_type}) - {match.score:.0%} match"
            for i, match in enumerate(matches)
        )
        return (
            f"I found {len(matches)} matching items:\n{options_text}\n"
            "Which one would you like to open? (Reply with the number)",
            None,
        )


def _parse_voice_audit_filters(command_text: str) -> tuple[str | None, str | None]:
    normalized = " ".join(command_text.strip().lower().split())
    if normalized in {"voice audit", "voice action audit", "voice actions audit"}:
        return None, None
    prefix = "voice audit "
    if not normalized.startswith(prefix):
        return None, None

    tail = normalized[len(prefix) :].strip()
    if tail.startswith("confidence "):
        return None, tail[len("confidence ") :].strip() or None
    if tail.startswith("event "):
        return tail[len("event ") :].strip() or None, None
    if tail in {"high", "medium", "low", "unavailable", "unknown"}:
        return None, tail
    return tail, None


def _parse_positive_int(text: str, command_name: str) -> int:
    clean = text.strip()
    if not clean.isdecimal():
        raise LaunchRequestError(f"{command_name} expects a positive request number.")
    value = int(clean)
    if value < 1:
        raise LaunchRequestError(f"{command_name} expects a positive request number.")
    return value


def _parse_drift_threshold(text: str) -> int:
    clean = text.strip()
    if not clean.isdecimal() or not (1 <= int(clean) <= 3):
        raise LaunchRequestError(
            "script drift snapshot threshold expects a whole number from 1 to 3 "
            "(the number of active warning types: signature, hash, path)."
        )
    return int(clean)


def _parse_voice_audit_retention_keep(command_text: str) -> int | None:
    normalized = " ".join(command_text.strip().lower().split())
    prefixes = (
        "voice audit retention",
        "voice action audit retention",
        "prune voice audit",
        "trim voice audit",
    )
    for prefix in prefixes:
        if normalized == prefix:
            return 100
        if normalized.startswith(f"{prefix} "):
            tail = normalized[len(prefix) :].strip()
            if tail.startswith("keep "):
                tail = tail[len("keep ") :].strip()
            if not tail.isdecimal():
                raise VoiceAuditError("Use a positive number, for example: keep 100.")
            keep_latest = int(tail)
            if keep_latest < 1:
                raise VoiceAuditError("Retention keep count must be at least 1.")
            return keep_latest
    return None


def _voice_audit_filter_text(event: str | None, confidence_level: str | None) -> str:
    parts = []
    if event:
        parts.append(f"event={event}")
    if confidence_level:
        parts.append(f"confidence={confidence_level}")
    return ", ".join(parts) if parts else "all entries"


def _file_extension_for_launch(path: Path) -> str:
    if not path.suffix:
        raise FileTypeAllowlistError(
            "File launch requires a file extension so it can be checked against the file-type allowlist."
        )
    return normalize_file_extension(path.suffix)


def _parse_semicolon_list(text: str) -> list[str]:
    values = [" ".join(part.strip().split()) for part in text.split(";")]
    cleaned = [value for value in values if value]
    if not cleaned:
        raise FileTypeAllowlistError("At least one trust value is required.")
    return cleaned
