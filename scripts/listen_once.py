"""Listen once with Vosk and print the recognized text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.voice_input import (
    VoiceInputConfig,
    VoiceInputError,
    listen_once_with_confidence,
    resolve_model_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recognize one spoken phrase.")
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--device", type=int, default=-1)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--timeout", type=int, default=8)
    args = parser.parse_args()

    config = VoiceInputConfig(
        model_path=resolve_model_path(args.model_path),
        sample_rate=args.sample_rate,
        timeout_seconds=args.timeout,
        input_device=None if args.device < 0 else args.device,
    )

    print("Listening once. Say a short phrase like 'hello'.", flush=True)
    try:
        result = listen_once_with_confidence(config)
    except VoiceInputError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Recognized: {result.text}")
    print(
        "Capture: "
        f"device={result.input_device} "
        f"rate={result.sample_rate} "
        f"capture_seconds={result.capture_seconds:.2f} "
        f"speech_seconds={result.speech_seconds:.2f} "
        f"chunks={result.chunk_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

