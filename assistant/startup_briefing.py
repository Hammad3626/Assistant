"""Voice-based startup briefing system for the assistant.

Greets the user when the system starts and provides daily information.
Integrates with voice output and can read tasks, weather, and other info.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from assistant.voice_output import speak, VoiceOutputConfig, VoiceOutputError


class StartupBriefing:
    """Generates and delivers voice briefings on startup."""

    def __init__(
        self,
        config: Optional[VoiceOutputConfig] = None,
        enable_voice: bool = True,
    ) -> None:
        """Initialize startup briefing system.

        Args:
            config: Voice output configuration
            enable_voice: Whether to speak briefing aloud
        """
        self.config = config or VoiceOutputConfig()
        self.enable_voice = enable_voice

    def get_greeting(self) -> str:
        """Get time-appropriate greeting."""
        now = datetime.now(UTC).hour
        
        if 5 <= now < 12:
            return "Good morning!"
        elif 12 <= now < 17:
            return "Good afternoon!"
        elif 17 <= now < 21:
            return "Good evening!"
        else:
            return "Hello there!"

    def get_time_info(self) -> str:
        """Get current time information."""
        now = datetime.now(UTC)
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        
        return f"It's {day_name}, {date_str}, {time_str}."

    def get_tasks_info(self, tasks_path: Path | None = None) -> str:
        """Get pending tasks information."""
        if not tasks_path or not tasks_path.exists():
            return "You have no tasks scheduled for today."
        
        try:
            import json
            content = tasks_path.read_text(encoding="utf-8")
            if not content.strip():
                return "You have no tasks scheduled for today."
            
            tasks_data = json.loads(content)
            if not tasks_data or not tasks_data.get("tasks"):
                return "You have no tasks scheduled for today."
            
            tasks = tasks_data.get("tasks", [])
            # Count incomplete tasks
            incomplete = [t for t in tasks if not t.get("completed", False)]
            
            if not incomplete:
                return "All tasks are completed! Great job."
            
            count = len(incomplete)
            if count == 1:
                return "You have one task for today."
            else:
                return f"You have {count} tasks for today."
        except Exception:
            return "Could not load task information."

    def get_system_status(self, ollama_available: bool = True) -> str:
        """Get system status information."""
        statuses = []
        
        if ollama_available:
            statuses.append("Ollama is running and ready")
        else:
            statuses.append("Ollama is not currently running")
        
        if statuses:
            return ". ".join(statuses) + "."
        
        return "System is ready."

    def generate_briefing(
        self,
        include_greeting: bool = True,
        include_time: bool = True,
        include_tasks: bool = True,
        include_status: bool = True,
        tasks_path: Optional[Path] = None,
        ollama_available: bool = True,
    ) -> str:
        """Generate complete startup briefing.

        Args:
            include_greeting: Include time-appropriate greeting
            include_time: Include current date and time
            include_tasks: Include task information
            include_status: Include system status
            tasks_path: Path to tasks file
            ollama_available: Whether Ollama service is available

        Returns:
            Complete briefing text
        """
        parts = []
        
        if include_greeting:
            parts.append(self.get_greeting())
        
        if include_time:
            parts.append(self.get_time_info())
        
        if include_tasks and tasks_path:
            parts.append(self.get_tasks_info(tasks_path))
        
        if include_status:
            parts.append(self.get_system_status(ollama_available))
        
        # Add closing message
        parts.append("I'm ready to help. You can wake me with the hotkey or speak a command.")
        
        return " ".join(parts)

    def deliver_briefing(
        self,
        briefing_text: Optional[str] = None,
        **kwargs,
    ) -> dict[str, bool | str]:
        """Deliver briefing via voice and return result.

        Args:
            briefing_text: Custom briefing text (generates if not provided)
            **kwargs: Arguments to generate_briefing()

        Returns:
            Dictionary with delivery status
        """
        result = {
            "success": False,
            "text": "",
            "error": None,
        }
        
        try:
            # Generate briefing if not provided
            if not briefing_text:
                briefing_text = self.generate_briefing(**kwargs)
            
            result["text"] = briefing_text
            
            # Deliver via voice if enabled
            if self.enable_voice:
                try:
                    speak(briefing_text, self.config)
                    result["success"] = True
                except VoiceOutputError as e:
                    result["error"] = f"Voice delivery failed: {str(e)}"
                    result["success"] = False
            else:
                result["success"] = True
            
            return result
        
        except Exception as e:
            result["error"] = f"Briefing failed: {str(e)}"
            return result

    @staticmethod
    def is_first_startup_today(last_startup_path: Path | None = None) -> bool:
        """Check if this is the first startup today.

        Args:
            last_startup_path: Path to file tracking last startup

        Returns:
            True if first startup today, False otherwise
        """
        if not last_startup_path or not last_startup_path.exists():
            return True
        
        try:
            import json
            from datetime import date
            
            content = last_startup_path.read_text(encoding="utf-8")
            data = json.loads(content)
            
            last_date_str = data.get("date")
            if not last_date_str:
                return True
            
            last_date = datetime.fromisoformat(last_date_str).date()
            today = date.today()
            
            return last_date < today
        except Exception:
            return True

    @staticmethod
    def record_startup(startup_path: Path | None = None) -> bool:
        """Record startup time for briefing detection.

        Args:
            startup_path: Path to store startup record

        Returns:
            True if recorded successfully
        """
        if not startup_path:
            startup_path = Path.home() / ".jarvis" / "startup_record.json"
        
        try:
            import json
            
            startup_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "date": datetime.now(UTC).date().isoformat(),
            }
            
            startup_path.write_text(json.dumps(data), encoding="utf-8")
            return True
        except Exception:
            return False


class StartupBriefingConfig:
    """Configuration for startup briefing."""
    
    def __init__(self):
        self.enable_briefing = True
        self.enable_voice = True
        self.include_greeting = True
        self.include_time = True
        self.include_tasks = True
        self.include_status = True
        self.only_first_startup = True  # Only brief on first startup each day
        self.tasks_file = Path.home() / ".jarvis" / "tasks.json"
        self.startup_record_file = Path.home() / ".jarvis" / "startup_record.json"
        self.voice_config = VoiceOutputConfig(rate=0, volume=100)
