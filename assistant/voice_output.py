"""Offline text-to-speech using Windows built-in speech."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass


class VoiceOutputError(RuntimeError):
    """Raised when local text-to-speech cannot speak."""


@dataclass(frozen=True)
class VoiceOutputConfig:
    rate: int = 0
    volume: int = 100


def speak(text: str, config: VoiceOutputConfig | None = None) -> None:
    """Speak text aloud using Windows System.Speech.

    Text is passed as a PowerShell argument rather than interpolated into the
    script, so user-provided assistant text is not executed as code.
    """
    if not text.strip():
        return

    if platform.system() != "Windows":
        raise VoiceOutputError("Voice output currently supports Windows only.")

    config = config or VoiceOutputConfig()
    script = (
        "& { "
        "param($Text, $Rate, $Volume) "
        "Add-Type -AssemblyName System.Speech; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$speaker.Rate = [int]$Rate; "
        "$speaker.Volume = [int]$Volume; "
        "$speaker.Speak($Text); "
        "}"
    )

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
                text,
                str(config.rate),
                str(config.volume),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise VoiceOutputError("Voice output timed out.") from exc
    except OSError as exc:
        raise VoiceOutputError(f"Voice output failed to start: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise VoiceOutputError(f"Voice output failed: {detail}")

