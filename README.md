# Local PC Assistant

An offline-first Python desktop assistant for Windows, built in small testable milestones.

## Milestone Plan

1. Environment setup
2. Basic command-line assistant
3. Local LLM integration
4. Voice input
5. Voice output
6. Local file/app control
7. Memory and settings
8. User interactive GUI

## Project Layout

```text
local_pc_assistant/
  assistant/
    __init__.py
    cli.py
    core.py
  scripts/
    check_env.py
    check_ollama.py
    check_voice.py
    listen_once.py
    speak_once.py
  tests/
    test_core.py
  pyproject.toml
```

The project starts with no required third-party packages. Later milestones will add dependencies only when needed.

## Run The CLI

```powershell
python -m assistant.cli
```

Try:

```text
hello
time
date
help
exit
```

To run without the local LLM:

```powershell
python -m assistant.cli --no-llm
```

To use a different installed Ollama model:

```powershell
python -m assistant.cli --model llama3:latest
```

By default, the assistant asks Ollama to run CPU-only. On mixed-GPU Windows PCs
this is slower, but easier to debug. You can opt into GPU offload later:

```powershell
python -m assistant.cli --model smollm2:135m --num-gpu 10
```

## Check Ollama

```powershell
python scripts/check_ollama.py
```

Try another installed model:

```powershell
python scripts/check_ollama.py --model llama3:latest
```

The health check is CPU-only by default:

```powershell
python scripts/check_ollama.py --model smollm2:135m --num-gpu 0
```

## Voice Input

Voice input is optional and offline-first. It uses Vosk plus a local speech
model.

Install voice dependencies:

```powershell
python -m pip install -e ".[voice]"
```

Check microphone and model setup:

```powershell
python scripts/check_voice.py
```

Test one spoken phrase:

```powershell
python scripts/listen_once.py --timeout 10
```

Run with voice input:

```powershell
python -m assistant.cli --model smollm2:135m --num-gpu 0 --voice
```

## Voice Output

Voice output uses Windows built-in text-to-speech and works offline.

Test one spoken phrase:

```powershell
python scripts/speak_once.py "Hello. Voice output is working."
```

Run the assistant with spoken responses:

```powershell
python -m assistant.cli --model smollm2:135m --num-gpu 0 --speak
```

Run with both voice input and output:

```powershell
python -m assistant.cli --model smollm2:135m --num-gpu 0 --voice --speak --voice-timeout 10
```

## Wake Voice Loop

Wake voice mode is optional. It keeps listening locally with Vosk, ignores
phrases without the wake phrase, and runs the command after the wake phrase.
Existing confirmations still apply.

Check the wake-loop parser without recording audio:

```powershell
python scripts/check_wake_voice.py
```

Run wake mode:

```powershell
python -m assistant.cli --model smollm2:135m --num-gpu 0 --wake --speak --voice-timeout 10
```

Try saying:

```text
hey eva hello
hey eva
time
hey eva exit
```

If you say only `hey eva`, the assistant listens once more for the command.
Use `Ctrl+C` to stop the loop from the terminal.

## Safe Local Actions

The assistant can prepare a small set of allowlisted local actions. It asks for
confirmation before launching apps or opening folders.

List allowed actions:

```text
actions
```

Examples:

```text
open calculator
yes
open notepad
yes
open chrome
yes
open C drive
yes
open this pc
yes
open settings
yes
open downloads
yes
```

It does not run raw arbitrary shell commands, permanently delete files, send
messages/emails, make network requests, or bulk-edit files in this milestone.
Named safe shell commands are available through the local allowlist and still
require confirmation. Individual text files in allowlisted folders can be moved
to assistant trash and restored.

## Local Draft Outbox

The assistant can create local-only drafts for messages, emails, and network
requests. It does not send the draft or contact the network.

Create drafts:

```text
draft message to Alex: running late
draft email to alex@example.com subject Hello: quick local note
draft network request GET https://example.com health check
```

Review drafts:

```text
outbox
drafts
```

Direct sending commands are blocked:

```text
send message to Alex: hello
```

Drafts are stored at `data/outbox.json` by default and are included in data
reports, exports, status, and the GUI startup dashboard.

## Safe File Trash

