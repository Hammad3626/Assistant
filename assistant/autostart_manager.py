"""Auto-start verification and management for the assistant.

Checks if the assistant is set to launch on Windows startup,
and provides functionality to enable/disable auto-start.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from assistant.windows_integration import WindowsIntegrationConfig


@dataclass
class AutoStartStatus:
    """Status of auto-start configuration."""
    
    enabled: bool  # Whether auto-start is enabled
    cli_shortcut_exists: bool  # CLI batch file in Startup
    gui_shortcut_exists: bool  # GUI batch file in Startup
    voice_shortcut_exists: bool  # Voice batch file in Startup
    startup_folder: Optional[Path] = None  # Windows Startup folder path
    startup_files: list[str] = None  # List of found startup files
    
    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.startup_files is None:
            self.startup_files = []


class AutoStartManager:
    """Manages auto-start configuration for the assistant."""
    
    # Standard Windows Startup folder location
    STARTUP_FOLDER = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    
    # Batch files we expect
    BATCH_FILES = {
        "cli": "start_cli.bat",
        "gui": "start_gui.bat",
        "voice": "start_voice.bat",
    }

    @staticmethod
    def get_startup_folder() -> Optional[Path]:
        """Get Windows Startup folder path.
        
        Returns:
            Path to Startup folder if it exists, None otherwise
        """
        if AutoStartManager.STARTUP_FOLDER.exists():
            return AutoStartManager.STARTUP_FOLDER
        return None

    @staticmethod
    def check_status() -> AutoStartStatus:
        """Check current auto-start status.
        
        Returns:
            AutoStartStatus with current configuration
        """
        startup_folder = AutoStartManager.get_startup_folder()
        
        if not startup_folder:
            return AutoStartStatus(
                enabled=False,
                cli_shortcut_exists=False,
                gui_shortcut_exists=False,
                voice_shortcut_exists=False,
                startup_folder=None,
                startup_files=[],
            )
        
        # Check for batch files
        startup_files = []
        cli_exists = False
        gui_exists = False
        voice_exists = False
        
        for file_type, filename in AutoStartManager.BATCH_FILES.items():
            batch_path = startup_folder / filename
            exists = batch_path.exists()
            
            if exists:
                startup_files.append(filename)
                if file_type == "cli":
                    cli_exists = True
                elif file_type == "gui":
                    gui_exists = True
                elif file_type == "voice":
                    voice_exists = True
        
        # Auto-start is enabled if at least one batch file exists
        enabled = cli_exists or gui_exists or voice_exists
        
        return AutoStartStatus(
            enabled=enabled,
            cli_shortcut_exists=cli_exists,
            gui_shortcut_exists=gui_exists,
            voice_shortcut_exists=voice_exists,
            startup_folder=startup_folder,
            startup_files=startup_files,
        )

    @staticmethod
    def get_status_report(status: Optional[AutoStartStatus] = None) -> str:
        """Get human-readable auto-start status report.
        
        Args:
            status: AutoStartStatus (checks current if not provided)
            
        Returns:
            Human-readable status string
        """
        if not status:
            status = AutoStartManager.check_status()
        
        if not status.enabled:
            return "Auto-start is not enabled. The assistant will not launch on system startup."
        
        # Build detailed report
        parts = ["Auto-start is enabled with the following:"]
        
        if status.cli_shortcut_exists:
            parts.append("• CLI mode will start on boot")
        if status.gui_shortcut_exists:
            parts.append("• GUI mode will start on boot")
        if status.voice_shortcut_exists:
            parts.append("• Voice mode will start on boot")
        
        if status.startup_folder:
            parts.append(f"• Startup folder: {status.startup_folder}")
        
        return "\n".join(parts)

    @staticmethod
    def enable_autostart(
        cli: bool = False,
        gui: bool = False,
        voice: bool = False,
        project_root: Optional[Path] = None,
    ) -> dict[str, bool | str]:
        """Enable auto-start by copying batch files to Startup folder.
        
        At least one mode must be True.
        
        Args:
            cli: Enable CLI mode auto-start
            gui: Enable GUI mode auto-start
            voice: Enable Voice mode auto-start
            project_root: Root directory of project (detects if None)
            
        Returns:
            Dictionary with success status and details
        """
        result = {
            "success": False,
            "enabled_modes": [],
            "errors": [],
        }
        
        if not (cli or gui or voice):
            result["errors"].append("At least one mode must be enabled")
            return result
        
        # Detect project root if not provided
        if not project_root:
            project_root = Path(__file__).parent.parent
        
        startup_folder = AutoStartManager.get_startup_folder()
        if not startup_folder:
            result["errors"].append("Windows Startup folder not found")
            return result
        
        # Copy batch files
        modes = {
            "CLI": (cli, "start_cli.bat"),
            "GUI": (gui, "start_gui.bat"),
            "Voice": (voice, "start_voice.bat"),
        }
        
        for mode_name, (enabled, filename) in modes.items():
            if not enabled:
                continue
            
            try:
                source = project_root / filename
                dest = startup_folder / filename
                
                if not source.exists():
                    result["errors"].append(f"Source batch file not found: {source}")
                    continue
                
                # Copy file
                import shutil
                shutil.copy2(source, dest)
                result["enabled_modes"].append(mode_name)
            
            except Exception as e:
                result["errors"].append(f"Failed to enable {mode_name}: {str(e)}")
        
        result["success"] = len(result["enabled_modes"]) > 0
        return result

    @staticmethod
    def disable_autostart(
        cli: bool = False,
        gui: bool = False,
        voice: bool = False,
        all_modes: bool = False,
    ) -> dict[str, bool | str]:
        """Disable auto-start by removing batch files from Startup folder.
        
        Args:
            cli: Disable CLI mode auto-start
            gui: Disable GUI mode auto-start
            voice: Disable Voice mode auto-start
            all_modes: Disable all modes at once
            
        Returns:
            Dictionary with success status and details
        """
        result = {
            "success": False,
            "disabled_modes": [],
            "errors": [],
        }
        
        startup_folder = AutoStartManager.get_startup_folder()
        if not startup_folder:
            result["errors"].append("Windows Startup folder not found")
            return result
        
        if all_modes:
            cli = gui = voice = True
        
        if not (cli or gui or voice):
            result["errors"].append("At least one mode must be disabled, or use all_modes=True")
            return result
        
        # Remove batch files
        modes = {
            "CLI": (cli, "start_cli.bat"),
            "GUI": (gui, "start_gui.bat"),
            "Voice": (voice, "start_voice.bat"),
        }
        
        for mode_name, (enabled, filename) in modes.items():
            if not enabled:
                continue
            
            try:
                batch_path = startup_folder / filename
                
                if batch_path.exists():
                    batch_path.unlink()
                
                # Mark as disabled whether file existed or not (it's now disabled)
                result["disabled_modes"].append(mode_name)
            
            except Exception as e:
                result["errors"].append(f"Failed to disable {mode_name}: {str(e)}")
        
        result["success"] = len(result["disabled_modes"]) > 0
        return result

    @staticmethod
    def print_status() -> None:
        """Print auto-start status to console."""
        status = AutoStartManager.check_status()
        report = AutoStartManager.get_status_report(status)
        print(report)
