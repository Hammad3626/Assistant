"""
Tests for Phase 5.3: Voice-to-Action Workflow
"""

import unittest
from unittest.mock import Mock, patch, MagicMock

from assistant.voice_to_action_workflow import (
    listen_and_parse,
    confirm_action,
    execute_voice_command,
    voice_to_action_workflow,
    voice_loop,
    VoiceActionResult,
)


class ListenAndParseTests(unittest.TestCase):
    """Test voice listening and command parsing."""
    
    @patch('assistant.voice_to_action_workflow.normalize_intent')
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_successful_listen_and_parse(self, mock_speak, mock_listen, mock_normalize):
        """Successfully listen and parse voice command."""
        # Mock voice input
        mock_voice_result = Mock()
        mock_voice_result.success = True
        mock_voice_result.text = "Turn on the light"
        mock_voice_result.confidence = 0.95
        mock_listen.return_value = mock_voice_result
        
        # Mock intent normalization
        mock_normalize.return_value = "turn_on light"
        
        user_input, command = listen_and_parse(speak_prompts=False)
        
        self.assertEqual(user_input, "Turn on the light")
        self.assertEqual(command, "turn_on light")
    
    @patch('assistant.voice_to_action_workflow.normalize_intent')
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_listen_failure_with_retries(self, mock_speak, mock_listen, mock_normalize):
        """Handle listen failure and retry."""
        # First attempt fails, second succeeds
        voice_fail = Mock()
        voice_fail.success = False
        voice_fail.error = "Noise too loud"
        
        voice_success = Mock()
        voice_success.success = True
        voice_success.text = "Turn off light"
        voice_success.confidence = 0.92
        
        mock_listen.side_effect = [voice_fail, voice_success]
        mock_normalize.return_value = "turn_off light"
        
        user_input, command = listen_and_parse(max_retries=2, speak_prompts=False)
        
        self.assertEqual(user_input, "Turn off light")
        self.assertEqual(command, "turn_off light")
        self.assertEqual(mock_listen.call_count, 2)
    
    @patch('assistant.voice_to_action_workflow.normalize_intent')
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_max_retries_exceeded(self, mock_speak, mock_listen, mock_normalize):
        """Fail when max retries exceeded."""
        # All attempts fail
        voice_fail = Mock()
        voice_fail.success = False
        voice_fail.error = "No speech detected"
        
        mock_listen.return_value = voice_fail
        
        user_input, command = listen_and_parse(max_retries=2, speak_prompts=False)
        
        self.assertIsNone(user_input)
        self.assertIsNone(command)
        self.assertEqual(mock_listen.call_count, 2)
    
    @patch('assistant.voice_to_action_workflow.normalize_intent')
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_no_command_parsed(self, mock_speak, mock_listen, mock_normalize):
        """Handle when input can't be parsed to command."""
        voice_result = Mock()
        voice_result.success = True
        voice_result.text = "blah blah blah"
        voice_result.confidence = 0.88
        
        mock_listen.return_value = voice_result
        mock_normalize.return_value = None  # No command parsed
        
        user_input, command = listen_and_parse(max_retries=2, speak_prompts=False)
        
        self.assertIsNone(user_input)
        self.assertIsNone(command)


class ConfirmActionTests(unittest.TestCase):
    """Test action confirmation."""
    
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_user_confirms_action(self, mock_speak, mock_listen):
        """User confirms action with 'yes'."""
        voice_result = Mock()
        voice_result.success = True
        voice_result.text = "Yes, do it"
        
        mock_listen.return_value = voice_result
        
        approved = confirm_action("turn_on_light", speak_confirmation=False)
        
        self.assertTrue(approved)
    
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_user_confirms_with_yeah(self, mock_speak, mock_listen):
        """User confirms with 'yeah'."""
        voice_result = Mock()
        voice_result.success = True
        voice_result.text = "Yeah go for it"
        
        mock_listen.return_value = voice_result
        
        approved = confirm_action("delete_file", speak_confirmation=False)
        
        self.assertTrue(approved)
    
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_user_rejects_action(self, mock_speak, mock_listen):
        """User rejects action with 'no'."""
        voice_result = Mock()
        voice_result.success = True
        voice_result.text = "No, cancel that"
        
        mock_listen.return_value = voice_result
        
        approved = confirm_action("dangerous_action", speak_confirmation=False)
        
        self.assertFalse(approved)
    
    @patch('assistant.voice_to_action_workflow.listen_once_with_confidence')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_confirmation_unclear_response(self, mock_speak, mock_listen):
        """Handle unclear confirmation response."""
        # Both attempts are unclear
        unclear_result = Mock()
        unclear_result.success = True
        unclear_result.text = "maybe"
        
        mock_listen.return_value = unclear_result
        
        approved = confirm_action("command", speak_confirmation=False)
        
        self.assertFalse(approved)  # Default to rejecting on unclear response


