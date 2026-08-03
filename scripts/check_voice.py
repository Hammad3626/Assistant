"""Check offline voice input dependencies and local model files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.voice_input import (
    VoiceInputError,
    default_input_device_text,
    list_input_devices,
    resolve_model_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check offline voice input setup.")
    parser.add_argument("--model-path", default=None)
    args = parser.parse_args()

    model_path = resolve_model_path(args.model_path)

    print("Voice input health check")
    print(f"Model path: {model_path}")

    try:
        devices = list_input_devices()
    except VoiceInputError as exc:
        print(f"ERROR: {exc}")
        print('Fix: python -m pip install -e ".[voice]"')
        return 1

    if not devices:
        print("ERROR: No microphone input devices found.")
        print("Fix: connect or enable a microphone in Windows Sound settings.")
        return 1

    print("Input devices:")
    try:
        print(f"Default input device: {default_input_device_text()}")
    except VoiceInputError as exc:
        print(f"Default input device: error: {exc}")
    for device in devices:
        print(f"- {device}")

    if not model_path.exists():
        print(f"ERROR: Vosk model folder not found: {model_path}")
        print("Fix: download and unzip vosk-model-small-en-us-0.15 into the models folder.")
        return 1

    print("OK: Voice dependencies, microphone, and model path are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
