"""Focused offline help topics for assistant commands."""

from __future__ import annotations


HELP_TOPICS = {
    "about": (
        "Help: about\n"
        "Use about to see a local architecture summary.\n"
        "Commands:\n"
        "- about\n"
        "- about assistant\n"
        "- architecture\n"
        "- system architecture\n"
        "This command is read-only and explains the assistant's local components."
    ),
    "actions": (
        "Help: actions\n"
        "Use actions to open allowlisted local apps and folders, run named safe shell commands, or review unlisted open requests.\n"
        "Commands:\n"
        "- actions\n"
        "- launch requests\n"
        "- file type allowlist\n"
        "- file type trust <extension>\n"
        "- allow file type <extension>\n"
        "- disallow file type <extension>\n"
        "- trust file type source <extension>: <source path>[; <source path>...]\n"
        "- trust file type signer <extension>: <signer token>[; <signer token>...]\n"
        "- trust file type thumbprint <extension>: <thumbprint>[; <thumbprint>...]\n"
        "- trust file type issuer <extension>: <issuer token>[; <issuer token>...]\n"
        "- trust file type validity <extension>: required|off\n"
        "- trust file type revocation <extension>: required|off|ocsp|crl|both\n"
        "- clear file type trust <extension>\n"
        "- request app <name>: <exe>\n"
        "- request script review <name>: <path>\n"
        "- script review checklist <request number>\n"
        "- verify script review checklist <request number>\n"
        "- script allowlist preflight <request number>\n"
        "- script execution readiness <request number>\n"
        "- confirm script run simulation <request number>: confirm script run\n"
        "- script allowlist entry simulation <request number>: <interpreter> [args...]\n"
        "- script allowlist design\n"
        "- request file review <name>: <path>\n"
        "- request folder review <name>: <path>\n"
        "- shell commands\n"
        "- run shell <allowed command name>\n"
        "- open calculator\n"
        "- open notepad\n"
        "- open paint\n"
        "- open chrome\n"
        "- open C drive\n"
        "- open D drive\n"
        "- open this pc\n"
        "- open settings\n"
        "- open documents\n"
        "- open downloads\n"
        "- open desktop\n"
        "- open project folder\n"
        "Safety: allowlisted actions and named shell commands require confirmation before they run. Unlisted app/script/file/folder requests are local review notes only. Script requests include read-only static inspection summaries when the file exists. Script review checklists, script allowlist preflights, script execution readiness bundles, confirmed-run simulations, and allowlist-entry simulations create local review manifests only; they do not allowlist or run scripts. Script allowlist design is design-only and does not allowlist or run scripts. File requests include read-only file-type risk notes plus explicit file-type launch eligibility."
    ),
    "shell": (
        "Help: shell\n"
        "Use shell commands for named, allowlisted local diagnostics only.\n"
        "Commands:\n"
        "- shell commands\n"
        "- safe shell\n"
        "- allowed shell commands\n"
        "- shell command guide\n"
        "- shell command wizard\n"
        "- add shell command <name>: <executable> [args...]\n"
        "- shell wizard add <name>: <executable> [args...]\n"
        "- shell review checklist <allowed command name>\n"
        "- verify shell checklist <allowed command name>\n"
        "- remove shell command <name>\n"
        "- run shell <allowed command name>\n"
        "Safety: adding a command does not run it. Static review notes, static risk scoring, and signed review metadata are saved. raw arbitrary shell text, pipelines, redirection, shell chaining, scripts, inline code, and destructive commands are blocked."
    ),
    "briefing": (
        "Help: briefing\n"
        "Use briefing for a read-only daily summary from local data.\n"
        "Commands:\n"
        "- briefing\n"
        "- daily briefing\n"
        "- good morning\n"
        "Includes saved memory count, open tasks, and recent notes."
    ),
    "data": (
        "Help: data\n"
        "Use data commands to inspect or export local assistant data.\n"
        "Commands:\n"
        "- data report\n"
        "- privacy report\n"
        "- export data\n"
        "- export safety reviews\n"
        "- backup data\n"
        "- backups\n"
        "Exports are local-only and written under the configured export folder."
    ),
    "history": (
        "Help: history\n"
        "Use history to review or clear saved conversation turns.\n"
        "Commands:\n"
        "- history\n"
        "- show history\n"
        "- recent history\n"
        "- clear history\n"
        "Clearing history does not clear memories, notes, or tasks."
    ),
    "memory": (
        "Help: memory\n"
        "Use memory for explicit facts you want the assistant to remember.\n"
        "Commands:\n"
        "- remember <fact>\n"
        "- memories\n"
        "- show memories\n"
        "- rename memory <number> to <new text>\n"
        "- delete memory <number>\n"
        "- memory trash\n"
        "- restore memory <trash number>\n"
        "- forget memories\n"
        "Memory is local and only saved when you use remember. Delete requires confirmation and moves one memory to local trash."
    ),
    "models": (
        "Help: models\n"
        "Use models to inspect installed local Ollama models.\n"
        "Commands:\n"
        "- models\n"
        "- list models\n"
        "- ollama models\n"
        "- local models\n"
        "This command is read-only. To change the default model, use scripts/models.py."
    ),
    "paths": (
        "Help: paths\n"
        "Use paths to see where local assistant files are stored and detect Windows locations.\n"
        "Commands:\n"
        "- paths\n"
        "- file paths\n"
        "- data paths\n"
        "- where is my data\n"
        "- detected folders\n"
        "- detected drives\n"
        "- detected locations\n"
        "These commands are read-only and do not open files or update allowlists."
    ),
    "safety": (
        "Help: safety\n"
        "Use safety to review local permissions and blocked actions.\n"
        "Commands:\n"
        "- safety\n"
        "- permissions\n"
        "- permissions dashboard\n"
        "- safety snapshot\n"
        "- safety snapshot launch\n"
        "- safety snapshot shell\n"
        "- safety snapshot scripts\n"
        "- safety snapshot scripts drift\n"
        "- safety snapshot scripts drift signature\n"
        "- safety snapshot scripts drift hash\n"
        "- safety snapshot scripts drift path\n"
        "- safety snapshot scripts drift threshold <1-3>\n"
        "- review snapshot\n"
        "- safety dashboard\n"
        "- security\n"
        "- privacy\n"
        "These commands are read-only and explain confirmation, allowlist, launch request, script review, and shell review rules."
    ),
    "roadmap": (
        "Help: roadmap\n"
        "Use roadmap to see what is working and what upgrades are reasonable next.\n"
        "Commands:\n"
        "- roadmap\n"
        "- next steps\n"
        "- project roadmap\n"
        "- what next\n"
        "This command is read-only and separates required capabilities from optional upgrades."
    ),
    "launch": (
        "Help: launch\n"
        "Use launch commands to see exact terminal commands for common assistant modes.\n"
        "Commands:\n"
        "- launch commands\n"
        "- start commands\n"
        "- startup commands\n"
        "- how do i launch\n"
        "This command is read-only and is useful when PowerShell scripts are blocked."
    ),
    "notes": (
        "Help: notes\n"
        "Use notes for append-only local notes.\n"
        "Commands:\n"
        "- note <text>\n"
        "- take note <text>\n"
        "- notes\n"
        "- show notes\n"
        "Notes are saved locally in the configured notes file."
    ),
    "outbox": (
        "Help: outbox\n"
        "Use outbox to prepare local drafts without sending anything.\n"
        "Commands:\n"
        "- outbox\n"
        "- drafts\n"
        "- draft message to <recipient>: <text>\n"
        "- draft email to <recipient> subject <subject>: <text>\n"
        "- draft network request GET <url> [note]\n"
        "Safety: drafts are local only. The assistant does not send messages, send emails, or make network requests on your behalf."
    ),
    "search": (
        "Help: search\n"
        "Use search to find matching text across local memory, notes, tasks, history, and allowlisted files.\n"
        "Commands:\n"
        "- search <text>\n"
        "- find <text>\n"
        "- file tools\n"
        "- list files in <folder>\n"
        "- search files in <folder> for <text>\n"
        "- find files in <folder> for <name text>\n"
        "- read file in <folder> <relative path>\n"
        "- open file in <folder> <relative path>\n"
        "- launch file in <folder> <relative path>\n"
        "- file type trust <extension>\n"
        "- trust file type source <extension>: <source path>[; <source path>...]\n"
        "- trust file type signer <extension>: <signer token>[; <signer token>...]\n"
        "- trust file type thumbprint <extension>: <thumbprint>[; <thumbprint>...]\n"
        "- trust file type issuer <extension>: <issuer token>[; <issuer token>...]\n"
        "- trust file type validity <extension>: required|off\n"
        "- trust file type revocation <extension>: required|off|ocsp|crl|both\n"
        "- clear file type trust <extension>\n"
        "- preview replace in <folder> find <text> with <text>\n"
        "- preview rename files in <folder> replace <name text> with <name text>\n"
        "- bulk apply safety\n"
        "- bulk replace apply plan in <folder> find <text> with <text>\n"
        "- bulk rename apply plan in <folder> replace <name text> with <name text>\n"
        "- backup bulk replace in <folder> find <text> with <text>\n"
        "- backup bulk rename in <folder> replace <name text> with <name text>\n"
        "- approve bulk replace in <folder> find <text> with <text> files <numbers|all>\n"
        "- approve bulk rename in <folder> replace <name text> with <name text> files <numbers|all>\n"
        "- bulk apply review\n"
        "- bulk rollback plan\n"
        "- bulk write preflight\n"
        "- bulk write checklist\n"
        "- bulk restore checklist\n"
        "- verify bulk write checklist\n"
        "- verify bulk restore checklist\n"
        "- bulk write command design\n"
        "- bulk restore command design\n"
        "Search is local and does not contact the internet."
    ),
    "files": (
        "Help: files\n"
        "Use file tools to safely inspect, confirmation-launch allowlisted file types, and trash text files inside allowlisted folders.\n"
        "Commands:\n"
        "- file tools\n"
        "- list files in <folder>\n"
        "- search files in <folder> for <text>\n"
        "- find files in <folder> for <name text>\n"
        "- read file in <folder> <relative path>\n"
        "- open file in <folder> <relative path>\n"
        "- launch file in <folder> <relative path>\n"
        "- file type trust <extension>\n"
        "- trust file type source <extension>: <source path>[; <source path>...]\n"
        "- trust file type signer <extension>: <signer token>[; <signer token>...]\n"
        "- trust file type thumbprint <extension>: <thumbprint>[; <thumbprint>...]\n"
        "- trust file type issuer <extension>: <issuer token>[; <issuer token>...]\n"
        "- trust file type validity <extension>: required|off\n"
        "- trust file type revocation <extension>: required|off|ocsp|crl|both\n"
        "- clear file type trust <extension>\n"
        "- preview replace in <folder> find <text> with <text>\n"
        "- preview rename files in <folder> replace <name text> with <name text>\n"
        "- bulk apply safety\n"
        "- bulk replace apply plan in <folder> find <text> with <text>\n"
        "- bulk rename apply plan in <folder> replace <name text> with <name text>\n"
        "- backup bulk replace in <folder> find <text> with <text>\n"
        "- backup bulk rename in <folder> replace <name text> with <name text>\n"
        "- approve bulk replace in <folder> find <text> with <text> files <numbers|all>\n"
        "- approve bulk rename in <folder> replace <name text> with <name text> files <numbers|all>\n"
        "- bulk apply review\n"
        "- bulk rollback plan\n"
        "- bulk write preflight\n"
        "- bulk write checklist\n"
        "- bulk restore checklist\n"
        "- verify bulk write checklist\n"
        "- verify bulk restore checklist\n"
        "- bulk write command design\n"
        "- bulk restore command design\n"
        "- delete file in <folder> <relative path>\n"
        "- file trash\n"
        "- restore file <trash number>\n"
        "Safety: open shows a local text preview only. Bulk previews and apply plans do not write files. Bulk backups and approvals save local files without changing originals. Delete requires confirmation and moves common text files to assistant trash."
    ),
    "status": (
        "Help: status\n"
        "Use status to inspect the assistant setup without changing anything.\n"
        "Commands:\n"
        "- status\n"
        "- health\n"
        "- system status\n"
        "Status is read-only and checks local configuration, data counts, and Ollama reachability."
    ),
    "tasks": (
        "Help: tasks\n"
        "Use tasks for a local to-do list.\n"
        "Commands:\n"
        "- todo <task>\n"
        "- todo <task> due YYYY-MM-DD\n"
        "- tasks\n"
        "- done <task number>\n"
        "- restore task <completed number>\n"
        "- delete task <number>\n"
        "- task trash\n"
        "- restore deleted task <number>\n"
        "- due today\n"
        "- due soon\n"
        "- overdue\n"
        "- upcoming\n"
        "- task stats\n"
        "- rename task <number> to <text>\n"
        "- due <number> YYYY-MM-DD\n"
        "- clear due <number>\n"
        "- completed tasks\n"
        "- all tasks\n"
        "Open task numbers come from the tasks list. Restore numbers come from completed tasks. Delete requires confirmation and moves tasks to trash."
    ),
    "voice": (
        "Help: voice\n"
        "Use voice mode from the terminal launch command.\n"
        "Examples:\n"
        "- python -m assistant.cli --voice --voice-timeout 10\n"
        "- python -m assistant.cli --speak\n"
        "- python -m assistant.cli --voice --speak --voice-timeout 10\n"
        "- python -m assistant.cli --wake --speak\n"
        "- voice status\n"
        "- voice confidence\n"
        "- voice safety drill\n"
        "- voice audit\n"
        "- voice audit confidence low\n"
        "- voice audit event action_preview\n"
        "- export voice audit\n"
        "- voice audit retention keep 100\n"
        "- prune voice audit keep 100\n"
        "- wake status\n"
        "Voice input uses the local Vosk model. Voice audit stores and exports local text summaries only, never audio. Voice audit retention previews are read-only; pruning requires confirmation and writes a local backup first. Voice confidence is read-only and does not confirm actions. Low-confidence spoken actions require the extra phrase 'confirm action'. Voice output uses Windows speech."
    ),
}