class ExecuteVoiceCommandTests(unittest.TestCase):
    """Test voice command execution."""
    
    def test_execute_with_core_instance(self):
        """Execute command using provided LocalAssistant instance."""
        mock_assistant = Mock()
        mock_assistant.execute_command.return_value = {
            "success": True,
            "output": "Light turned on",
            "error": None
        }
        
        result = execute_voice_command("turn_on light", assistant=mock_assistant)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["output"], "Light turned on")
        mock_assistant.execute_command.assert_called_once_with("turn_on light")
    
    def test_execute_command_failure(self):
        """Handle command execution failure."""
        mock_assistant = Mock()
        mock_assistant.execute_command.return_value = {
            "success": False,
            "output": "",
            "error": "Light not found"
        }
        
        result = execute_voice_command("turn_on light", assistant=mock_assistant)
        
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Light not found")
    
    @patch('assistant.voice_to_action_workflow.LocalAssistant')
    def test_execute_creates_core_if_needed(self, mock_assistant_class):
        """Create LocalAssistant instance if not provided."""
        mock_assistant = Mock()
        mock_assistant.execute_command.return_value = {
            "success": True,
            "output": "Done",
            "error": None
        }
        mock_assistant_class.return_value = mock_assistant
        
        result = execute_voice_command("some_command")
        
        self.assertTrue(result["success"])
        mock_assistant_class.assert_called_once()


class VoiceToActionWorkflowTests(unittest.TestCase):
    """Test complete voice-to-action workflow."""
    
    @patch('assistant.voice_to_action_workflow.execute_voice_command')
    @patch('assistant.voice_to_action_workflow.confirm_action')
    @patch('assistant.voice_to_action_workflow.listen_and_parse')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_successful_workflow(self, mock_speak, mock_listen_parse, mock_confirm, mock_execute):
        """Execute complete successful workflow."""
        # Setup mocks
        mock_listen_parse.return_value = ("Turn on light", "turn_on light")
        mock_confirm.return_value = True
        mock_execute.return_value = {
            "success": True,
            "command": "turn_on light",
            "output": "Light is now on",
            "error": None
        }
        
        result = voice_to_action_workflow(speak_enabled=False)
        
        self.assertTrue(result.success)
        self.assertEqual(result.user_input, "Turn on light")
        self.assertEqual(result.interpreted_command, "turn_on light")
        self.assertTrue(result.action_executed)
    
    @patch('assistant.voice_to_action_workflow.listen_and_parse')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_workflow_input_failed(self, mock_speak, mock_listen_parse):
        """Workflow fails when voice input fails."""
        mock_listen_parse.return_value = (None, None)
        
        result = voice_to_action_workflow(speak_enabled=False)
        
        self.assertFalse(result.success)
        self.assertEqual(result.user_input, "")
        self.assertIsNotNone(result.error)
    
    @patch('assistant.voice_to_action_workflow.execute_voice_command')
    @patch('assistant.voice_to_action_workflow.confirm_action')
    @patch('assistant.voice_to_action_workflow.listen_and_parse')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_workflow_user_rejects(self, mock_speak, mock_listen_parse, mock_confirm, mock_execute):
        """Workflow stops when user rejects action."""
        mock_listen_parse.return_value = ("Delete file", "delete file")
        mock_confirm.return_value = False  # User rejects
        
        result = voice_to_action_workflow(speak_enabled=False, confirm_before_execute=True)
        
        self.assertFalse(result.success)
        self.assertFalse(result.action_executed)
        self.assertIsNotNone(result.error)
        mock_execute.assert_not_called()
    
    @patch('assistant.voice_to_action_workflow.execute_voice_command')
    @patch('assistant.voice_to_action_workflow.confirm_action')
    @patch('assistant.voice_to_action_workflow.listen_and_parse')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_workflow_execution_fails(self, mock_speak, mock_listen_parse, mock_confirm, mock_execute):
        """Workflow reports failure if execution fails."""
        mock_listen_parse.return_value = ("Create file", "create_file")
        mock_confirm.return_value = True
        mock_execute.return_value = {
            "success": False,
            "command": "create_file",
            "output": "",
            "error": "Disk full"
        }
        
        result = voice_to_action_workflow(speak_enabled=False)
        
        self.assertFalse(result.success)
        self.assertFalse(result.action_executed)
        self.assertIn("Disk full", result.error)


