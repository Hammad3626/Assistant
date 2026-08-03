"""Design-only script allowlisting safety plan.

This module intentionally defines review gates only. It does not create a
script allowlist, execute scripts, or approve future script execution.
"""

from __future__ import annotations


def script_allowlist_design_text() -> str:
    """Return the explicit script allowlisting design without enabling scripts."""
    return "\n".join(
        [
            "Explicit script allowlist design",
            "Status: design only. No scripts are allowlisted or executed in this build.",
            "Future command shape:",
            "- prepare: request script review <name>: <path>",
            "- inspect: script review checklist <request id>",
            "- verify: verify script review checklist <request id>",
            "- preflight: script allowlist preflight <request id>",
            "- readiness: script execution readiness <request id>",
            "- allowlist: add script allowlist <name>: <path> after verified review",
            "- execute: run script <allowed script name> after final confirmation",
            "",
            "Required static review gates:",
            "- Script path must be explicit, local, and free of shell control characters.",
            "- Extension must be one of the supported script types.",
            "- File must exist and be a regular file at review time.",
            "- File size, line count, extension, and SHA-256 hash must be recorded.",
            "- Static findings must be recorded before allowlisting.",
            "- High-risk findings require manual operator checklist review.",
            "- Missing, unreadable, or oversized scripts cannot be allowlisted automatically.",
            "",
            "Required trust gates:",
            "- Allowed script entry must pin the exact script SHA-256 hash.",
            "- Allowed script entry must pin the reviewed absolute path.",
            "- The file hash and size must match the reviewed manifest immediately before any future run.",
            "- The interpreter must be explicitly allowlisted and invoked without shell=True.",
            "- Arguments must be fixed or separately allowlisted as structured values.",
            "",
            "Required execution gates for any future implementation:",
            "- Show interpreter, path, hash, static risk, and checklist status.",
            "- Require a fresh typed phrase: confirm script run.",
            "- Refuse execution if the script changed after review.",
            "- Refuse execution if the checklist signature or manifest hash is invalid.",
            "- Record the requested script, manifest ids, confirmation, and result in action audit.",
            "",
            "Current safe commands:",
            "- request script review <name>: <path>",
            "- script review checklist <request id>",
            "- verify script review checklist <request id>",
            "- script allowlist preflight <request id>",
            "- script execution readiness <request id>",
            "- confirm script run simulation <request id>: confirm script run",
            "- script allowlist entry simulation <request id>: <interpreter> [args...]",
            "- launch requests",
            "- safety snapshot launch",
            "- safety snapshot scripts",
            "- script allowlist design",
            "",
            "Blocked in this build:",
            "- add script allowlist <name>: <path>",
            "- run script <allowed script name>",
            "- automatic script approval from LLM output or natural language.",
        ]
    )
