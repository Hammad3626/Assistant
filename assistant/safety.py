"""Read-only safety and permission summary for the local assistant."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionRow:
    area: str
    status: str
    current_mode: str
    next_safe_step: str


def safety_text(allowed_actions_summary: str) -> str:
    """Return a concise explanation of local safety boundaries."""
    return "\n".join(
        [
            "Safety and permissions",
            "Allowed:",
            "- Answer built-in commands locally.",
            "- Use the local Ollama model for unknown questions when LLM mode is enabled.",
            "- Save explicit memories, notes, tasks, local history, and text-only voice action summaries.",
            "- Search local assistant data.",
            "- Create local-only drafts for messages, emails, and network requests.",
            "- Read and search small text previews inside allowlisted folders.",
            "- Preview bulk find/replace and filename rename plans without writing files.",
            "- Review backup, per-file approval, and audit requirements for bulk apply plans.",
            "- Create local backup copies for planned bulk file changes without applying them.",
            "- Save local per-file approval manifests for planned bulk file changes.",
            "- Create audit-linked bulk apply review manifests without applying changes.",
            "- Create rollback plans from local bulk backups without restoring files.",
            "- Create bulk write preflight manifests without writing or restoring files.",
            "- Add and verify manifest hashes to bulk backup, approval, rollback, review, and preflight records.",
            "- Add signed review metadata to bulk write preflight records without enabling writes.",
            "- Verify bulk write and restore checklist signatures and source manifests without applying changes.",
            "- Export signed shell, bulk, and script safety review records locally without executing actions.",
            "- Show read-only safety snapshots for recent launch requests, script reviews, and shell review records.",
            "- Review confirmed bulk write and restore command designs without enabling writes.",
            "- Create local operator checklist files for future bulk write and restore reviews without applying changes.",
            "- Move individual allowlisted text files to assistant trash after confirmation.",
            "- Move individual memories to local trash after confirmation.",
            "- Run named safe shell commands from the local allowlist after confirmation.",
            "- Edit named safe shell command allowlists with guided validation, static review notes, static risk scoring, and signed review metadata.",
            "- Create local operator checklist files for shell command reviews without running commands.",
            "- Verify shell checklist signatures and no-run flags without running commands.",
            "- Open allowlisted apps and folders only after confirmation.",
            "- Save local review requests for unlisted apps, scripts, files, or folders without opening them.",
            "- Create read-only static inspection summaries for script review requests without running scripts.",
            "- Review explicit script allowlisting design gates without enabling script execution.",
            "- Create and verify local script operator checklist manifests without running or allowlisting scripts.",
            "- Export signed script review records locally without running or allowlisting scripts.",
            "- Filter read-only safety snapshots to script review requests and checklist verification details without running scripts.",
            "- Create review-only script allowlist preflight records without running or allowlisting scripts.",
            "- Review latest script readiness, run-simulation, and allowlist-entry simulation gate states in read-only safety snapshots.",
            "- Surface explicit script drift warnings for signature/hash/path mismatches in read-only safety snapshots.",
            "- Use drift-only script snapshot views to triage only requests with active drift warnings.",
            "- Use warning-type breakdown counts in drift snapshots to prioritize signature/hash/path remediation.",
            "- Use warning-type filtered drift snapshots to review only signature, hash, or path issues.",
            "- Run read-only file-type review when saving unlisted file open requests.",
            "- Launch files in Windows only after confirmation when both folder and file type are allowlisted.",
            "- Optionally require trusted source roots or trusted signer tokens for launch-allowlisted file types.",
            "- Optionally pin launch-allowlisted file types to exact certificate thumbprints.",
            "- Optionally require certificate issuer token matches and currently-valid certificate dates.",
            "- Preview and correct spoken action commands before confirmation.",
            "",
            "Current allowlists:",
            f"- {allowed_actions_summary}",
            "",
            "Requires confirmation:",
            "- Opening an allowlisted app.",
            "- Opening an allowlisted folder.",
            "- Opening files or folders in Windows Explorer.",
            "- Moving an allowlisted text file to assistant trash.",
            "- Moving an individual memory to local trash.",
            "- Running a named safe shell command.",
            "",
            "Blocked:",
            "- Raw arbitrary shell commands.",
            "- Permanent file deletion or destructive filesystem changes.",
            "- Applying bulk file modification plans.",
            "- Reading files outside allowlisted folders.",
            "- Sending messages or emails on your behalf.",
            "- Making network requests on your behalf, except existing local assistant health/model checks.",
            "- Opening unlisted apps or folders as an explicit opt-in (off by default; still confirmation-gated and denylist-enforced against system tools like cmd/powershell/regedit).",
            "- Opening arbitrary files or documents outside designed allowlists.",
            "- Running cmd.exe, powershell.exe, pwsh.exe, scripts, or registry tools as app actions.",
            "- Auto-adding unlisted apps or scripts to allowlists.",
            "- Shell pipelines, redirection, command chaining, and unlisted executables.",
            "",
            "Privacy:",
            "- Core data stays in local project files.",
            "- Voice input uses the local Vosk model.",
            "- Voice status, paths, models, status, and data report are read-only.",
        ]
    )


def permission_dashboard_text(allowed_actions_summary: str) -> str:
    """Return a structured safety dashboard for gated capabilities."""
    rows = (
        PermissionRow(
            area="Apps and folders",
            status="confirmation-gated",
            current_mode="Allowlisted apps/folders can open only after confirmation.",
            next_safe_step="Use review requests before adding new apps or folders.",
        ),
        PermissionRow(
            area="Arbitrary files/documents",
            status="confirmation-gated with explicit file-type allowlist",
            current_mode="Allowlisted folder files can be previewed safely, and Windows file launch requires explicit file-type allowlisting plus confirmation. Optional trust signals can enforce trusted source roots, signer-token checks, exact certificate thumbprint pins, issuer-token checks, currently-valid certificate dates, and revocation modes with signed-file review notes explaining what blocked or allowed launch.",
            next_safe_step="Keep file launch confirmation-gated while improving script review safety.",
        ),
        PermissionRow(
            area="Shell commands",
            status="named allowlist with guided editor",
            current_mode="Only configured command names run, each run requires confirmation, and allowlist edits use validation, static review notes, static risk scoring, signed review metadata, local review export, operator checklist files, checklist verification, and read-only safety snapshots.",
            next_safe_step="Keep raw shell execution blocked unless a separate safety design is approved.",
        ),
        PermissionRow(
            area="File deletion",
            status="reversible trash only",
            current_mode="Individual allowlisted text files move to assistant trash after confirmation.",
            next_safe_step="Keep restore/dry-run before considering broader file operations.",
        ),
        PermissionRow(
            area="Bulk file modification",
            status="dry-run, backup, approval, review, rollback-plan, hashed signed preflight, verified checklist, and design only",
            current_mode="Bulk changes can be previewed, backed up, approved, reviewed, rollback-planned, hash-checked, signed-preflighted, checklisted, checklist-verified, exported for review, and designed locally, but not applied or restored.",
            next_safe_step="Keep bulk apply and restore blocked unless a separate implementation safety review is approved.",
        ),
        PermissionRow(
            area="Messages, email, network",
            status="draft-only",
            current_mode="Drafts are saved locally; nothing is sent and no external request is made.",
            next_safe_step="Require account setup, preview, recipient validation, and final confirmation.",
        ),
        PermissionRow(
            area="Scripts",
            status="review-only with allowlist design, checklist manifests, and signed export",
            current_mode="Script requests can be saved for review, summarized in filtered safety snapshots with checklist, preflight, readiness, run-simulation, and allowlist-entry simulation details, statically inspected when the file exists, compared against a design-only allowlisting gate plan, written to signed local operator checklist manifests, preflighted as review-only allowlist records, and exported as signed local review records including preflights, but are not executed or allowlisted.",
            next_safe_step="Add severity-threshold filtering in drift snapshots so operators can prioritize requests with multiple simultaneous warning types.",
        ),
        PermissionRow(
            area="Memory and tasks",
            status="local enabled with item controls",
            current_mode="Explicit memories, notes, and tasks are stored in local project files. Individual memories can be renamed, moved to local trash after confirmation, and restored. Tasks support edit, trash, restore, and GUI review controls.",
            next_safe_step="Maintain local-only storage and confirmation gates as task features expand.",
        ),
        PermissionRow(
            area="Voice",
            status="local optional with preview, second confirmation, and text audit",
            current_mode="Voice input uses local Vosk when enabled; wake mode is opt-in, and spoken actions show a preview, richer correction phrases, read-only confidence reporting, second confirmation for low-confidence actions, GUI action review, GUI voice audit review controls, GUI filtered audit/export/retention buttons, read-only voice audit filters/export, a no-microphone safety drill, local text-only voice action summaries, and confirmed retention cleanup with backup.",
            next_safe_step="Keep voice automation confirmation-gated while improving review visibility.",
        ),
    )

    lines = [
        "Permissions dashboard",
        "This is read-only and does not change permissions.",
        "",
        "Current allowlists:",
        f"- {allowed_actions_summary}",
        "",
        "Capability status:",
    ]
    for row in rows:
        lines.extend(
            [
                f"- {row.area}: {row.status}",
                f"  Current: {row.current_mode}",
                f"  Next safe step: {row.next_safe_step}",
            ]
        )

    lines.extend(
        [
            "",
            "Blocked until explicit safety design:",
            "- Raw arbitrary shell commands.",
            "- Permanent deletion.",
            "- Applying bulk file modification plans.",
            "- Sending messages, emails, or network requests.",
            "- Running unreviewed scripts or unlisted executables.",
        ]
    )
    return "\n".join(lines)
