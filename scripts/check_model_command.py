"""Check the assistant's read-only model listing command."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant model command check")
    response = LocalAssistant(use_llm=False).respond("models")

    if "Installed Ollama models:" in response.text:
        print(response.text)
        print("OK: Model command listed installed models.")
        return 0

    if response.text.startswith("Model error:"):
        print(response.text)
        print("OK: Model command returns a clear local Ollama error.")
        return 0

    print("ERROR: Model command returned unexpected text:")
    print(response.text)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
