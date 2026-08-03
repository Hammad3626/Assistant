"""Check confirmation-gated file launch workflow with explicit file-type allowlist."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from assistant.actions import save_allowed_folders
from assistant.core import LocalAssistant
from assistant.file_type_allowlist import FileSignerInfo


def main() -> int:
    print("Local PC Assistant file launch workflow check")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace"
        workspace.mkdir()
        target = workspace / "report.pdf"
        target.write_text("local test", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"workspace": str(workspace)}, folders_path)

        assistant = LocalAssistant(
            use_llm=False,
            folders_path=folders_path,
            file_type_allowlist_path=root / "file_types.json",
        )

        blocked = assistant.respond("launch file in workspace report.pdf")
        print("> launch file in workspace report.pdf")
        print(blocked.text)
        if "File launch blocked" not in blocked.text:
            print("ERROR: launch should be blocked before file-type allowlisting.")
            return 1

        allowed = assistant.respond("allow file type pdf")
        print("> allow file type pdf")
        print(allowed.text)
        if "File type allowlisted: .pdf" not in allowed.text:
            print("ERROR: allow file type command failed.")
            return 1

        trusted = root / "trusted"
        trusted.mkdir()
        source_policy = assistant.respond(f"trust file type source .pdf: {trusted}")
        print(f"> trust file type source .pdf: {trusted}")
        print(source_policy.text)
        if "Updated trusted sources" not in source_policy.text:
            print("ERROR: source trust policy command failed.")
            return 1

        trust_blocked = assistant.respond("launch file in workspace report.pdf")
        print("> launch file in workspace report.pdf")
        print(trust_blocked.text)
        if "File launch blocked by trust checks" not in trust_blocked.text:
            print("ERROR: launch should be blocked by trusted source policy.")
            return 1

        clear_policy = assistant.respond("clear file type trust .pdf")
        print("> clear file type trust .pdf")
        print(clear_policy.text)
        if "Cleared trust policy" not in clear_policy.text:
            print("ERROR: clear trust policy command failed.")
            return 1

        thumbprint_policy = assistant.respond(
            "trust file type thumbprint .pdf: 11223344556677889900AABBCCDDEEFF00112233"
        )
        print("> trust file type thumbprint .pdf: 11223344556677889900AABBCCDDEEFF00112233")
        print(thumbprint_policy.text)
        if "Updated pinned signer thumbprints" not in thumbprint_policy.text:
            print("ERROR: thumbprint policy command failed.")
            return 1

        with patch(
            "assistant.file_type_allowlist._authenticode_signer_info",
            return_value=FileSignerInfo(
                subject="CN=Microsoft Corporation",
                thumbprint="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            ),
        ):
            thumbprint_blocked = assistant.respond("launch file in workspace report.pdf")
        print("> launch file in workspace report.pdf")
        print(thumbprint_blocked.text)
        if "thumbprint" not in thumbprint_blocked.text.lower():
            print("ERROR: launch should be blocked by thumbprint policy mismatch.")
            return 1

        clear_policy_again = assistant.respond("clear file type trust .pdf")
        print("> clear file type trust .pdf")
        print(clear_policy_again.text)
        if "Cleared trust policy" not in clear_policy_again.text:
            print("ERROR: second clear trust policy command failed.")
            return 1

        issuer_policy = assistant.respond("trust file type issuer .pdf: Microsoft Root")
        print("> trust file type issuer .pdf: Microsoft Root")
        print(issuer_policy.text)
        if "Updated trusted issuer tokens" not in issuer_policy.text:
            print("ERROR: issuer trust policy command failed.")
            return 1

        validity_policy = assistant.respond("trust file type validity .pdf: required")
        print("> trust file type validity .pdf: required")
        print(validity_policy.text)
        if "Updated certificate validity requirement" not in validity_policy.text:
            print("ERROR: validity trust policy command failed.")
            return 1

        with patch(
            "assistant.file_type_allowlist._authenticode_signer_info",
            return_value=FileSignerInfo(
                subject="CN=Microsoft Corporation",
                thumbprint="11223344556677889900AABBCCDDEEFF00112233",
                issuer="CN=Unknown Issuer",
                not_before=datetime.now(UTC) + timedelta(days=1),
                not_after=datetime.now(UTC) + timedelta(days=2),
            ),
        ):
            issuer_validity_blocked = assistant.respond("launch file in workspace report.pdf")
        print("> launch file in workspace report.pdf")
        print(issuer_validity_blocked.text)
        if "issuer" not in issuer_validity_blocked.text.lower() and "valid" not in issuer_validity_blocked.text.lower():
            print("ERROR: launch should be blocked by issuer/validity policy mismatch.")
            return 1

        clear_policy_final = assistant.respond("clear file type trust .pdf")
        print("> clear file type trust .pdf")
        print(clear_policy_final.text)
        if "Cleared trust policy" not in clear_policy_final.text:
            print("ERROR: final clear trust policy command failed.")
            return 1

        pending = assistant.respond("launch file in workspace report.pdf")
        print("> launch file in workspace report.pdf")
        print(pending.text)
        if pending.pending_action is None or pending.pending_action.kind != "file_launch":
            print("ERROR: launch should require confirmation with a file_launch pending action.")
            return 1

        with patch("assistant.core.os.startfile", create=True) as mock_startfile:
            result = assistant.confirm_pending_action(pending.pending_action)
            print("> yes")
            print(result)
            if "Done: Opened file in Windows" not in result:
                print("ERROR: confirmed launch did not complete.")
                return 1
            if mock_startfile.call_count != 1:
                print("ERROR: Windows file open was not called exactly once.")
                return 1

    print("OK: Confirmation-gated file launch workflow is working.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())