File deletion is reversible. The assistant can move individual common text files
from allowlisted folders into assistant trash:

```text
delete file in project folder notes/example.txt
yes
```

Review and restore:

```text
file trash
restore file 1
```

The assistant blocks permanent deletion, path traversal outside allowlisted
folders, non-text files, assistant trash internals, and bulk file modification.

## Safe Shell Commands

Shell command support is intentionally narrow. The assistant can run only named
commands from:

```text
config/shell_commands.json
```

List allowed shell commands:

```text
shell commands
```

Run one with confirmation:

```text
run shell python version
yes
```

Raw shell text, `cmd.exe`, PowerShell, pipelines, redirection, command chaining,
scripts, and destructive commands are blocked.

## Unlisted Open Requests

Unlisted apps, scripts, files, documents, and folders do not open automatically.
Instead, the assistant can save local review requests so you can decide later
whether to manually add a trusted target to an allowlist or supported workflow.

Create review requests:

```text
request app paint: mspaint.exe
request script review cleanup: tools/cleanup.py
request file review report: C:\Users\You\Documents\report.pdf
request folder review archive: C:\Users\You\Documents\Archive
```

Review requests:

```text
launch requests
```

Blocked launch attempts show guidance and do not create a request automatically:

```text
open mystery app
run script tools/cleanup.py
open C:\Users\You\Documents\report.pdf
```

Requests are stored locally in `data/launch_requests.json`. They do not edit
`config/apps.json` or `config/folders.json`, do not run scripts, do not open
documents, and do not bypass confirmation.

## Settings

Default settings live in:

```text
config/settings.json
```

Check settings:

```powershell
python scripts/check_settings.py
```

Run with saved defaults:

```powershell
python -m assistant.cli
```

Override a setting for one run:

```powershell
python -m assistant.cli --model smollm2:135m --num-gpu 0 --voice --speak
```

Inside the assistant, type:

```text
settings
```

## GUI

The GUI uses Python tkinter, loads the same local settings, and keeps action confirmation enabled.

Check GUI support:

```powershell
python scripts/check_gui.py
```

Run the GUI:

```powershell
python -m assistant.gui
```

Run the GUI without the LLM for quick local command testing:

```powershell
python -m assistant.gui --no-llm
```

Try these in the GUI:

```text
hello
actions
open calculator
```

For local actions, use the Confirm or Cancel button after the assistant asks.

The GUI menu also includes quick local views for settings, allowed actions,
memories, outbox, history, and action audit. Use Assistant > Clear Transcript
to clear only the visible chat area; it does not delete saved history or memory.

Use Assistant > Edit Settings to update common local settings such as assistant
name, default model, LLM mode, voice input, voice output, history, and action
audit. Settings are saved to `config/settings.json`. Restart the assistant after
changing model, voice, or storage settings.

Use Assistant > Status for a read-only dashboard covering settings, local data
counts, allowlist counts, and Ollama reachability.

You can also print the same status in the terminal:

```powershell
python scripts/status.py
```

## Local Model Management

List installed local Ollama models:

```powershell
python scripts/models.py
```

Set the assistant's default model only if it is already installed:

```powershell
python scripts/models.py --set-default smollm2:135m --num-gpu 0
```

This does not download models. Use `ollama pull ...` separately if you choose
to install a new model.

## Configurable Persona

The local LLM persona lives in:

```text
config/persona.txt
```

Check it:

```powershell
python scripts/check_persona.py
```

You can edit the persona text to change tone or response style. Safety rules
are appended by code and are not removed by editing this file.

## Daily Use

Run a full non-interactive health check:

```powershell
python scripts/check_all.py
```

Launch the GUI:

```powershell
.\start_gui.ps1
```

Launch the CLI:

```powershell
.\start_cli.ps1
```

Launch voice input plus voice output using saved settings:

```powershell
.\start_voice.ps1
```

If PowerShell blocks a launcher script, run the module command directly instead:

```powershell
python -m assistant.gui
python -m assistant.cli
python -m assistant.cli --voice --speak
```

## Windows Launchers

If PowerShell blocks `.ps1` files, use the batch launchers instead:

```powershell
.\start_gui.bat
.\start_cli.bat
.\start_voice.bat
```

