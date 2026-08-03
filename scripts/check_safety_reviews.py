"""Check local signed safety review export without executing safety actions."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local assistant signed safety review export check")
    assistant = LocalAssistant(use_llm=False)
    response = assistant.respond("export safety reviews")
    print(response.text)
    if "Signed safety review export created" not in response.text:
        print("ERROR: Safety review export did not complete.")
        return 1
    if "No commands were run" not in response.text:
        print("ERROR: Safety review export did not report read-only behavior.")
        return 1
    if "safety_reviews.json" not in response.text:
        print("ERROR: Safety review export manifest was not reported.")
        return 1
    if (
        "Script review records:" not in response.text
        or "Script checklist review records:" not in response.text
        or "Script preflight review records:" not in response.text
    ):
        print("ERROR: Safety review export did not report script review record counts.")
        return 1
    print("OK: Signed safety review export is local and read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
