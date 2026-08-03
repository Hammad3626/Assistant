"""Tests for auto-start management system."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from assistant.autostart_manager import (
    AutoStartManager,
    AutoStartStatus,
)


class AutoStartStatusTests(unittest.TestCase):
    """Tests for AutoStartStatus dataclass."""

    def test_status_creation(self):
        """Status can be created with parameters."""
        status = AutoStartStatus(
            enabled=True,
            cli_shortcut_exists=True,
            gui_shortcut_exists=False,
            voice_shortcut_exists=False,
        )
        
        self.assertTrue(status.enabled)
        self.assertTrue(status.cli_shortcut_exists)
        self.assertFalse(status.gui_shortcut_exists)

    def test_status_defaults(self):
        """Status has default values for optional fields."""
        status = AutoStartStatus(
            enabled=False,
            cli_shortcut_exists=False,
            gui_shortcut_exists=False,
            voice_shortcut_exists=False,
        )
        
        self.assertIsNone(status.startup_folder)
        self.assertIsNotNone(status.startup_files)
        self.assertEqual(len(status.startup_files), 0)


class StartupFolderTests(unittest.TestCase):
    """Tests for Startup folder detection."""

    def test_get_startup_folder_exists(self):
        """Returns path when Startup folder exists."""
        with patch.object(AutoStartManager, 'STARTUP_FOLDER') as mock_folder:
            mock_folder.exists.return_value = True
            
            result = AutoStartManager.get_startup_folder()
            
            self.assertIsNotNone(result)
            self.assertEqual(result, mock_folder)

    def test_get_startup_folder_not_exists(self):
        """Returns None when Startup folder doesn't exist."""
        with patch.object(AutoStartManager, 'STARTUP_FOLDER') as mock_folder:
            mock_folder.exists.return_value = False
            
            result = AutoStartManager.get_startup_folder()
            
            self.assertIsNone(result)


class StatusCheckTests(unittest.TestCase):
    """Tests for checking auto-start status."""

    def test_status_disabled_no_folder(self):
        """Status is disabled when Startup folder doesn't exist."""
        with patch.object(AutoStartManager, 'get_startup_folder', return_value=None):
            status = AutoStartManager.check_status()
            
            self.assertFalse(status.enabled)
            self.assertFalse(status.cli_shortcut_exists)
            self.assertFalse(status.gui_shortcut_exists)
            self.assertFalse(status.voice_shortcut_exists)

    def test_status_with_cli_batch(self):
        """Status detects CLI batch file."""
        with TemporaryDirectory() as temp_dir:
            startup_folder = Path(temp_dir)
            cli_batch = startup_folder / "start_cli.bat"
            cli_batch.touch()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                status = AutoStartManager.check_status()
                
                self.assertTrue(status.enabled)
                self.assertTrue(status.cli_shortcut_exists)
                self.assertFalse(status.gui_shortcut_exists)
                self.assertIn("start_cli.bat", status.startup_files)

    def test_status_with_all_batch_files(self):
        """Status detects all batch files."""
        with TemporaryDirectory() as temp_dir:
            startup_folder = Path(temp_dir)
            (startup_folder / "start_cli.bat").touch()
            (startup_folder / "start_gui.bat").touch()
            (startup_folder / "start_voice.bat").touch()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                status = AutoStartManager.check_status()
                
                self.assertTrue(status.enabled)
                self.assertTrue(status.cli_shortcut_exists)
                self.assertTrue(status.gui_shortcut_exists)
                self.assertTrue(status.voice_shortcut_exists)
                self.assertEqual(len(status.startup_files), 3)


class StatusReportTests(unittest.TestCase):
    """Tests for status report generation."""

    def test_report_disabled(self):
        """Report indicates disabled auto-start."""
        status = AutoStartStatus(
            enabled=False,
            cli_shortcut_exists=False,
            gui_shortcut_exists=False,
            voice_shortcut_exists=False,
        )
        
        report = AutoStartManager.get_status_report(status)
        
        self.assertIn("not enabled", report.lower())

    def test_report_enabled_cli(self):
        """Report indicates CLI auto-start enabled."""
        status = AutoStartStatus(
            enabled=True,
            cli_shortcut_exists=True,
            gui_shortcut_exists=False,
            voice_shortcut_exists=False,
            startup_folder=Path("C:\\Startup"),
        )
        
        report = AutoStartManager.get_status_report(status)
        
        self.assertIn("enabled", report.lower())
        self.assertIn("cli", report.lower())

    def test_report_generates_if_none_provided(self):
        """Report generates current status if not provided."""
        with patch.object(AutoStartManager, 'check_status') as mock_check:
            mock_status = AutoStartStatus(
                enabled=True,
                cli_shortcut_exists=True,
                gui_shortcut_exists=False,
                voice_shortcut_exists=False,
            )
            mock_check.return_value = mock_status
            
            report = AutoStartManager.get_status_report()
            
            self.assertIn("enabled", report.lower())
            mock_check.assert_called_once()