class VoiceLoopTests(unittest.TestCase):
    """Test continuous voice command loop."""
    
    @patch('assistant.voice_to_action_workflow.voice_to_action_workflow')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_voice_loop_single_command_then_exit(self, mock_speak, mock_workflow):
        """Execute single command and exit on exit phrase."""
        workflow_result = Mock()
        workflow_result.success = True
        workflow_result.user_input = "turn on light. Exit."
        workflow_result.interpreted_command = "turn_on light"
        workflow_result.error = None
        
        mock_workflow.return_value = workflow_result
        
        stats = voice_loop(speak_enabled=False, exit_phrase="exit")
        
        self.assertEqual(stats["total_commands"], 1)
        self.assertEqual(stats["successful_commands"], 1)
        self.assertEqual(stats["failed_commands"], 0)
    
    @patch('assistant.voice_to_action_workflow.voice_to_action_workflow')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_voice_loop_multiple_commands(self, mock_speak, mock_workflow):
        """Execute multiple commands in sequence."""
        success_result = Mock()
        success_result.success = True
        success_result.user_input = "turn on light"
        success_result.interpreted_command = "turn_on light"
        success_result.error = None
        
        fail_result = Mock()
        fail_result.success = False
        fail_result.user_input = "do something invalid"
        fail_result.interpreted_command = ""
        fail_result.error = "Could not parse"
        
        exit_result = Mock()
        exit_result.success = True
        exit_result.user_input = "exit"
        exit_result.interpreted_command = "exit"
        exit_result.error = None
        
        mock_workflow.side_effect = [success_result, fail_result, exit_result]
        
        stats = voice_loop(speak_enabled=False)
        
        self.assertEqual(stats["total_commands"], 3)
        self.assertEqual(stats["successful_commands"], 2)
        self.assertEqual(stats["failed_commands"], 1)
    
    @patch('assistant.voice_to_action_workflow.voice_to_action_workflow')
    @patch('assistant.voice_to_action_workflow.speak')
    def test_voice_loop_keyboard_interrupt(self, mock_speak, mock_workflow):
        """Handle keyboard interrupt gracefully."""
        mock_workflow.side_effect = KeyboardInterrupt()
        
        stats = voice_loop(speak_enabled=False)
        
        # Should complete gracefully
        self.assertIsInstance(stats, dict)
        self.assertIn("total_commands", stats)


class VoiceActionResultTests(unittest.TestCase):
    """Test result data structure."""
    
    def test_result_initialization(self):
        """Create result with default values."""
        result = VoiceActionResult(
            success=True,
            user_input="test input",
            interpreted_command="test command",
            action_executed=True,
            execution_result="Success"
        )
        
        self.assertTrue(result.success)
        self.assertEqual(result.user_input, "test input")
        self.assertIsNone(result.error)
    
    def test_result_with_error(self):
        """Create result with error."""
        result = VoiceActionResult(
            success=False,
            user_input="failed input",
            interpreted_command="",
            action_executed=False,
            execution_result="",
            error="Connection failed"
        )
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Connection failed")


if __name__ == "__main__":
    unittest.main()
