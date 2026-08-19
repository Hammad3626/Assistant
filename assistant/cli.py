"""Command-line interface for the local assistant."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path

from assistant.actions import ActionError, PendingAction, parse_action
from assistant.audit import ActionAuditStore
from assistant.aliases import AliasError, resolve_alias
from assistant.autostart_manager import AutoStartManager
from assistant.core import LocalAssistant
from assistant.history import HistoryStore
from assistant.intent_parser import normalize_intent
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.ollama_client import OllamaClient
from assistant.outbox import OutboxStore
from assistant.persona import PersonaError, build_system_prompt, load_persona
from assistant.settings import SettingsError, load_settings
from assistant.startup_briefing import StartupBriefing, StartupBriefingConfig
from assistant.tasks import TasksStore
from assistant.voice_output import VoiceOutputConfig, VoiceOutputError, speak
from assistant.voice_audit import VoiceActionAuditStore
from assistant.voice_input import (
    DEFAULT_WAKE_PHRASE,
    VoiceInputConfig,
    VoiceInputResult,
    VoiceInputError,
    extract_wake_command,
    format_voice_confidence,
    listen_once_with_confidence,
    normalize_spoken_command,
    resolve_model_path,
    wake_status_text,
)


CONFIRMATION_WORDS = {"yes", "y", "confirm", "ok", "okay"}
SECOND_VOICE_CONFIRMATION_PHRASE = "confirm action"
LOW_CONFIDENCE_ACTION_LEVELS = {"low", "unavailable"}
VOICE_CORRECTION_PREFIXES = (
    "correct",
    "correction",
    "change to",
    "change it to",
    "change that to",
    "no change to",
    "actually",
    "instead",
    "no",
    "cancel and",
    "cancel that and",
    "replace with",
    "replace it with",
    "i meant",
    "i said",
    "make that",
)


@dataclass(frozen=True)
class VoiceCommandRead:
    text: str
    confidence_level: str
    raw_result: VoiceInputResult


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_voice_debug(
    enabled: bool,
    path: Path,
    stage: str,
    **details: object,
) -> None:
    if not enabled:
        return
    payload = {
        "created_at": _utc_now_iso(),
        "stage": stage,
        "details": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _print_voice_debug(stage: str, **details: object) -> None:
    parts = [f"{key}={value}" for key, value in details.items()]
    print(f"VoiceDebug> {stage}: " + ", ".join(parts))


def maybe_speak(text: str, enabled: bool, rate: int, volume: int) -> bool:
    if not enabled:
        return True
    try:
        speak(text, VoiceOutputConfig(rate=rate, volume=volume))
    except VoiceOutputError as exc:
        print(f"Assistant> Voice output error: {exc}")
        return False
    return True


def is_confirmation(text: str) -> bool:
    """Return whether text is a simple confirmation."""
    return text.strip().lower() in CONFIRMATION_WORDS


def is_second_voice_confirmation(text: str) -> bool:
    """Return whether text is the extra phrase for low-confidence voice actions."""
    return normalize_voice_correction_phrase(text).lower() == SECOND_VOICE_CONFIRMATION_PHRASE


def requires_second_voice_confirmation(confidence_level: str | None) -> bool:
    """Return whether a voice action should require a second confirmation phrase."""
    return confidence_level in LOW_CONFIDENCE_ACTION_LEVELS


def normalize_voice_correction_phrase(text: str) -> str:
    """Normalize common speech punctuation so correction phrases match reliably."""
    cleaned = text.strip()
    for character in ",.;:!?":
        cleaned = cleaned.replace(character, " ")
    return " ".join(cleaned.split())


def extract_voice_correction(text: str) -> str | None:
    """Return a corrected command from a spoken correction phrase."""
    normalized = normalize_voice_correction_phrase(text)
    lowered = normalized.lower()
    for prefix in VOICE_CORRECTION_PREFIXES:
        if lowered == prefix:
            return None
        if lowered.startswith(f"{prefix} "):
            corrected = normalized[len(prefix) :].strip()
            return corrected or None
    return None


def voice_action_preview_text(user_text: str, action: PendingAction) -> str:
    """Return a voice-specific preview before a pending action can run."""
    return "\n".join(
        [
            f"Voice command preview: I heard '{user_text}'.",
            f"Pending action: {action.description}.",
            "Say 'yes' to continue, 'no' to cancel, or a correction like 'actually <command>'.",
        ]
    )


def low_confidence_voice_confirmation_text(confidence_level: str | None) -> str:
    """Return the extra confirmation prompt for low-confidence spoken actions."""
    level = confidence_level or "unknown"
    return (
        f"Voice confidence was {level}. For safety, say "
        f"'{SECOND_VOICE_CONFIRMATION_PHRASE}' to run this action, or say 'no' to cancel."
    )


def read_voice_command_result(
    voice_config: VoiceInputConfig,
    wake_enabled: bool,
    wake_phrase: str,
    voice_debug_enabled: bool,
    voice_debug_path: Path,
) -> VoiceCommandRead | None:
    """Listen once and return a command, or None when wake mode ignores speech."""
    print("Listening...")
    voice_result = listen_once_with_confidence(voice_config)
    user_text = voice_result.text
    _print_voice_debug(
        "audio_capture",
        sample_rate=voice_result.sample_rate,
        input_device=voice_result.input_device,
        capture_seconds=round(voice_result.capture_seconds, 2),
        speech_seconds=round(voice_result.speech_seconds, 2),
        chunk_count=voice_result.chunk_count,
        status_count=len(voice_result.audio_statuses),
    )
    _write_voice_debug(
        voice_debug_enabled,
        voice_debug_path,
        "audio_capture",
        sample_rate=voice_result.sample_rate,
        input_device=voice_result.input_device,
        capture_seconds=voice_result.capture_seconds,
        speech_seconds=voice_result.speech_seconds,
        chunk_count=voice_result.chunk_count,
        audio_statuses=list(voice_result.audio_statuses),
    )
    if wake_enabled:
        woke, command = extract_wake_command(user_text, wake_phrase)
        if not woke:
            print(f"Heard without wake phrase: {user_text}")
            print(format_voice_confidence(voice_result.confidence))
            _write_voice_debug(
                voice_debug_enabled,
                voice_debug_path,
                "wake_ignored",
                transcribed_text=user_text,
                confidence_level=voice_result.confidence.level,
            )
            return None
        if command:
            user_text = command
            print(f"Wake phrase heard. Command: {user_text}")
        else:
            print("Wake phrase heard. Listening for command...")
            voice_result = listen_once_with_confidence(voice_config)
            user_text = voice_result.text
            _print_voice_debug(
                "audio_capture",
                sample_rate=voice_result.sample_rate,
                input_device=voice_result.input_device,
                capture_seconds=round(voice_result.capture_seconds, 2),
                speech_seconds=round(voice_result.speech_seconds, 2),
                chunk_count=voice_result.chunk_count,
                status_count=len(voice_result.audio_statuses),
            )
            _write_voice_debug(
                voice_debug_enabled,
                voice_debug_path,
                "audio_capture",
                sample_rate=voice_result.sample_rate,
                input_device=voice_result.input_device,
                capture_seconds=voice_result.capture_seconds,
                speech_seconds=voice_result.speech_seconds,
                chunk_count=voice_result.chunk_count,
                audio_statuses=list(voice_result.audio_statuses),
                wake_follow_up=True,
            )

    normalized_text = normalize_spoken_command(user_text)
    if normalized_text != user_text:
        print(f"You> {user_text} -> {normalized_text}")
    else:
        print(f"You> {user_text}")
    print(format_voice_confidence(voice_result.confidence))
    _write_voice_debug(
        voice_debug_enabled,
        voice_debug_path,
        "transcription",
        transcribed_text=user_text,
        normalized_command=normalized_text,
        confidence_level=voice_result.confidence.level,
    )
    return VoiceCommandRead(
        text=normalized_text,
        confidence_level=voice_result.confidence.level,
        raw_result=voice_result,
    )


def read_voice_command(
    voice_config: VoiceInputConfig,
    wake_enabled: bool,
    wake_phrase: str,
) -> str | None:
    """Listen once and return recognized command text for compatibility."""
    result = read_voice_command_result(
        voice_config,
        wake_enabled,
        wake_phrase,
        voice_debug_enabled=False,
        voice_debug_path=Path("data/voice_debug.jsonl"),
    )
    return None if result is None else result.text


def should_continue_wake_loop_after_voice_error(error: VoiceInputError) -> bool:
    """Return True for expected silence timeouts in optional wake mode."""
    return "No speech recognized" in str(error)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local PC assistant.")
    parser.add_argument("--settings-path", default="config/settings.json")
    parser.add_argument("--model", default=None)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--num-gpu", type=int, default=None)
    parser.add_argument("--voice", action="store_true")
    parser.add_argument("--wake", action="store_true")
    parser.add_argument("--wake-phrase", default=DEFAULT_WAKE_PHRASE)
    parser.add_argument("--voice-model-path", default=None)
    parser.add_argument("--voice-device", type=int, default=None)
    parser.add_argument("--voice-sample-rate", type=int, default=None)
    parser.add_argument("--voice-timeout", type=int, default=None)
    parser.add_argument("--voice-debug", action="store_true")
    parser.add_argument("--speak", action="store_true")
    parser.add_argument("--speech-rate", type=int, default=None)
    parser.add_argument("--speech-volume", type=int, default=None)
    parser.add_argument("--startup-briefing", action="store_true", help="Enable startup briefing on first run of the day")
    parser.add_argument("--check-autostart", action="store_true", help="Check and report auto-start status")
    parser.add_argument("--enable-autostart", action="store_true", help="Enable auto-start (CLI mode)")
    parser.add_argument("--disable-autostart", action="store_true", help="Disable auto-start")
    args = parser.parse_args()

    try:
        settings = load_settings(args.settings_path)
        system_prompt = build_system_prompt(load_persona(settings.persona_path))
    except SettingsError as exc:
        print(f"Settings error: {exc}")
        return 1
    except PersonaError as exc:
        print(f"Persona error: {exc}")
        return 1

    model = args.model if args.model is not None else settings.model
    use_llm = settings.use_llm and not args.no_llm
    num_gpu = args.num_gpu if args.num_gpu is not None else settings.num_gpu
    voice_enabled = settings.voice_enabled or args.voice
    wake_enabled = args.wake
    if wake_enabled:
        voice_enabled = True
    voice_model_path = args.voice_model_path or settings.voice_model_path
    voice_device = args.voice_device if args.voice_device is not None else settings.voice_input_device
    voice_sample_rate = (
        args.voice_sample_rate if args.voice_sample_rate is not None else settings.voice_sample_rate
    )
    voice_timeout = args.voice_timeout if args.voice_timeout is not None else settings.voice_timeout
    voice_debug_enabled = settings.voice_debug_enabled or args.voice_debug
    voice_debug_path = Path(settings.voice_debug_path)
    speak_enabled = settings.speak_enabled or args.speak
    speech_rate = args.speech_rate if args.speech_rate is not None else settings.speech_rate
    speech_volume = args.speech_volume if args.speech_volume is not None else settings.speech_volume

    llm_client = (
        None
        if not use_llm
        else OllamaClient(model=model, num_gpu=num_gpu, system_prompt=system_prompt)
    )
    assistant = LocalAssistant(
        name=settings.assistant_name,
        llm_client=llm_client,
        use_llm=use_llm,
        memory_store=MemoryStore(settings.memory_path),
        notes_store=NotesStore(settings.notes_path),
        tasks_store=TasksStore(settings.tasks_path),
        outbox_store=OutboxStore(settings.outbox_path),
        history_store=HistoryStore(settings.history_path, enabled=settings.history_enabled),
        action_audit_store=ActionAuditStore(
            settings.action_audit_path,
            enabled=settings.action_audit_enabled,
        ),
        voice_action_audit_store=VoiceActionAuditStore(
            settings.voice_action_audit_path,
            enabled=settings.voice_action_audit_enabled,
        ),
        aliases_path=settings.aliases_path,
        voice_model_path=voice_model_path,
        settings_path=args.settings_path,
        persona_path=settings.persona_path,
    )

    print("Local PC Assistant")
    print(f"Settings: {args.settings_path}")
    print("Type 'help' for commands or 'exit' to quit.")
    if not use_llm:
        print("LLM: disabled")
    else:
        print(f"LLM: local Ollama model '{model}'")
        print(f"GPU offload layers: {num_gpu}")
    if voice_enabled:
        print("Voice input: enabled")
        device_text = "default" if voice_device < 0 else str(voice_device)
        print(f"Voice input device: {device_text}")
        print(f"Voice sample rate: {voice_sample_rate}")
    if wake_enabled:
        print(f"Wake voice loop: enabled, phrase '{args.wake_phrase}'")
    if voice_debug_enabled:
        print(f"Voice debug log: {voice_debug_path}")
    if speak_enabled:
        print("Voice output: enabled")
    if wake_enabled:
        print("Wake mode ignores speech until the wake phrase is heard. Press Ctrl+C to stop.")

    # Handle auto-start management commands
    if args.check_autostart:
        AutoStartManager.print_status()
        return 0
    
    if args.enable_autostart:
        result = AutoStartManager.enable_autostart(cli=True, project_root=None)
        if result["success"]:
            print(f"✓ Auto-start enabled for: {', '.join(result['enabled_modes'])}")
            AutoStartManager.print_status()
        else:
            print(f"✗ Failed to enable auto-start: {'; '.join(result['errors'])}")
        return 0
    
    if args.disable_autostart:
        result = AutoStartManager.disable_autostart(all_modes=True)
        if result["success"]:
            print(f"✓ Auto-start disabled for: {', '.join(result['disabled_modes'])}")
            AutoStartManager.print_status()
        else:
            print(f"✗ Failed to disable auto-start: {'; '.join(result['errors'])}")
        return 0

    # Deliver startup briefing if enabled and first run of the day
    if args.startup_briefing or settings.startup_briefing_enabled:
        startup_record = Path.home() / ".jarvis" / "startup_record.json"
        
        if StartupBriefing.is_first_startup_today(startup_record):
            briefing = StartupBriefing(enable_voice=speak_enabled)
            tasks_file = Path(settings.tasks_path) if settings.tasks_path else None
            
            result = briefing.deliver_briefing(
                include_greeting=True,
                include_time=True,
                include_tasks=True,
                include_status=True,
                tasks_path=tasks_file,
                ollama_available=use_llm,
            )
            
            if result["success"]:
                if speak_enabled:
                    print(f"Assistant> {result['text']}")
                else:
                    print(f"\n{result['text']}\n")
            elif result["error"]:
                print(f"Briefing error: {result['error']}")
            
            # Record this startup
            StartupBriefing.record_startup(startup_record)

    pending_action: PendingAction | None = None
    pending_action_needs_second_voice_confirmation = False
    pending_action_second_confirmation_armed = False
    pending_action_voice_confidence_level: str | None = None
    last_voice_confidence_level: str | None = None
    pending_low_confidence_command: VoiceCommandRead | None = None

    while True:
        if voice_enabled:
            voice_config = VoiceInputConfig(
                model_path=resolve_model_path(voice_model_path),
                sample_rate=voice_sample_rate,
                timeout_seconds=voice_timeout,
                input_device=None if voice_device < 0 else voice_device,
            )
            try:
                voice_command = read_voice_command_result(
                    voice_config,
                    wake_enabled,
                    args.wake_phrase,
                    voice_debug_enabled=voice_debug_enabled,
                    voice_debug_path=voice_debug_path,
                )
                if voice_command is None:
                    continue
                user_text = voice_command.text
                last_voice_confidence_level = voice_command.confidence_level
                assistant.voice_action_audit_store.record(
                    event="recognized",
                    command_text=user_text,
                    confidence_level=last_voice_confidence_level,
                )
                _write_voice_debug(
                    voice_debug_enabled,
                    voice_debug_path,
                    "recognized",
                    normalized_command=user_text,
                    confidence_level=last_voice_confidence_level,
                )
            except VoiceInputError as exc:
                if wake_enabled and should_continue_wake_loop_after_voice_error(exc):
                    print("No wake phrase heard before timeout. Listening again...")
                    continue
                print(f"Assistant> Voice input error: {exc}")
                return 1
            except KeyboardInterrupt:
                print("\nAssistant> Goodbye.")
                return 0
        else:
            try:
                user_text = input("You> ")
            except (EOFError, KeyboardInterrupt):
                print("\nAssistant> Goodbye.")
                return 0
            last_voice_confidence_level = None

        if voice_enabled and pending_action is None:
            if pending_low_confidence_command is not None:
                corrected = extract_voice_correction(user_text)
                if is_confirmation(user_text):
                    user_text = pending_low_confidence_command.text
                    last_voice_confidence_level = pending_low_confidence_command.confidence_level
                    pending_low_confidence_command = None
                    _write_voice_debug(
                        voice_debug_enabled,
                        voice_debug_path,
                        "low_confidence_confirmed",
                        normalized_command=user_text,
                        confidence_level=last_voice_confidence_level,
                    )
                elif corrected:
                    user_text = normalize_spoken_command(corrected)
                    pending_low_confidence_command = None
                    _write_voice_debug(
                        voice_debug_enabled,
                        voice_debug_path,
                        "low_confidence_corrected",
                        normalized_command=user_text,
                    )
                else:
                    response_text = "Cancelled low-confidence command. Please repeat more clearly."
                    pending_low_confidence_command = None
                    print(f"Assistant> {response_text}")
                    assistant.record_turn(user_text, response_text)
                    _write_voice_debug(
                        voice_debug_enabled,
                        voice_debug_path,
                        "low_confidence_cancelled",
                        reply_text=user_text,
                    )
                    if not maybe_speak(response_text, speak_enabled, speech_rate, speech_volume):
                        return 1
                    continue
            elif requires_second_voice_confirmation(last_voice_confidence_level):
                pending_low_confidence_command = VoiceCommandRead(
                    text=user_text,
                    confidence_level=last_voice_confidence_level or "unavailable",
                    raw_result=voice_command.raw_result,
                )
                response_text = (
                    f"I heard '{user_text}' with {last_voice_confidence_level} confidence. "
                    "Say 'yes' to use it, 'no' to cancel, or say a correction like 'correct <command>'."
                )
                print(f"Assistant> {response_text}")
                assistant.record_turn(user_text, response_text)
                _write_voice_debug(
                    voice_debug_enabled,
                    voice_debug_path,
                    "low_confidence_prompt",
                    normalized_command=user_text,
                    confidence_level=last_voice_confidence_level,
                )
                if not maybe_speak(response_text, speak_enabled, speech_rate, speech_volume):
                    return 1
                continue

        corrected_user_text: str | None = None
        if pending_action:
            action = pending_action
            if voice_enabled:
                corrected_user_text = extract_voice_correction(user_text)

            if corrected_user_text:
                response_text = "Cancelled pending action so I can use the corrected voice command."
                assistant.action_audit_store.record(
                    action,
                    status="cancelled",
                    requested_by=user_text,
                    result=response_text,
                )
                assistant.voice_action_audit_store.record(
                    event="corrected",
                    command_text=user_text,
                    confidence_level=last_voice_confidence_level,
                    action_description=action.description,
                    result=response_text,
                )
                pending_action = None
                pending_action_needs_second_voice_confirmation = False
                pending_action_second_confirmation_armed = False
                pending_action_voice_confidence_level = None
                print(f"Assistant> {response_text}")
                assistant.record_turn(user_text, response_text)
                user_text = corrected_user_text
            elif (
                voice_enabled
                and pending_action_needs_second_voice_confirmation
                and is_second_voice_confirmation(user_text)
                and pending_action_second_confirmation_armed
            ):
                try:
                    response_text = assistant.confirm_pending_action(action)
                    assistant.action_audit_store.record(
                        action,
                        status="confirmed",
                        requested_by=user_text,
                        result=response_text,
                    )
                    assistant.voice_action_audit_store.record(
                        event="confirmed",
                        command_text=user_text,
                        confidence_level=last_voice_confidence_level,
                        action_description=action.description,
                        result=response_text,
                    )
                except ActionError as exc:
                    response_text = f"Action failed: {exc}"
                    assistant.action_audit_store.record(
                        action,
                        status="failed",
                        requested_by=user_text,
                        result=response_text,
                    )
                    assistant.voice_action_audit_store.record(
                        event="failed",
                        command_text=user_text,
                        confidence_level=last_voice_confidence_level,
                        action_description=action.description,
                        result=response_text,
                    )
                pending_action = None
                pending_action_needs_second_voice_confirmation = False
                pending_action_second_confirmation_armed = False
                pending_action_voice_confidence_level = None
            elif (
                voice_enabled
                and pending_action_needs_second_voice_confirmation
                and is_second_voice_confirmation(user_text)
            ):
                response_text = (
                    "Please say 'yes' first after reviewing the preview. "
                    f"Then say '{SECOND_VOICE_CONFIRMATION_PHRASE}' to run the action."
                )
                assistant.voice_action_audit_store.record(
                    event="second_confirmation_out_of_order",
                    command_text=user_text,
                    confidence_level=last_voice_confidence_level,
                    action_description=action.description,
                    result=response_text,
                )
            elif is_confirmation(user_text):
                if voice_enabled and pending_action_needs_second_voice_confirmation:
                    pending_action_second_confirmation_armed = True
                    response_text = low_confidence_voice_confirmation_text(
                        pending_action_voice_confidence_level
                    )
                    assistant.voice_action_audit_store.record(
                        event="second_confirmation_requested",
                        command_text=user_text,
                        confidence_level=last_voice_confidence_level,
                        action_description=action.description,
                        result=response_text,
                    )
                else:
                    try:
                        response_text = assistant.confirm_pending_action(action)
                        assistant.action_audit_store.record(
                            action,
                            status="confirmed",
                            requested_by=user_text,
                            result=response_text,
                        )
                        if voice_enabled:
                            assistant.voice_action_audit_store.record(
                                event="confirmed",
                                command_text=user_text,
                                confidence_level=last_voice_confidence_level,
                                action_description=action.description,
                                result=response_text,
                            )
                    except ActionError as exc:
                        response_text = f"Action failed: {exc}"
                        assistant.action_audit_store.record(
                            action,
                            status="failed",
                            requested_by=user_text,
                            result=response_text,
                        )
                        if voice_enabled:
                            assistant.voice_action_audit_store.record(
                                event="failed",
                                command_text=user_text,
                                confidence_level=last_voice_confidence_level,
                                action_description=action.description,
                                result=response_text,
                            )
                    pending_action = None
                    pending_action_needs_second_voice_confirmation = False
                    pending_action_second_confirmation_armed = False
                    pending_action_voice_confidence_level = None
            elif voice_enabled and pending_action_needs_second_voice_confirmation:
                response_text = "Cancelled."
                assistant.action_audit_store.record(
                    action,
                    status="cancelled",
                    requested_by=user_text,
                    result=response_text,
                )
                assistant.voice_action_audit_store.record(
                    event="cancelled",
                    command_text=user_text,
                    confidence_level=last_voice_confidence_level,
                    action_description=action.description,
                    result=response_text,
                )
                pending_action = None
                pending_action_needs_second_voice_confirmation = False
                pending_action_second_confirmation_armed = False
                pending_action_voice_confidence_level = None
            else:
                response_text = "Cancelled."
                assistant.action_audit_store.record(
                    action,
                    status="cancelled",
                    requested_by=user_text,
                    result=response_text,
                )
                if voice_enabled:
                    assistant.voice_action_audit_store.record(
                        event="cancelled",
                        command_text=user_text,
                        confidence_level=last_voice_confidence_level,
                        action_description=action.description,
                        result=response_text,
                    )
                pending_action = None
                pending_action_needs_second_voice_confirmation = False
                pending_action_second_confirmation_armed = False
                pending_action_voice_confidence_level = None

            print(f"Assistant> {response_text}")
            if voice_enabled:
                _write_voice_debug(
                    voice_debug_enabled,
                    voice_debug_path,
                    "action_resolution",
                    confidence_level=last_voice_confidence_level,
                    final_response=response_text,
                    execution_result=("cancelled" if response_text == "Cancelled." else "completed"),
                )
            assistant.record_turn(user_text, response_text)
            if not maybe_speak(response_text, speak_enabled, speech_rate, speech_volume):
                return 1
            if corrected_user_text is None:
                continue

        alias_text = user_text
        try:
            alias_text = resolve_alias(user_text, settings.aliases_path)
        except AliasError:
            alias_text = user_text
        intent_text = normalize_intent(alias_text)
        command_for_action = intent_text if intent_text is not None else alias_text
        try:
            selected_target = parse_action(command_for_action)
        except ActionError:
            selected_target = None
        if voice_enabled:
            _print_voice_debug(
                "routing",
                transcribed_text=user_text,
                normalized_command=command_for_action,
                detected_intent=intent_text or "",
                selected_target=selected_target.description if selected_target else "",
            )
            _write_voice_debug(
                voice_debug_enabled,
                voice_debug_path,
                "routing",
                transcribed_text=user_text,
                normalized_command=command_for_action,
                detected_intent=intent_text or "",
                selected_target=selected_target.description if selected_target else "",
            )

        response = assistant.respond(user_text)
        pending_action = response.pending_action
        pending_action_needs_second_voice_confirmation = (
            voice_enabled
            and response.pending_action is not None
            and requires_second_voice_confirmation(last_voice_confidence_level)
        )
        pending_action_second_confirmation_armed = False
        pending_action_voice_confidence_level = (
            last_voice_confidence_level if response.pending_action is not None else None
        )
        response_text = response.text
        if voice_enabled and response.pending_action is not None:
            response_text = f"{response.text}\n{voice_action_preview_text(user_text, response.pending_action)}"
            if pending_action_needs_second_voice_confirmation:
                response_text = (
                    f"{response_text}\n"
                    f"{low_confidence_voice_confirmation_text(pending_action_voice_confidence_level)}"
                )
            assistant.voice_action_audit_store.record(
                event="action_preview",
                command_text=user_text,
                confidence_level=last_voice_confidence_level,
                action_description=response.pending_action.description,
                result="Pending confirmation.",
            )
            _write_voice_debug(
                voice_debug_enabled,
                voice_debug_path,
                "action_preview",
                action_description=response.pending_action.description,
                confidence_level=last_voice_confidence_level,
                execution_result="pending_confirmation",
            )

        print(f"Assistant> {response_text}")
        if voice_enabled:
            _write_voice_debug(
                voice_debug_enabled,
                voice_debug_path,
                "assistant_response",
                final_response=response_text,
                should_exit=response.should_exit,
            )
        assistant.record_turn(user_text, response_text)
        if not maybe_speak(response_text, speak_enabled, speech_rate, speech_volume):
            return 1

        if response.should_exit:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
