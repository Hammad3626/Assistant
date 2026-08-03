"""Deterministic natural command normalization for the local assistant.

This layer rewrites friendly phrasing into commands the assistant already
supports. It does not grant new permissions or execute anything by itself.
"""

from __future__ import annotations

import re


_DIRECT_MAPPINGS = {
    "good afternoon": "hello",
    "good evening": "hello",
    "good night": "hello",
    "hey assistant": "hello",
    "hey jarvis": "hello",
    "hi assistant": "hello",
    "hi jarvis": "hello",
    "how are you": "hello",
    "what can you do for me": "help",
    "what commands do you know": "command reference",
    "show all commands": "command reference",
    "show command list": "command reference",
    "list commands": "command reference",
    "show help": "help",
    "show configuration": "settings",
    "show config": "settings",
    "assistant settings": "settings",
    "assistant status": "status",
    "system health": "status",
    "health check": "status",
    "are you healthy": "status",
    "show installed models": "models",
    "what models are installed": "models",
    "show local models": "models",
    "show ollama models": "models",
    "check microphone": "voice status",
    "microphone status": "voice status",
    "voice setup status": "voice status",
    "show voice confidence": "voice confidence",
    "speech confidence status": "voice confidence",
    "how confident was voice input": "voice confidence",
    "show voice safety drill": "voice safety drill",
    "practice voice confirmation": "voice safety drill",
    "simulate low confidence voice": "voice safety drill",
    "show voice audit": "voice audit",
    "show voice action audit": "voice audit",
    "show recognized voice commands": "voice audit",
    "show low confidence voice audit": "voice audit confidence low",
    "show voice audit retention": "voice audit retention keep 100",
    "preview voice audit cleanup": "voice audit retention keep 100",
    "export voice action audit": "export voice audit",
    "backup voice audit": "export voice audit",
    "wake mode status": "wake status",
    "show wake status": "wake status",
    "show file tools": "file tools",
    "show safe file tools": "file tools",
    "show shell commands": "shell commands",
    "show safe shell commands": "shell commands",
    "show shell command guide": "shell command guide",
    "how do i add a shell command": "shell command guide",
    "how do i add safe shell commands": "shell command guide",
    "open shell command wizard": "shell command wizard",
    "start shell command wizard": "shell command wizard",
    "safe shell wizard": "shell command wizard",
    "show bulk apply safety": "bulk apply safety",
    "show bulk file apply safety": "bulk apply safety",
    "how would you safely apply bulk changes": "bulk apply safety",
    "how would you safely apply bulk file changes": "bulk apply safety",
    "show bulk apply review": "bulk apply review",
    "review bulk apply": "bulk apply review",
    "show bulk rollback plan": "bulk rollback plan",
    "show bulk restore plan": "bulk rollback plan",
    "plan bulk rollback": "bulk rollback plan",
    "show bulk write preflight": "bulk write preflight",
    "preflight bulk write": "bulk write preflight",
    "preflight bulk apply": "bulk write preflight",
    "design bulk write command": "bulk write command design",
    "show bulk write command design": "bulk write command design",
    "design confirmed bulk write": "bulk write command design",
    "design bulk restore command": "bulk restore command design",
    "show bulk restore command design": "bulk restore command design",
    "design confirmed bulk restore": "bulk restore command design",
    "design script allowlist": "script allowlist design",
    "design script allowlisting": "script allowlist design",
    "show script allowlist design": "script allowlist design",
    "show script allowlisting design": "script allowlist design",
    "how would you safely allow scripts": "script allowlist design",
    "show outbox drafts": "outbox",
    "show drafts": "outbox",
    "show launch requests": "launch requests",
    "show app requests": "launch requests",
    "show safety snapshot": "safety snapshot",
    "show review snapshot": "safety snapshot",
    "show launch safety snapshot": "safety snapshot launch",
    "show shell safety snapshot": "safety snapshot shell",
    "show script safety snapshot": "safety snapshot scripts",
    "show script review snapshot": "safety snapshot scripts",
    "show drives": "detected drives",
    "what drives do i have": "detected drives",
    "show detected drives": "detected drives",
    "show detected folders": "detected folders",
    "show windows folders": "detected folders",
    "show windows locations": "detected locations",
    "show permissions dashboard": "permissions dashboard",
    "show safety dashboard": "permissions dashboard",
    "what is allowed": "permissions dashboard",
    "what is blocked": "permissions dashboard",
    "show memories": "memories",
    "show my memories": "memories",
    "show my notes": "notes",
    "show my tasks": "tasks",
    "list my tasks": "tasks",
    "list tasks": "tasks",
    "list todos": "tasks",
}


