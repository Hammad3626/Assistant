"""Speak one phrase using local Windows text-to-speech."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.voice_output import VoiceOutputConfig, VoiceOutputError, speak


def main() -> int:
    parser = argparse.ArgumentParser(description="Speak one phrase locally.")
    parser.add_argument("text", nargs="?", default="Hello. Voice output is working.")
    parser.add_argument("--rate", type=int, default=0)
    parser.add_argument("--volume", type=int, default=100)
    args = parser.parse_args()

    print(f"Speaking: {args.text}")
    try:
        speak(args.text, VoiceOutputConfig(rate=args.rate, volume=args.volume))
    except VoiceOutputError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("OK: Voice output completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

