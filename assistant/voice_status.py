"""Read-only voice setup status for the local assistant."""

from __future__ import annotations

import platform
from pathlib import Path

from assistant.voice_input import (
    VoiceInputError,
    default_input_device_text,
    list_input_devices,
    resolve_model_path,
)


def voice_status_text(model_path: str | Path | None = None) -> str:
    """Return voice readiness details without recording audio."""
    resolved_model_path = resolve_model_path(model_path)
    lines = [
        "Voice status",
        f"Input model path: {resolved_model_path}",
        f"Input model found: {'yes' if resolved_model_path.exists() else 'no'}",
    ]

    try:
        devices = list_input_devices()
    except VoiceInputError as exc:
        lines.append(f"Input devices: error: {exc}")
    else:
        try:
            lines.append(f"Default input device: {default_input_device_text()}")
        except VoiceInputError as exc:
            lines.append(f"Default input device: error: {exc}")
        lines.append(f"Input devices: {len(devices)}")
        lines.extend(f"- {device}" for device in devices[:10])
        if len(devices) > 10:
            lines.append(f"- ...and {len(devices) - 10} more")

    output_supported = platform.system() == "Windows"
    lines.append(f"Voice output supported: {'yes' if output_supported else 'no'}")
    lines.append("This command is read-only and does not listen or speak.")
    return "\n".join(lines)
