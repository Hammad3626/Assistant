"""Check the assistant's safety and permissions command."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant safety command check")
    assistant = LocalAssistant(use_llm=False)
    response = assistant.respond("safety")
    dashboard = assistant.respond("permissions dashboard")

    required = (
        "Safety and permissions",
        "Allowed:",
        "Requires confirmation:",
        "Blocked:",
        "Privacy:",
        "Raw arbitrary shell commands",
        "named safe shell command",
        "guided validation",
        "script allowlisting design gates",
        "allowlisted apps and folders",
    )
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: Safety command is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    dashboard_required = (
        "Permissions dashboard",
        "Apps and folders: confirmation-gated",
        "Shell commands: named allowlist with guided editor",
        "Bulk file modification: dry-run, backup, approval, review, rollback-plan, hashed signed preflight, verified checklist, and design only",
        "Messages, email, network: draft-only",
        "Scripts: review-only with allowlist design, checklist manifests, and signed export",
    )
    missing_dashboard = [phrase for phrase in dashboard_required if phrase not in dashboard.text]
    if missing_dashboard:
        print("ERROR: Permissions dashboard is missing expected text:")
        for phrase in missing_dashboard:
            print(f"- {phrase}")
        return 1

    print(response.text)
    print()
    print(dashboard.text)
    print("OK: Safety command is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
