"""Check allowlisted file listing/search/preview tools without changing files."""

from __future__ import annotations

from pathlib import Path

from assistant.file_tools import AllowlistedFileTools, FileToolError, file_tools_help_text


def main() -> int:
    print("Local assistant file tools check")
    tools = AllowlistedFileTools()
    print(file_tools_help_text())

    try:
        folders = tools.folder_names()
        if not folders:
            print("ERROR: No allowlisted folders are configured.")
            return 1
        folder = "project folder" if "project folder" in folders else folders[0]
        print()
        print(tools.list_files_summary(folder, limit=5))
        readme = _first_project_text_file(Path.cwd())
        if readme is not None and folder in {"project folder", "assistant folder"}:
            print()
            print(tools.read_file_summary(folder, readme.as_posix()))
            print()
            print(tools.open_file_preview_summary(folder, readme.as_posix()))
            print()
            print(tools.search_file_names_summary(folder, readme.name))
            print()
            print(tools.bulk_replace_plan_summary(folder, "assistant", "helper"))
            print()
            print(tools.bulk_rename_plan_summary(folder, "README", "README-preview"))
            print()
            print(tools.bulk_apply_safety_text())
            print()
            print(tools.bulk_replace_apply_plan_summary(folder, "assistant", "helper"))
            print()
            print(tools.backup_bulk_replace_plan(folder, "assistant", "helper"))
            print()
            print(tools.approve_bulk_replace_plan(folder, "assistant", "helper", "1"))
            print()
            print(tools.create_bulk_apply_review().summary)
            print()
            print(tools.create_bulk_rollback_plan().summary)
            print()
            preflight = tools.create_bulk_write_preflight()
            print(preflight.summary)
            if "Manifest hashes verified" not in preflight.summary:
                print("ERROR: Bulk write preflight did not verify manifest hashes.")
                return 1
            if "Signed review metadata" not in preflight.summary:
                print("ERROR: Bulk write preflight did not include signed review metadata.")
                return 1
            print()
            write_checklist = tools.create_bulk_write_operator_checklist()
            print(write_checklist.summary)
            if "No files were written" not in write_checklist.summary:
                print("ERROR: Bulk write checklist did not report no-write behavior.")
                return 1
            print()
            restore_checklist = tools.create_bulk_restore_operator_checklist()
            print(restore_checklist.summary)
            if "No files were written" not in restore_checklist.summary:
                print("ERROR: Bulk restore checklist did not report no-write behavior.")
                return 1
            print()
            write_verification = tools.verify_bulk_write_operator_checklist()
            print(write_verification.summary)
            if write_verification.status != "verified":
                print("ERROR: Bulk write checklist verification did not verify.")
                return 1
            print()
            restore_verification = tools.verify_bulk_restore_operator_checklist()
            print(restore_verification.summary)
            if restore_verification.status != "verified":
                print("ERROR: Bulk restore checklist verification did not verify.")
                return 1
    except FileToolError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("OK: File listing, filename search, content search, safe preview, dry-run bulk plans, bulk backups, approval manifests, apply reviews, rollback plans, manifest hashes, signed review metadata, write preflights, bulk operator checklists, and checklist verification are available.")
    return 0


def _first_project_text_file(root: Path) -> Path | None:
    for name in ("README.md", "pyproject.toml"):
        path = root / name
        if path.exists():
            return path.relative_to(root)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