def normalize_intent(text: str) -> str | None:
    """Return a known safe command for natural phrasing, or None.

    The output is always an existing assistant command. Requests that mention
    arbitrary paths, unlisted apps, sending, or raw commands are left alone so
    the core router can block or review them normally.
    """
    original = " ".join(text.strip().split())
    if not original:
        return None

    command_text = _strip_polite_prefixes(original)
    normalized = _normalize_text(command_text)
    if not normalized:
        return None

    direct = _DIRECT_MAPPINGS.get(normalized)
    if direct:
        return _changed(original, direct)

    mapped = _normalize_time_date(normalized)
    if mapped:
        return _changed(original, mapped)

    mapped = _normalize_open_command(normalized)
    if mapped:
        return _changed(original, mapped)

    mapped = _normalize_memory_note_task(command_text)
    if mapped:
        return _changed(original, mapped)

    mapped = _normalize_search(command_text)
    if mapped:
        return _changed(original, mapped)

    mapped = _normalize_file_tools(command_text)
    if mapped:
        return _changed(original, mapped)

    mapped = _normalize_shell(command_text)
    if mapped:
        return _changed(original, mapped)

    return None


def _changed(original: str, mapped: str) -> str | None:
    if _normalize_text(original) == _normalize_text(mapped):
        return None
    return mapped


def _normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[?!]+$", "", text)
    text = text.replace("what's", "what is")
    text = text.replace("whats", "what is")
    text = text.replace("c colon", "c:")
    text = text.replace("d colon", "d:")
    return " ".join(text.split())


def _strip_polite_prefixes(text: str) -> str:
    cleaned = text.strip(" ,")
    prefixes = (
        r"please\s+",
        r"jarvis[, ]+",
        r"assistant[, ]+",
        r"can you\s+",
        r"could you\s+",
        r"would you\s+",
        r"will you\s+",
    )
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            new_text = re.sub(rf"^{prefix}", "", cleaned, flags=re.IGNORECASE).strip(" ,")
            if new_text != cleaned:
                cleaned = new_text
                changed = True
    return cleaned


def _normalize_time_date(normalized: str) -> str | None:
    if normalized in {
        "current time",
        "tell me the time",
        "tell me current time",
        "what is the current time",
        "what time is it now",
    }:
        return "time"
    if normalized in {
        "current date",
        "tell me the date",
        "what day is it",
        "what is today's date",
        "what is todays date",
    }:
        return "date"
    return None


def _normalize_open_command(normalized: str) -> str | None:
    # Let exact absolute paths fall through to the existing blocked/review path.
    if re.search(r"\b(open|launch|start|show)\s+[a-z]:\\", normalized):
        return None

    app_patterns = {
        "calculator": r"(?:open|launch|start|run)\s+(?:the\s+)?(?:calculator|calc)(?:\s+app)?",
        "notepad": r"(?:open|launch|start|run)\s+(?:the\s+)?notepad(?:\s+app)?",
        "chrome": r"(?:open|launch|start|run)\s+(?:google\s+)?chrome(?:\s+browser|\s+app)?",
    }
    for target, pattern in app_patterns.items():
        if re.fullmatch(pattern, normalized):
            return f"open {target}"

    folder_patterns = {
        "downloads": r"(?:open|show|launch|start)\s+(?:my\s+|the\s+)?downloads(?:\s+folder)?",
        "documents": r"(?:open|show|launch|start)\s+(?:my\s+|the\s+)?documents(?:\s+folder)?",
        "project folder": r"(?:open|show|launch|start)\s+(?:my\s+|the\s+)?(?:project|assistant)(?:\s+folder)?",
        "assistant folder": r"(?:open|show|launch|start)\s+(?:my\s+|the\s+)?assistant folder",
    }
    for target, pattern in folder_patterns.items():
        if re.fullmatch(pattern, normalized):
            return f"open {target}"

    if re.fullmatch(r"(?:open|show)\s+(?:this pc|my computer|computer|file explorer)", normalized):
        return "open this pc"

    if re.fullmatch(r"(?:open|show|launch|start)\s+(?:windows\s+)?settings(?:\s+app)?", normalized):
        return "open settings"

    drive_match = re.fullmatch(
        r"(?:open|show)\s+(?:drive\s+)?([a-z])(?::)?(?:\s+drive|\s+local disk)?",
        normalized,
    )
    if drive_match:
        return f"open {drive_match.group(1).upper()} drive"

    return None