Create Desktop batch launchers:

```powershell
python scripts/create_desktop_launchers.py
```

This creates:

```text
Local Assistant GUI.bat
Local Assistant CLI.bat
Local Assistant Voice.bat
```

The launchers still use the same settings and the same confirmation rules for local actions.

## Explicit Local Memory

Memory is local and opt-in. The assistant only saves something when you use `remember`.

```text
remember I prefer short answers
memories
forget memories
```

Memory is stored in:

```text
data/memory.json
```

Check memory:

```powershell
python scripts/check_memory.py
```

The `data/` folder is ignored by git so personal memories are not accidentally committed.

## Memory-Aware Local LLM

Saved memories are passed to the local Ollama prompt as context for open-ended questions.
Built-in commands still run without the LLM.

Example:

```text
remember I prefer short answers
how should you answer me?
```

Use `memories` to inspect what will be available as context, and `forget memories` to clear it.

## Safe Settings Updates

Use the GUI settings panel or the settings updater instead of hand-editing JSON:

```powershell
python scripts/update_settings.py --show
python scripts/update_settings.py --list-keys
python scripts/update_settings.py --set assistant_name=Friday
python scripts/update_settings.py --set voice_enabled=true --set speak_enabled=true
```

Settings are validated by type. Unknown keys are rejected.

## Local Conversation History

Conversation history is stored locally as JSONL when `history_enabled` is true.

```text
history
clear history
```

History is stored in:

```text
data/history.jsonl
```

Check history:

```powershell
python scripts/check_history.py
```

Disable history:

```powershell
python scripts/update_settings.py --set history_enabled=false
```

## Local Data Management

Report local data counts:

```powershell
python scripts/data_report.py
```

Export memory and history to a timestamped folder under `exports/`:

```powershell
python scripts/export_data.py
```

Clear history only:

```powershell
python scripts/clear_data.py --history --yes
```

Clear action audit only:

```powershell
python scripts/clear_data.py --action-audit --yes
```

Clear explicit memories only:

```powershell
python scripts/clear_data.py --memory --yes
```

Clear memory, history, and action audit:

```powershell
python scripts/clear_data.py --all --yes
```

The clear script refuses to run without `--yes` and only touches the configured memory/history files.

## Local Action Audit

Confirmed, failed, and cancelled local actions are logged locally in:

```text
data/action_audit.jsonl
```

Inspect the audit log:

```text
action audit
```

Check audit storage:

```powershell
python scripts/check_audit.py
```

Disable action audit logging:

```powershell
python scripts/update_settings.py --set action_audit_enabled=false
```

## Configurable App Allowlist

Safe app launches are configured in:

```text
config/apps.json
```

Check allowed apps:

```powershell
python scripts/check_apps.py
python scripts/update_apps.py --show
```

Add a trusted `.exe` target:

```powershell
python scripts/update_apps.py --add paint mspaint.exe
```

Then use it in the assistant:

```text
open paint
yes
```

The validator rejects shell executables such as `powershell.exe` and `cmd.exe`, and app launches still require confirmation.

Chrome is configured as `chrome.exe` by default. If Windows cannot find it when
confirmed, update the app allowlist to the full Chrome path with
`scripts/update_apps.py --add chrome "<path-to-chrome.exe>"`.

## Configurable Folder Allowlist

Safe folder openings are configured in:

```text
config/folders.json
```

Check allowed folders:

```powershell
python scripts/check_folders.py
python scripts/update_folders.py --show
```

Add an existing trusted folder:

```powershell
python scripts/update_folders.py --add desktop "%USERPROFILE%\Desktop"
```

Then use it in the assistant:

```text
open desktop
yes
```

Folder paths must already exist, must be directories, and cannot contain shell control characters. Folder openings still require confirmation.

## Windows Folder And Drive Detection

The assistant can detect common Windows folders and mounted drive roots without
changing any allowlists.

Run read-only detection:

```text
detected folders
detected drives
detected locations
```

You can also check it from PowerShell:

```powershell
python scripts/check_windows_detection.py
```

Detection does not open folders, does not scan file contents, and does not edit
`config/folders.json`. To trust a detected folder, add it manually with
`scripts/update_folders.py --add`.
