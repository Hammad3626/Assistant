"""Comprehensive tests for startup briefing system."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from assistant.startup_briefing import (
    StartupBriefing,
    StartupBriefingConfig,
)


class GreetingTests(unittest.TestCase):
    """Tests for greeting generation."""

    def test_morning_greeting(self):
        """Morning hours receive morning greeting."""
        briefing = StartupBriefing()
        
        with patch('assistant.startup_briefing.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 9
            greeting = briefing.get_greeting()
            self.assertEqual(greeting, "Good morning!")

    def test_afternoon_greeting(self):
        """Afternoon hours receive afternoon greeting."""
        briefing = StartupBriefing()
        
        with patch('assistant.startup_briefing.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 14
            greeting = briefing.get_greeting()
            self.assertEqual(greeting, "Good afternoon!")

    def test_evening_greeting(self):
        """Evening hours receive evening greeting."""
        briefing = StartupBriefing()
        
        with patch('assistant.startup_briefing.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 18
            greeting = briefing.get_greeting()
            self.assertEqual(greeting, "Good evening!")

    def test_night_greeting(self):
        """Night hours receive generic greeting."""
        briefing = StartupBriefing()
        
        with patch('assistant.startup_briefing.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 2
            greeting = briefing.get_greeting()
            self.assertEqual(greeting, "Hello there!")


class TimeInfoTests(unittest.TestCase):
    """Tests for time information."""

    def test_get_time_info(self):
        """Time info includes day, date, and time."""
        briefing = StartupBriefing()
        
        with patch('assistant.startup_briefing.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.strftime.side_effect = lambda fmt: {
                "%A": "Monday",
                "%B %d, %Y": "August 03, 2026",
                "%I:%M %p": "09:30 AM",
            }.get(fmt, "")
            mock_dt.now.return_value = mock_now
            
            time_info = briefing.get_time_info()
            
            self.assertIn("Monday", time_info)
            self.assertIn("August 03, 2026", time_info)
            self.assertIn("09:30 AM", time_info)


class TasksInfoTests(unittest.TestCase):
    """Tests for tasks information."""

    def test_tasks_file_not_found(self):
        """Missing tasks file returns default message."""
        briefing = StartupBriefing()
        
        result = briefing.get_tasks_info(Path("/nonexistent/tasks.json"))
        
        self.assertIn("no tasks", result.lower())

    def test_empty_tasks_file(self):
        """Empty tasks file returns default message."""
        briefing = StartupBriefing()
        
        with TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.json"
            tasks_file.write_text("", encoding="utf-8")
            
            result = briefing.get_tasks_info(tasks_file)
            
            self.assertIn("no tasks", result.lower())

    def test_tasks_with_completed_items(self):
        """All completed tasks returns success message."""
        briefing = StartupBriefing()
        
        with TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.json"
            tasks_data = {
                "tasks": [
                    {"name": "Task 1", "completed": True},
                    {"name": "Task 2", "completed": True},
                ]
            }
            tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")
            
            result = briefing.get_tasks_info(tasks_file)
            
            self.assertIn("completed", result.lower())

    def test_tasks_with_incomplete_items(self):
        """Incomplete tasks returns count."""
        briefing = StartupBriefing()
        
        with TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.json"
            tasks_data = {
                "tasks": [
                    {"name": "Task 1", "completed": False},
                    {"name": "Task 2", "completed": False},
                    {"name": "Task 3", "completed": True},
                ]
            }
            tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")
            
            result = briefing.get_tasks_info(tasks_file)
            
            self.assertIn("2", result)

    def test_single_incomplete_task(self):
        """Single incomplete task returns singular form."""
        briefing = StartupBriefing()
        
        with TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.json"
            tasks_data = {"tasks": [{"name": "Task 1", "completed": False}]}
            tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")
            
            result = briefing.get_tasks_info(tasks_file)
            
            self.assertIn("one task", result.lower())


class SystemStatusTests(unittest.TestCase):
    """Tests for system status information."""

    def test_ollama_available(self):
        """Status when Ollama is available."""
        briefing = StartupBriefing()
        
        status = briefing.get_system_status(ollama_available=True)
        
        self.assertIn("running", status.lower())

    def test_ollama_unavailable(self):
        """Status when Ollama is unavailable."""
        briefing = StartupBriefing()
        
        status = briefing.get_system_status(ollama_available=False)
        
        self.assertIn("not", status.lower())


class BriefingGenerationTests(unittest.TestCase):
    """Tests for complete briefing generation."""

    def test_generate_full_briefing(self):
        """Full briefing includes all components."""
        briefing = StartupBriefing()
        
        with patch('assistant.startup_briefing.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 10
            mock_now.strftime.side_effect = lambda fmt: {
                "%A": "Monday",
                "%B %d, %Y": "August 03, 2026",
                "%I:%M %p": "10:00 AM",
            }.get(fmt, "")
            mock_dt.now.return_value = mock_now
            
            full_briefing = briefing.generate_briefing(
                include_greeting=True,
                include_time=True,
                include_tasks=False,
                include_status=True,
                ollama_available=True,
            )
            
            self.assertIn("Good morning", full_briefing)
            self.assertIn("Monday", full_briefing)
            self.assertIn("running", full_briefing.lower())
            self.assertIn("ready", full_briefing.lower())

    def test_briefing_without_greeting(self):
        """Briefing can exclude greeting."""
        briefing = StartupBriefing()
        
        full_briefing = briefing.generate_briefing(
            include_greeting=False,
            include_time=False,
            include_tasks=False,
            include_status=False,
        )
        
        self.assertNotIn("Good", full_briefing)

    def test_briefing_with_tasks(self):
        """Briefing includes task information when available."""
        briefing = StartupBriefing()
        
        with TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.json"
            tasks_data = {
                "tasks": [
                    {"name": "Task 1", "completed": False},
                    {"name": "Task 2", "completed": False},
                ]
            }
            tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")
            
            full_briefing = briefing.generate_briefing(
                include_greeting=False,
                include_time=False,
                include_tasks=True,
                include_status=False,
                tasks_path=tasks_file,
            )
            
            self.assertIn("2", full_briefing)


class BriefingDeliveryTests(unittest.TestCase):
    """Tests for briefing delivery."""

    @patch('assistant.startup_briefing.speak')
    def test_deliver_briefing_with_voice(self, mock_speak):
        """Briefing delivered via voice when enabled."""
        briefing = StartupBriefing(enable_voice=True)
        
        result = briefing.deliver_briefing(briefing_text="Test briefing")
        
        self.assertTrue(result["success"])
        self.assertEqual(result["text"], "Test briefing")
        mock_speak.assert_called_once()

    @patch('assistant.startup_briefing.speak')
    def test_deliver_briefing_without_voice(self, mock_speak):
        """Briefing not delivered via voice when disabled."""
        briefing = StartupBriefing(enable_voice=False)
        
        result = briefing.deliver_briefing(briefing_text="Test briefing")
        
        self.assertTrue(result["success"])
        mock_speak.assert_not_called()

    @patch('assistant.startup_briefing.speak')
    def test_deliver_briefing_voice_error(self, mock_speak):
        """Briefing handles voice delivery errors."""
        from assistant.voice_output import VoiceOutputError
        
        mock_speak.side_effect = VoiceOutputError("Speech failed")
        briefing = StartupBriefing(enable_voice=True)
        
        result = briefing.deliver_briefing(briefing_text="Test briefing")
        
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])

    @patch('assistant.startup_briefing.datetime')
    def test_deliver_briefing_generates_if_needed(self, mock_dt):
        """Briefing is generated if not provided."""
        mock_now = MagicMock()
        mock_now.hour = 10
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Monday",
            "%B %d, %Y": "August 03, 2026",
            "%I:%M %p": "10:00 AM",
        }.get(fmt, "")
        mock_dt.now.return_value = mock_now
        
        with patch('assistant.startup_briefing.speak'):
            briefing = StartupBriefing(enable_voice=False)
            result = briefing.deliver_briefing()
            
            self.assertTrue(result["success"])
            self.assertIn("Good morning", result["text"])


class StartupDetectionTests(unittest.TestCase):
    """Tests for detecting first startup of the day."""

    def test_first_startup_no_record(self):
        """First startup when no record exists."""
        is_first = StartupBriefing.is_first_startup_today(Path("/nonexistent.json"))
        
        self.assertTrue(is_first)

    def test_first_startup_today(self):
        """First startup today when record is from yesterday."""
        with TemporaryDirectory() as temp_dir:
            record_file = Path(temp_dir) / "startup.json"
            yesterday = datetime.now(UTC) - timedelta(days=1)
            data = {
                "timestamp": yesterday.isoformat(),
                "date": yesterday.date().isoformat(),
            }
            record_file.write_text(json.dumps(data), encoding="utf-8")
            
            is_first = StartupBriefing.is_first_startup_today(record_file)
            
            self.assertTrue(is_first)

    def test_not_first_startup_today(self):
        """Not first startup when record is from today."""
        with TemporaryDirectory() as temp_dir:
            record_file = Path(temp_dir) / "startup.json"
            now = datetime.now(UTC)
            data = {
                "timestamp": now.isoformat(),
                "date": now.date().isoformat(),
            }
            record_file.write_text(json.dumps(data), encoding="utf-8")
            
            is_first = StartupBriefing.is_first_startup_today(record_file)
            
            self.assertFalse(is_first)


class StartupRecordingTests(unittest.TestCase):
    """Tests for recording startup."""

    def test_record_startup(self):
        """Startup record is created successfully."""
        with TemporaryDirectory() as temp_dir:
            record_file = Path(temp_dir) / "startup.json"
            
            success = StartupBriefing.record_startup(record_file)
            
            self.assertTrue(success)
            self.assertTrue(record_file.exists())
            
            data = json.loads(record_file.read_text(encoding="utf-8"))
            self.assertIn("timestamp", data)
            self.assertIn("date", data)

    def test_record_startup_creates_directory(self):
        """Record startup creates necessary directories."""
        with TemporaryDirectory() as temp_dir:
            record_file = Path(temp_dir) / "nested" / "dir" / "startup.json"
            
            success = StartupBriefing.record_startup(record_file)
            
            self.assertTrue(success)
            self.assertTrue(record_file.exists())


class ConfigurationTests(unittest.TestCase):
    """Tests for briefing configuration."""

    def test_config_creation(self):
        """Configuration can be created with defaults."""
        config = StartupBriefingConfig()
        
        self.assertTrue(config.enable_briefing)
        self.assertTrue(config.enable_voice)
        self.assertTrue(config.include_greeting)
        self.assertIsNotNone(config.voice_config)

    def test_config_customization(self):
        """Configuration can be customized."""
        config = StartupBriefingConfig()
        config.enable_voice = False
        config.include_greeting = False
        
        self.assertFalse(config.enable_voice)
        self.assertFalse(config.include_greeting)


class IntegrationTests(unittest.TestCase):
    """Integration tests for startup briefing."""

    @patch('assistant.startup_briefing.speak')
    @patch('assistant.startup_briefing.datetime')
    def test_full_startup_cycle(self, mock_dt, mock_speak):
        """Complete startup cycle with briefing."""
        # Setup datetime mock for briefing generation
        mock_now = MagicMock()
        mock_now.hour = 9
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Monday",
            "%B %d, %Y": "August 03, 2026",
            "%I:%M %p": "09:30 AM",
        }.get(fmt, "")
        
        # Setup date mock for record_startup
        mock_date_obj = MagicMock()
        mock_date_obj.isoformat.return_value = "2026-08-03"
        mock_now.date.return_value = mock_date_obj
        mock_now.isoformat.return_value = "2026-08-03T09:30:00+00:00"
        
        mock_dt.now.return_value = mock_now
        
        with TemporaryDirectory() as temp_dir:
            # Create tasks file
            tasks_file = Path(temp_dir) / "tasks.json"
            tasks_data = {"tasks": [{"name": "Important task", "completed": False}]}
            tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")
            
            # Create startup record file
            record_file = Path(temp_dir) / "startup.json"
            
            # Check if first startup (no record yet)
            is_first = StartupBriefing.is_first_startup_today(record_file)
            self.assertTrue(is_first, "Should be first startup when no record exists")
            
            # Create briefing
            briefing = StartupBriefing(enable_voice=True)
            
            # Generate and deliver briefing
            result = briefing.deliver_briefing(
                include_greeting=True,
                include_time=True,
                include_tasks=True,
                include_status=True,
                tasks_path=tasks_file,
                ollama_available=True,
            )
            
            # Verify briefing was successful
            self.assertTrue(result["success"], "Briefing delivery should succeed")
            self.assertIn("Good morning", result["text"])
            self.assertIn("Monday", result["text"])
            self.assertIn("one task", result["text"].lower())
            mock_speak.assert_called_once()
            
            # Record startup (test without mocking to avoid date comparison issues)
            success = StartupBriefing.record_startup(record_file)
            self.assertTrue(success, "Recording startup should succeed")
            self.assertTrue(record_file.exists(), "Startup record file should exist")
            
            # Verify file structure
            data = json.loads(record_file.read_text(encoding="utf-8"))
            self.assertIn("timestamp", data)
            self.assertIn("date", data)


if __name__ == "__main__":
    unittest.main()
