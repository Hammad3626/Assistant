"""Offline microphone input using Vosk.

The imports for Vosk and sounddevice are intentionally lazy so the rest of the
assistant still works before voice dependencies are installed.
"""

from __future__ import annotations

import json
import math
import queue
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_VOICE_MODEL_PATH = Path("models/vosk-model-small-en-us-0.15")
DEFAULT_WAKE_PHRASE = "hey eva"

SPOKEN_COMMAND_ALIASES = {
    "as it": "exit",
    "ex it": "exit",
    "eggs it": "exit",
    "except": "exit",
    "by": "bye",
    "high": "hi",
}


class VoiceInputError(RuntimeError):
    """Raised when offline voice input cannot start or complete."""


def _pcm16le_rms(data: bytes) -> int:
    """Return RMS level for mono/single-channel 16-bit PCM bytes."""
    if not data:
        return 0

    sample_count = len(data) // 2
    if sample_count <= 0:
        return 0

    total = 0
    for index in range(0, sample_count * 2, 2):
        sample = int.from_bytes(data[index : index + 2], byteorder="little", signed=True)
        total += sample * sample
    return int(math.sqrt(total / sample_count))


@dataclass(frozen=True)
class VoiceInputConfig:
    model_path: Path = DEFAULT_VOICE_MODEL_PATH
    sample_rate: int = 16000
    timeout_seconds: int = 8
    input_device: int | None = None
    blocksize: int = 4000
    silence_timeout_ms: int = 1200
    min_speech_ms: int = 200
    speech_rms_threshold: int = 250


@dataclass(frozen=True)
class VoiceConfidenceReport:
    text: str
    word_count: int
    average_confidence: float | None
    minimum_confidence: float | None
    level: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class VoiceInputResult:
    text: str
    confidence: VoiceConfidenceReport
    capture_seconds: float
    speech_seconds: float
    chunk_count: int
    input_device: int | None
    sample_rate: int
    audio_statuses: tuple[str, ...]


def resolve_model_path(model_path: str | Path | None = None) -> Path:
    """Return the configured local Vosk model path."""
    return Path(model_path) if model_path else DEFAULT_VOICE_MODEL_PATH


def normalize_spoken_command(text: str) -> str:
    """Map common speech-recognition mistakes to known short commands."""
    normalized = " ".join(text.strip().lower().split())
    return SPOKEN_COMMAND_ALIASES.get(normalized, text.strip())


def extract_wake_command(text: str, wake_phrase: str = DEFAULT_WAKE_PHRASE) -> tuple[bool, str]:
    """Return whether text contains the wake phrase and any command after it."""
    text_words = " ".join(text.strip().lower().split()).split()
    wake_words = " ".join(wake_phrase.strip().lower().split()).split()
    if not wake_words:
        raise VoiceInputError("Wake phrase cannot be empty.")

    wake_len = len(wake_words)
    for index in range(0, len(text_words) - wake_len + 1):
        if text_words[index : index + wake_len] == wake_words:
            command = " ".join(text_words[index + wake_len :])
            return True, command.strip(" ,.!?")
    return False, ""


def wake_status_text(wake_phrase: str = DEFAULT_WAKE_PHRASE) -> str:
    """Return a read-only explanation of wake-loop behavior."""
    return (
        "Wake voice loop\n"
        f"Wake phrase: {wake_phrase}\n"
        "Launch command: python -m assistant.cli --wake --speak\n"
        "Behavior: listens repeatedly, ignores speech without the wake phrase, "
        "then runs the spoken command after the wake phrase.\n"
        "Safety: optional only, local Vosk input only, and existing confirmations still apply."
    )


def voice_confidence_status_text() -> str:
    """Return a read-only explanation of voice confidence handling."""
    return (
        "Voice confidence reporting\n"
        "Status: read-only safety signal.\n"
        "Source: local Vosk word confidence when the recognizer provides it.\n"
        "Levels: high, medium, low, or unavailable.\n"
        "Behavior: CLI voice mode prints the confidence level after a phrase is recognized.\n"
        "Low/unavailable action commands require 'yes' and then the extra phrase 'confirm action'.\n"
        "Safety: confidence never confirms actions, bypasses previews, or runs commands. "
        "Action commands still require explicit confirmation."
    )


def analyze_voice_confidence(raw_result: str | dict[str, Any]) -> VoiceConfidenceReport:
    """Build a read-only confidence report from a Vosk result."""
    if isinstance(raw_result, str):
        try:
            result = json.loads(raw_result)
        except json.JSONDecodeError:
            result = {"text": raw_result}
    else:
        result = raw_result

    text = str(result.get("text", "")).strip()
    words = result.get("result", [])
    confidences: list[float] = []
    if isinstance(words, list):
        for item in words:
            if not isinstance(item, dict):
                continue
            confidence = item.get("conf")
            if isinstance(confidence, int | float):
                confidences.append(max(0.0, min(1.0, float(confidence))))

    if not confidences:
        return VoiceConfidenceReport(
            text=text,
            word_count=len(text.split()),
            average_confidence=None,
            minimum_confidence=None,
            level="unavailable",
            notes=(
                "Vosk did not provide per-word confidence for this phrase.",
                "Review the preview carefully before confirming any action.",
            ),
        )

    average = sum(confidences) / len(confidences)
    minimum = min(confidences)
    if average >= 0.80 and minimum >= 0.60:
        level = "high"
    elif average >= 0.60 and minimum >= 0.40:
        level = "medium"
    else:
        level = "low"

    notes = ["Read-only signal; confirmations are still required."]
    if level == "low":
        notes.append("Repeat or correct the command before confirming an action.")

    return VoiceConfidenceReport(
        text=text,
        word_count=len(confidences),
        average_confidence=average,
        minimum_confidence=minimum,
        level=level,
        notes=tuple(notes),
    )


