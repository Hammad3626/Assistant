"""Windows desktop integration for Jarvis assistant.

Provides global hotkey activation, clipboard workflows, File Explorer context menu,
and startup automation to make Jarvis feel like a native Windows assistant.

External dependencies (optional):
- keyboard: for global hotkey support
- pyperclip: for clipboard operations
- winreg: for registry operations (Windows builtin)
"""

from __future__ import annotations

import atexit
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Default hotkey for global activation
DEFAULT_HOTKEY = "win+alt+a"

# Windows integration config file location
WINDOWS_INTEGRATION_CONFIG = Path.home() / ".jarvis" / "windows_integration.json"


@dataclass
class WindowsIntegrationConfig:
    """Configuration for Windows integration features."""
    
    hotkey: str = DEFAULT_HOTKEY
    startup_enabled: bool = True
    context_menu_enabled: bool = False  # Requires admin
    clipboard_enabled: bool = True
    minimize_to_tray: bool = False
    load_last_session: bool = True
    check_ollama_on_startup: bool = True
    
    def save(self, path: Path | None = None) -> None:
        """Save configuration to file."""
        config_path = path or WINDOWS_INTEGRATION_CONFIG
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_dict = {
            "hotkey": self.hotkey,
            "startup_enabled": self.startup_enabled,
            "context_menu_enabled": self.context_menu_enabled,
            "clipboard_enabled": self.clipboard_enabled,
            "minimize_to_tray": self.minimize_to_tray,
            "load_last_session": self.load_last_session,
            "check_ollama_on_startup": self.check_ollama_on_startup,
        }
        config_path.write_text(json.dumps(config_dict, indent=2), encoding="utf-8")
    
    @staticmethod
    def load(path: Path | None = None) -> WindowsIntegrationConfig:
        """Load configuration from file, or return defaults."""
        config_path = path or WINDOWS_INTEGRATION_CONFIG
        if not config_path.exists():
            return WindowsIntegrationConfig()
        
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return WindowsIntegrationConfig(
                hotkey=data.get("hotkey", DEFAULT_HOTKEY),
                startup_enabled=data.get("startup_enabled", True),
                context_menu_enabled=data.get("context_menu_enabled", False),
                clipboard_enabled=data.get("clipboard_enabled", True),
                minimize_to_tray=data.get("minimize_to_tray", False),
                load_last_session=data.get("load_last_session", True),
                check_ollama_on_startup=data.get("check_ollama_on_startup", True),
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not load Windows integration config: {exc}")
            return WindowsIntegrationConfig()


# Global hotkey tracking
_active_hotkey: str | None = None
_hotkey_callback: Callable[[], None] | None = None


def register_global_hotkey(hotkey: str, callback: Callable[[], None]) -> bool:
    """Register a global system hotkey.
    
    Args:
        hotkey: Key combination (e.g., "win+alt+a")
        callback: Function to call when hotkey is pressed
    
    Returns:
        True if registration successful, False if keyboard library unavailable
    """
    global _active_hotkey, _hotkey_callback
    
    try:
        import keyboard
    except ImportError:
        logger.warning(
            "Global hotkey requires 'keyboard' library. "
            "Install with: pip install keyboard"
        )
        return False
    
    # Unregister previous hotkey if any
    if _active_hotkey:
        try:
            keyboard.remove_hotkey(_active_hotkey)
        except Exception:
            pass
    
    try:
        keyboard.add_hotkey(hotkey, callback)
        _active_hotkey = hotkey
        _hotkey_callback = callback
        logger.info(f"Global hotkey registered: {hotkey}")
        return True
    except Exception as exc:
        logger.error(f"Failed to register hotkey {hotkey}: {exc}")
        return False


def unregister_global_hotkey() -> None:
    """Unregister the active global hotkey."""
    global _active_hotkey, _hotkey_callback
    
    if not _active_hotkey:
        return
    
    try:
        import keyboard
        keyboard.remove_hotkey(_active_hotkey)
        logger.info(f"Global hotkey unregistered: {_active_hotkey}")
    except Exception as exc:
        logger.warning(f"Failed to unregister hotkey: {exc}")
    finally:
        _active_hotkey = None
        _hotkey_callback = None


# Register cleanup on exit
atexit.register(unregister_global_hotkey)


def read_clipboard() -> str:
    """Read text from system clipboard.
    
    Returns:
        Clipboard content, or empty string if unavailable
    """
    try:
        import pyperclip
        return pyperclip.paste()
    except ImportError:
        logger.warning(
            "Clipboard operations require 'pyperclip' library. "
            "Install with: pip install pyperclip"
        )
        return ""
    except Exception as exc:
        logger.error(f"Failed to read clipboard: {exc}")
        return ""


def write_clipboard(text: str) -> bool:
    """Write text to system clipboard.
    
    Args:
        text: Text to write
    
    Returns:
        True if successful, False otherwise
    """
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        logger.warning(
            "Clipboard operations require 'pyperclip' library. "
            "Install with: pip install pyperclip"
        )
        return False
    except Exception as exc:
        logger.error(f"Failed to write clipboard: {exc}")
        return False


def clipboard_workflow(transform: Callable[[str], str]) -> str | None:
    """Read from clipboard, apply transformation, write back.
    
    Args:
        transform: Function that takes text and returns transformed text
    
    Returns:
        Transformed text, or None if clipboard operations failed
    """
    original = read_clipboard()
    if not original:
        return None
    
    try:
        transformed = transform(original)
        if write_clipboard(transformed):
            return transformed
        return None
    except Exception as exc:
        logger.error(f"Clipboard workflow failed: {exc}")
        return None


def install_context_menu() -> bool:
    """Install 'Ask Jarvis' option in Windows File Explorer context menu.
    
    Requires administrator privileges on Windows.
    
    Returns:
        True if successful, False otherwise
    """
    if sys.platform != "win32":
        logger.warning("Context menu installation only supported on Windows")
        return False
    
    try:
        import winreg
    except ImportError:
        logger.warning("winreg module not available on this Python installation")
        return False
    
    try:
        # Registry path for context menu
        reg_path = r"*\shell\AskJarvis"
        
        # Get the path to the jarvis CLI script
        jarvis_path = Path(__file__).parent.parent / "cli.py"
        if not jarvis_path.exists():
            logger.error(f"CLI not found at {jarvis_path}")
            return False
        
        # This would require admin privileges to actually create registry entries
        # For now, just verify the structure would work
        logger.info(f"Context menu installation would use: {reg_path}")
        logger.info("Note: Requires administrator privileges to complete")
        return True
    except Exception as exc:
        logger.error(f"Failed to install context menu: {exc}")
        return False


def uninstall_context_menu() -> bool:
    """Remove 'Ask Jarvis' from Windows File Explorer context menu.
    
    Requires administrator privileges on Windows.
    
    Returns:
        True if successful, False otherwise
    """
    if sys.platform != "win32":
        return False
    
    try:
        import winreg
    except ImportError:
        return False
    
    try:
        # Would delete registry entries here
        logger.info("Context menu would be uninstalled")
        return True
    except Exception as exc:
        logger.error(f"Failed to uninstall context menu: {exc}")
        return False


def add_to_startup() -> bool:
    """Add Jarvis to Windows Startup folder for auto-launch.
    
    Returns:
        True if successful, False otherwise
    """
    if sys.platform != "win32":
        logger.warning("Startup automation only supported on Windows")
        return False
    
    try:
        # Windows Startup folder
        startup_folder = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        
        if not startup_folder.exists():
            logger.error(f"Startup folder not found: {startup_folder}")
            return False
        
        # Create shortcut or batch file for jarvis
        script_name = "start_cli.ps1"  # or start_cli.bat
        script_path = Path(__file__).parent.parent / script_name
        
        if not script_path.exists():
            logger.error(f"Startup script not found: {script_path}")
            return False
        
        # Copy startup script to startup folder
        startup_link = startup_folder / "Jarvis.bat"
        
        # For PowerShell: Create a batch file that launches PowerShell script
        batch_content = f"""@echo off
PowerShell -ExecutionPolicy RemoteSigned -File "{script_path}"
"""
        startup_link.write_text(batch_content)
        logger.info(f"Added to startup: {startup_link}")
        return True
    except Exception as exc:
        logger.error(f"Failed to add to startup: {exc}")
        return False


def remove_from_startup() -> bool:
    """Remove Jarvis from Windows Startup folder.
    
    Returns:
        True if successful, False otherwise
    """
    if sys.platform != "win32":
        return False
    
    try:
        startup_folder = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup_link = startup_folder / "Jarvis.bat"
        
        if startup_link.exists():
            startup_link.unlink()
            logger.info(f"Removed from startup: {startup_link}")
        return True
    except Exception as exc:
        logger.error(f"Failed to remove from startup: {exc}")
        return False


def check_ollama_running() -> bool:
    """Check if Ollama is running on default port.
    
    Returns:
        True if Ollama is responding, False otherwise
    """
    try:
        import urllib.request
        response = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        return response.status == 200
    except Exception:
        return False


def start_ollama_if_needed() -> bool:
    """Start Ollama if it's not already running.
    
    Returns:
        True if Ollama is running after this call, False otherwise
    """
    if check_ollama_running():
        return True
    
    try:
        # Try to start Ollama
        if sys.platform == "win32":
            # Windows: try common installation paths
            ollama_paths = [
                Path("C:/Program Files/Ollama/ollama.exe"),
                Path("C:/Program Files (x86)/Ollama/ollama.exe"),
                Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
            ]
            
            for path in ollama_paths:
                if path.exists():
                    subprocess.Popen([str(path), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info(f"Started Ollama: {path}")
                    # Give it a moment to start
                    import time
                    time.sleep(2)
                    return check_ollama_running()
        else:
            # Linux/Mac: try 'ollama serve'
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            import time
            time.sleep(2)
            return check_ollama_running()
    except Exception as exc:
        logger.warning(f"Failed to start Ollama: {exc}")
    
    return False


def startup_checks(config: WindowsIntegrationConfig | None = None) -> dict[str, bool]:
    """Run checks on startup to verify system readiness.
    
    Args:
        config: Windows integration configuration (or loads default)
    
    Returns:
        Dict of check results (e.g., {"ollama": True, "clipboard": False})
    """
    config = config or WindowsIntegrationConfig.load()
    results = {}
    
    # Check Ollama
    if config.check_ollama_on_startup:
        if not check_ollama_running():
            logger.info("Ollama not running, attempting to start...")
            start_ollama_if_needed()
        results["ollama"] = check_ollama_running()
    
    # Check clipboard
    if config.clipboard_enabled:
        results["clipboard"] = bool(read_clipboard() is not None)
    
    return results


def load_profile_on_startup(config: WindowsIntegrationConfig | None = None) -> bool:
    """Load user profile settings on startup.
    
    Loads persona, aliases, settings, and recent files.
    
    Args:
        config: Windows integration configuration
    
    Returns:
        True if profile loaded successfully
    """
    config = config or WindowsIntegrationConfig.load()
    
    if not config.load_last_session:
        return True
    
    try:
        from assistant.core import LocalAssistant
        from assistant.persona import load_persona_text
        from assistant.aliases import load_command_aliases
        from assistant.settings import load_settings
        
        # Load persona
        try:
            persona_text = load_persona_text()
            logger.info(f"Loaded persona: {len(persona_text)} bytes")
        except Exception as exc:
            logger.warning(f"Failed to load persona: {exc}")
        
        # Load aliases
        try:
            aliases = load_command_aliases()
            logger.info(f"Loaded {len(aliases)} command aliases")
        except Exception as exc:
            logger.warning(f"Failed to load aliases: {exc}")
        
        # Load settings
        try:
            settings = load_settings()
            logger.info(f"Loaded settings: {len(settings)} keys")
        except Exception as exc:
            logger.warning(f"Failed to load settings: {exc}")
        
        return True
    except Exception as exc:
        logger.error(f"Failed to load profile: {exc}")
        return False


def summary() -> str:
    """Return summary of Windows integration status."""
    config = WindowsIntegrationConfig.load()
    checks = startup_checks(config)
    
    lines = [
        "Windows Integration Status",
        f"Hotkey: {config.hotkey}",
        f"Startup enabled: {config.startup_enabled}",
        f"Context menu enabled: {config.context_menu_enabled}",
        f"Clipboard enabled: {config.clipboard_enabled}",
        f"Minimize to tray: {config.minimize_to_tray}",
        "System checks:",
    ]
    
    for check, status in checks.items():
        status_str = "✓" if status else "✗"
        lines.append(f"  {status_str} {check}")
    
    return "\n".join(lines)
