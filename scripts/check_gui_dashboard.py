"""Check the read-only GUI startup dashboard text."""

from __future__ import annotations

from assistant.core import LocalAssistant
from assistant.gui_dashboard import build_startup_dashboard, build_startup_health_rows
from assistant.settings import load_settings


def main() -> int:
    print("Local PC Assistant GUI dashboard check")
    settings = load_settings("config/settings.json")
    dashboard = build_startup_dashboard(
        settings,
        LocalAssistant(use_llm=False, voice_model_path=settings.voice_model_path),
        "disabled",
        0,
    )
    rows = build_startup_health_rows(
        settings,
        LocalAssistant(use_llm=False, voice_model_path=settings.voice_model_path),
        "disabled",
        0,
    )

    required = (
        "Startup dashboard",
        "Assistant:",
        "Model:",
        "Voice model:",
        "Local data:",
        "Useful commands:",
    )
    missing = [phrase for phrase in required if phrase not in dashboard]
    if missing:
        print("ERROR: GUI dashboard is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(dashboard)
    print()
    print("Startup health rows:")
    for row in rows:
        prefix = "OK" if row.ok else "Check"
        print(f"- {row.label}: {prefix}: {row.value}")
    print("OK: GUI dashboard is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