class EnableAutoStartTests(unittest.TestCase):
    """Tests for enabling auto-start."""

    def test_enable_requires_mode(self):
        """Enabling requires at least one mode."""
        with TemporaryDirectory() as temp_dir:
            result = AutoStartManager.enable_autostart(project_root=Path(temp_dir))
            
            self.assertFalse(result["success"])
            self.assertGreater(len(result["errors"]), 0)

    def test_enable_no_startup_folder(self):
        """Fails when Startup folder doesn't exist."""
        with patch.object(AutoStartManager, 'get_startup_folder', return_value=None):
            result = AutoStartManager.enable_autostart(cli=True, project_root=Path("."))
            
            self.assertFalse(result["success"])
            self.assertGreater(len(result["errors"]), 0)

    def test_enable_missing_source_file(self):
        """Fails when source batch file doesn't exist."""
        with TemporaryDirectory() as temp_dir:
            startup_folder = Path(temp_dir) / "Startup"
            startup_folder.mkdir()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                result = AutoStartManager.enable_autostart(
                    cli=True,
                    project_root=Path("/nonexistent"),
                )
                
                self.assertFalse(result["success"])
                self.assertGreater(len(result["errors"]), 0)

    def test_enable_cli_mode(self):
        """Successfully enables CLI mode."""
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            project_root.mkdir()
            (project_root / "start_cli.bat").touch()
            
            startup_folder = Path(temp_dir) / "Startup"
            startup_folder.mkdir()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                result = AutoStartManager.enable_autostart(
                    cli=True,
                    project_root=project_root,
                )
                
                self.assertTrue(result["success"])
                self.assertIn("CLI", result["enabled_modes"])
                self.assertTrue((startup_folder / "start_cli.bat").exists())

    def test_enable_multiple_modes(self):
        """Successfully enables multiple modes."""
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            project_root.mkdir()
            (project_root / "start_cli.bat").touch()
            (project_root / "start_gui.bat").touch()
            (project_root / "start_voice.bat").touch()
            
            startup_folder = Path(temp_dir) / "Startup"
            startup_folder.mkdir()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                result = AutoStartManager.enable_autostart(
                    cli=True,
                    gui=True,
                    voice=True,
                    project_root=project_root,
                )
                
                self.assertTrue(result["success"])
                self.assertEqual(len(result["enabled_modes"]), 3)
                self.assertTrue((startup_folder / "start_cli.bat").exists())
                self.assertTrue((startup_folder / "start_gui.bat").exists())
                self.assertTrue((startup_folder / "start_voice.bat").exists())


class DisableAutoStartTests(unittest.TestCase):
    """Tests for disabling auto-start."""

    def test_disable_requires_mode(self):
        """Disabling requires at least one mode unless all_modes=True."""
        result = AutoStartManager.disable_autostart()
        
        self.assertFalse(result["success"])
        self.assertGreater(len(result["errors"]), 0)

    def test_disable_no_startup_folder(self):
        """Fails when Startup folder doesn't exist."""
        with patch.object(AutoStartManager, 'get_startup_folder', return_value=None):
            result = AutoStartManager.disable_autostart(cli=True)
            
            self.assertFalse(result["success"])

    def test_disable_cli_mode(self):
        """Successfully disables CLI mode."""
        with TemporaryDirectory() as temp_dir:
            startup_folder = Path(temp_dir)
            cli_batch = startup_folder / "start_cli.bat"
            cli_batch.touch()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                result = AutoStartManager.disable_autostart(cli=True)
                
                self.assertTrue(result["success"])
                self.assertIn("CLI", result["disabled_modes"])
                self.assertFalse(cli_batch.exists())

    def test_disable_all_modes(self):
        """Successfully disables all modes with all_modes=True."""
        with TemporaryDirectory() as temp_dir:
            startup_folder = Path(temp_dir)
            (startup_folder / "start_cli.bat").touch()
            (startup_folder / "start_gui.bat").touch()
            (startup_folder / "start_voice.bat").touch()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                result = AutoStartManager.disable_autostart(all_modes=True)
                
                self.assertTrue(result["success"])
                self.assertEqual(len(result["disabled_modes"]), 3)
                self.assertFalse((startup_folder / "start_cli.bat").exists())
                self.assertFalse((startup_folder / "start_gui.bat").exists())
                self.assertFalse((startup_folder / "start_voice.bat").exists())

    def test_disable_nonexistent_file(self):
        """Silently skips when batch file doesn't exist."""
        with TemporaryDirectory() as temp_dir:
            startup_folder = Path(temp_dir)
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                result = AutoStartManager.disable_autostart(cli=True)
                
                # Succeed even if file didn't exist (it's already disabled)
                self.assertTrue(result["success"])


class IntegrationTests(unittest.TestCase):
    """Integration tests for auto-start system."""

    def test_enable_then_disable(self):
        """Can enable and then disable auto-start."""
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            project_root.mkdir()
            (project_root / "start_cli.bat").touch()
            
            startup_folder = Path(temp_dir) / "Startup"
            startup_folder.mkdir()
            
            with patch.object(AutoStartManager, 'get_startup_folder', return_value=startup_folder):
                # Enable
                enable_result = AutoStartManager.enable_autostart(
                    cli=True,
                    project_root=project_root,
                )
                self.assertTrue(enable_result["success"])
                self.assertTrue((startup_folder / "start_cli.bat").exists())
                
                # Check status
                status = AutoStartManager.check_status()
                self.assertTrue(status.enabled)
                self.assertTrue(status.cli_shortcut_exists)
                
                # Disable
                disable_result = AutoStartManager.disable_autostart(cli=True)
                self.assertTrue(disable_result["success"])
                self.assertFalse((startup_folder / "start_cli.bat").exists())
                
                # Check status again
                status = AutoStartManager.check_status()
                self.assertFalse(status.enabled)


if __name__ == "__main__":
    unittest.main()