def _normalize_memory_note_task(text: str) -> str | None:
    patterns = (
        (r"^(?:save memory that|save a memory that|save memory|save a memory|remember that|remember)\s+(.+)$", "remember"),
        (r"^(?:make a note to|make a note|write a note to|write note|take a note|note that)\s+(.+)$", "note"),
        (r"^(?:add task to|add task|add a task to|add a task|remind me to|create task to|create task)\s+(.+)$", "todo"),
    )
    for pattern, command in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            payload = match.group(1).strip(" .")
            if payload:
                return f"{command} {payload}"
    return None


def _normalize_search(text: str) -> str | None:
    match = re.match(r"^(?:search for|find in my data|find locally|look up locally)\s+(.+)$", text, flags=re.IGNORECASE)
    if match:
        query = match.group(1).strip(" .")
        if query:
            return f"search {query}"
    return None


def _normalize_file_tools(text: str) -> str | None:
    normalized = _normalize_text(text)
    if normalized.startswith((
        "search files in ",
        "find files in ",
        "preview replace in ",
        "preview rename files in ",
        "bulk replace apply plan in ",
        "bulk rename apply plan in ",
        "backup bulk replace in ",
        "backup bulk rename in ",
        "approve bulk replace in ",
        "approve bulk rename in ",
    )):
        return None

    match = re.match(
        r"^(?:list|show)\s+files\s+in\s+(?:my\s+|the\s+)?(.+?)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        folder = _normalize_folder_name(match.group(1))
        if folder:
            return f"list files in {folder}"

    match = re.match(
        r"^search\s+(?:my\s+|the\s+)?(.+?)\s+for\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        folder = _normalize_folder_name(match.group(1))
        query = match.group(2).strip(" .")
        if folder and query:
            return f"search files in {folder} for {query}"

    match = re.match(
        r"^(?:find|search)\s+(?:file\s+names|filenames|files)\s+in\s+(?:my\s+|the\s+)?(.+?)\s+for\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        folder = _normalize_folder_name(match.group(1))
        query = match.group(2).strip(" .")
        if folder and query:
            return f"find files in {folder} for {query}"

    match = re.match(
        r"^dry run\s+replace\s+in\s+(?:my\s+|the\s+)?(.+?)\s+find\s+(.+?)\s+with\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        folder = _normalize_folder_name(match.group(1))
        old_text = match.group(2).strip(" .")
        new_text = match.group(3).strip(" .")
        if folder and old_text and new_text:
            return f"preview replace in {folder} find {old_text} with {new_text}"

    match = re.match(
        r"^dry run\s+rename\s+files\s+in\s+(?:my\s+|the\s+)?(.+?)\s+replace\s+(.+?)\s+with\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        folder = _normalize_folder_name(match.group(1))
        old_text = match.group(2).strip(" .")
        new_text = match.group(3).strip(" .")
        if folder and old_text and new_text:
            return f"preview rename files in {folder} replace {old_text} with {new_text}"

    match = re.match(
        r"^(?:open|preview)\s+file\s+in\s+(?:my\s+|the\s+)?(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        folder, relative_path = _split_folder_and_relative_path(match.group(1))
        if folder and relative_path:
            return f"open file in {folder} {relative_path}"

    match = re.match(
        r"^(?:open|preview)\s+(.+?)\s+in\s+(?:my\s+|the\s+)?(.+?)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        relative_path = match.group(1).strip(" .")
        folder = _normalize_folder_name(match.group(2))
        if folder and relative_path:
            return f"open file in {folder} {relative_path}"

    return None


def _normalize_shell(text: str) -> str | None:
    normalized = _normalize_text(text)
    if normalized in {"run python version check", "check python version", "show python version"}:
        return "run shell python version"
    return None


def _normalize_folder_name(text: str) -> str:
    folder = text.strip(" .").lower()
    if folder in {"downloads folder", "download folder"}:
        return "downloads"
    if folder in {"documents folder", "document folder"}:
        return "documents"
    return folder


def _split_folder_and_relative_path(text: str) -> tuple[str, str]:
    clean_text = " ".join(text.strip().split())
    lowered = clean_text.lower()
    known_folders = (
        "assistant folder",
        "project folder",
        "downloads folder",
        "documents folder",
        "desktop folder",
        "downloads",
        "documents",
        "desktop",
    )
    for folder in known_folders:
        prefix = f"{folder} "
        if lowered.startswith(prefix):
            return _normalize_folder_name(folder), clean_text[len(prefix) :].strip(" .")
    folder, _, relative_path = clean_text.partition(" ")
    return _normalize_folder_name(folder), relative_path.strip(" .")