def format_voice_confidence(report: VoiceConfidenceReport) -> str:
    """Return a compact CLI confidence summary."""
    if report.average_confidence is None or report.minimum_confidence is None:
        return f"Voice confidence: {report.level} ({report.word_count} words, no word scores)"
    average = round(report.average_confidence, 2)
    minimum = round(report.minimum_confidence, 2)
    return f"Voice confidence: {report.level} (avg {average}, min {minimum}, words {report.word_count})"


def list_input_devices() -> list[str]:
    """Return available audio input devices."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoiceInputError("Missing dependency: sounddevice") from exc

    devices: list[str] = []
    for index, device in enumerate(sd.query_devices()):
        if int(device.get("max_input_channels", 0)) > 0:
            name = device.get("name", "Unknown input device")
            default_rate = int(float(device.get("default_samplerate", 0.0)))
            channels = int(device.get("max_input_channels", 0))
            devices.append(f"{index}: {name} (channels={channels}, default_rate={default_rate})")
    return devices


def default_input_device_text() -> str:
    """Return the current default input device summary."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoiceInputError("Missing dependency: sounddevice") from exc

    default_input_index, _ = sd.default.device
    if default_input_index is None or int(default_input_index) < 0:
        return "none"
    device = sd.query_devices(int(default_input_index))
    name = str(device.get("name", "Unknown input device"))
    channels = int(device.get("max_input_channels", 0))
    default_rate = int(float(device.get("default_samplerate", 0.0)))
    return f"{int(default_input_index)}: {name} (channels={channels}, default_rate={default_rate})"


def listen_once_with_confidence(config: VoiceInputConfig | None = None) -> VoiceInputResult:
    """Listen for one spoken phrase and return recognized text plus confidence."""
    config = config or VoiceInputConfig()

    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
    except ImportError as exc:
        raise VoiceInputError(
            "Voice input requires vosk and sounddevice. Install the voice dependencies first."
        ) from exc

    if not config.model_path.exists():
        raise VoiceInputError(f"Vosk model not found: {config.model_path}")

    audio_queue: queue.Queue[bytes] = queue.Queue()
    audio_statuses: list[str] = []

    def audio_callback(indata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
        if status:
            # Keep recording; status messages are often recoverable.
            if len(audio_statuses) < 8:
                audio_statuses.append(str(status))
        audio_queue.put(bytes(indata))

    recognizer = KaldiRecognizer(Model(str(config.model_path)), config.sample_rate)
    if hasattr(recognizer, "SetWords"):
        recognizer.SetWords(True)
    deadline = time.monotonic() + config.timeout_seconds
    capture_start = time.monotonic()
    silence_timeout_seconds = max(0.1, config.silence_timeout_ms / 1000.0)
    min_speech_seconds = max(0.0, config.min_speech_ms / 1000.0)
    speech_started_at: float | None = None
    last_speech_at: float | None = None
    chunk_count = 0

    def result_from_json(raw_result: dict[str, Any]) -> VoiceInputResult:
        confidence = analyze_voice_confidence(raw_result)
        speech_seconds = 0.0
        if speech_started_at is not None and last_speech_at is not None:
            speech_seconds = max(0.0, last_speech_at - speech_started_at)
        return VoiceInputResult(
            text=confidence.text,
            confidence=confidence,
            capture_seconds=max(0.0, time.monotonic() - capture_start),
            speech_seconds=speech_seconds,
            chunk_count=chunk_count,
            input_device=config.input_device,
            sample_rate=config.sample_rate,
            audio_statuses=tuple(audio_statuses),
        )

    try:
        with sd.RawInputStream(
            samplerate=config.sample_rate,
            blocksize=config.blocksize,
            dtype="int16",
            channels=1,
            device=config.input_device,
            callback=audio_callback,
        ):
            while time.monotonic() < deadline:
                try:
                    data = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                chunk_count += 1
                now = time.monotonic()

                rms = _pcm16le_rms(data)
                if rms >= config.speech_rms_threshold:
                    if speech_started_at is None:
                        speech_started_at = now
                    last_speech_at = now

                if recognizer.AcceptWaveform(data):
                    phrase_result = result_from_json(json.loads(recognizer.Result()))
                    if phrase_result.text:
                        return phrase_result

                if (
                    speech_started_at is not None
                    and last_speech_at is not None
                    and (now - last_speech_at) >= silence_timeout_seconds
                    and (last_speech_at - speech_started_at) >= min_speech_seconds
                ):
                    final_after_silence = result_from_json(json.loads(recognizer.FinalResult()))
                    if final_after_silence.text:
                        return final_after_silence
    except Exception as exc:
        raise VoiceInputError(f"Microphone input failed: {exc}") from exc

    final = result_from_json(json.loads(recognizer.FinalResult()))
    if not final.text:
        if speech_started_at is not None:
            raise VoiceInputError("Speech detected, but transcription was empty. Check microphone level and background noise.")
        raise VoiceInputError("No speech recognized before timeout.")
    return final


def listen_once(config: VoiceInputConfig | None = None) -> str:
    """Listen for one spoken phrase and return recognized text."""
    return listen_once_with_confidence(config).text