TOPIC_ALIASES = {
    "architecture": "about",
    "system": "about",
    "action": "actions",
    "apps": "actions",
    "app": "actions",
    "safe shell": "shell",
    "backup": "data",
    "backups": "data",
    "briefings": "briefing",
    "health": "status",
    "memories": "memory",
    "model": "models",
    "ollama": "models",
    "note": "notes",
    "draft": "outbox",
    "drafts": "outbox",
    "outbox": "outbox",
    "email": "outbox",
    "message": "outbox",
    "network": "outbox",
    "files": "files",
    "file": "files",
    "file tools": "files",
    "local files": "files",
    "allowed files": "files",
    "permissions": "safety",
    "security": "safety",
    "privacy": "safety",
    "next": "roadmap",
    "steps": "roadmap",
    "project": "roadmap",
    "startup": "launch",
    "start": "launch",
    "speech": "voice",
    "microphone": "voice",
    "wake": "voice",
    "todo": "tasks",
    "task": "tasks",
}


def help_topics_text() -> str:
    """Return a compact list of focused help topics."""
    topics = ", ".join(sorted(HELP_TOPICS))
    return f"Help topics: {topics}.\nUse help <topic>, for example: help tasks."


def command_help_text(topic: str) -> str:
    """Return focused help for a topic, or a list of available topics."""
    normalized = " ".join(topic.strip().lower().split())
    if not normalized:
        return help_topics_text()

    canonical = TOPIC_ALIASES.get(normalized, normalized)
    help_text = HELP_TOPICS.get(canonical)
    if help_text:
        return help_text

    return f"I do not have help for '{topic}'.\n{help_topics_text()}"
