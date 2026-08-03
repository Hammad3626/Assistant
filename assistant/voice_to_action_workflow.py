"""
Phase 5.3: Voice-to-Action Workflow

Enables hands-free operation:
1. Listen for voice input
2. Transcribe to text
3. Parse command intent
4. Confirm understanding with user
5. Execute action
6. Report result via voice
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from assistant.voice_input import listen_once_with_confidence, VoiceInputResult
from assistant.voice_output import speak
from assistant.intent_parser import normalize_intent
from assistant.core import LocalAssistant

logger = logging.getLogger(__name__)


@dataclass
class VoiceActionResult:
    """Result of a voice-to-action workflow."""
    success: bool
    user_input: str
    interpreted_command: str
    action_executed: bool
    execution_result: str
    error: Optional[str] = None


def listen_and_parse(
    max_retries: int = 3,
    speak_prompts: bool = True
) -> tuple[Optional[str], Optional[str]]:
    """
    Listen for voice input and parse to command.
    
    Args:
        max_retries: Maximum number of attempts to get clear input
        speak_prompts: Whether to use voice prompts
    
    Returns:
        Tuple of (transcribed_text, parsed_command) or (None, None) on failure
    """
    for attempt in range(max_retries):
        # Prompt user
        if speak_prompts:
            speak(f"Listening... (attempt {attempt + 1})")
        
        # Listen for voice input
        voice_result = listen_once_with_confidence(timeout=10)
        
        if not voice_result.success:
            logger.warning(f"Voice input failed: {voice_result.error}")
            if speak_prompts:
                speak(f"Sorry, I didn't catch that. {voice_result.error}")
            continue
        
        transcribed = voice_result.text
        confidence = voice_result.confidence
        
        logger.info(f"Heard: '{transcribed}' (confidence: {confidence})")
        
        # Parse intent
        try:
            command = normalize_intent(transcribed)
            
            if not command:
                logger.debug("No command parsed from input")
                if speak_prompts:
                    speak("I didn't understand that. Please try again.")
                continue
            
            return transcribed, command
        
        except Exception as e:
            logger.error(f"Intent parsing error: {e}")
            if speak_prompts:
                speak("Error parsing command. Please try again.")
            continue
    
    logger.warning(f"Failed to get clear input after {max_retries} attempts")
    if speak_prompts:
        speak("I couldn't understand after several attempts. Giving up.")
    
    return None, None


def confirm_action(
    command: str,
    speak_confirmation: bool = True
) -> bool:
    """
    Confirm action with user before execution.
    
    Args:
        command: The interpreted command
        speak_confirmation: Whether to speak confirmation prompt
    
    Returns:
        True if user confirms, False if user rejects
    """
    confirmation_prompt = f"Did you want to: {command}? Say yes or no."
    
    if speak_confirmation:
        speak(confirmation_prompt)
    
    logger.info(f"Waiting for confirmation on: {command}")
    
    # Listen for yes/no response
    for attempt in range(2):
        voice_result = listen_once_with_confidence(timeout=5)
        
        if not voice_result.success:
            if speak_confirmation:
                speak("I didn't hear that clearly.")
            continue
        
        response = voice_result.text.lower()
        
        if any(word in response for word in ["yes", "yeah", "yep", "go", "confirm"]):
            logger.info("User confirmed action")
            return True
        elif any(word in response for word in ["no", "nope", "cancel", "stop", "reject"]):
            logger.info("User rejected action")
            if speak_confirmation:
                speak("Understood. Action cancelled.")
            return False
    
    logger.warning("Could not get clear confirmation response")
    if speak_confirmation:
        speak("I couldn't understand your response. Cancelling.")
    return False


def execute_voice_command(
    command: str,
    assistant: Optional[LocalAssistant] = None
) -> dict:
    """
    Execute a command parsed from voice input.
    
    Args:
        command: The command to execute
        assistant: Optional LocalAssistant instance to use for execution
    
    Returns:
        Execution result dictionary
    """
    result = {
        "success": False,
        "command": command,
        "output": "",
        "error": None
    }
    
    if not assistant:
        try:
            assistant = LocalAssistant()
        except Exception as e:
            result["error"] = f"Failed to initialize LocalAssistant: {str(e)}"
            logger.error(result["error"])
            return result
    
    try:
        # Execute the command through the LocalAssistant interface
        exec_result = assistant.execute_command(command)
        
        result["success"] = exec_result.get("success", False)
        result["output"] = exec_result.get("output", "")
        result["error"] = exec_result.get("error")
        
        logger.info(f"Command execution result: {result}")
    
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Command execution error: {e}", exc_info=True)
    
    return result


def voice_to_action_workflow(
    assistant: Optional[LocalAssistant] = None,
    confirm_before_execute: bool = True,
    speak_enabled: bool = True,
    max_voice_attempts: int = 3
) -> VoiceActionResult:
    """
    Complete voice-to-action workflow:
    1. Listen for voice input
    2. Parse to command
    3. Confirm with user
    4. Execute action
    5. Report result
    
    Args:
        assistant: Optional LocalAssistant instance for execution
        confirm_before_execute: Whether to ask for confirmation
        speak_enabled: Whether to use voice output
        max_voice_attempts: Max attempts for voice input
    
    Returns:
        VoiceActionResult with workflow outcome
    """
    result = VoiceActionResult(
        success=False,
        user_input="",
        interpreted_command="",
        action_executed=False,
        execution_result=""
    )
    
    try:
        # Step 1: Listen and parse
        if speak_enabled:
            speak("Ready for voice command.")
        
        user_input, command = listen_and_parse(
            max_retries=max_voice_attempts,
            speak_prompts=speak_enabled
        )
        
        if not user_input or not command:
            result.error = "Failed to get clear voice input"
            if speak_enabled:
                speak("Command input failed. Please try again later.")
            return result
        
        result.user_input = user_input
        result.interpreted_command = command
        
        logger.info(f"Parsed command: {command}")
        
        # Step 2: Confirm with user
        if confirm_before_execute:
            approved = confirm_action(command, speak_confirmation=speak_enabled)
            if not approved:
                result.error = "User rejected action"
                return result
        
        # Step 3: Execute
        exec_result = execute_voice_command(command, assistant)
        
        if not exec_result.get("success"):
            result.error = exec_result.get("error", "Execution failed")
            if speak_enabled:
                speak(f"Command failed: {result.error}")
            return result
        
        result.action_executed = True
        result.execution_result = exec_result.get("output", "Command executed")
        result.success = True
        
        # Step 4: Report result
        if speak_enabled:
            speak(f"Done. {result.execution_result}")
        
        logger.info("Voice-to-action workflow completed successfully")
    
    except Exception as e:
        result.error = f"Workflow error: {str(e)}"
        logger.error(f"Voice-to-action workflow error: {e}", exc_info=True)
        if speak_enabled:
            speak(f"Error: {result.error}")
    
    return result


def voice_loop(
    assistant: Optional[LocalAssistant] = None,
    speak_enabled: bool = True,
    exit_phrase: str = "exit",
) -> dict:
    """
    Continuous voice command loop until user exits.
    
    Args:
        assistant: LocalAssistant instance for command execution
        speak_enabled: Whether to use voice output
        exit_phrase: Command to exit the loop
    
    Returns:
        Summary statistics of all commands executed
    """
    stats = {
        "total_commands": 0,
        "successful_commands": 0,
        "failed_commands": 0,
        "commands": []
    }
    
    logger.info("Starting voice command loop")
    if speak_enabled:
        speak("Voice mode active. Say 'exit' to stop.")
    
    try:
        while True:
            # Run workflow
            workflow_result = voice_to_action_workflow(
                assistant=assistant,
                speak_enabled=speak_enabled,
                confirm_before_execute=True
            )
            
            stats["total_commands"] += 1
            
            if workflow_result.success:
                stats["successful_commands"] += 1
            else:
                stats["failed_commands"] += 1
            
            stats["commands"].append({
                "input": workflow_result.user_input,
                "command": workflow_result.interpreted_command,
                "success": workflow_result.success,
                "error": workflow_result.error
            })
            
            # Check for exit phrase
            if exit_phrase.lower() in workflow_result.user_input.lower():
                logger.info("User initiated exit")
                if speak_enabled:
                    speak("Exiting voice mode.")
                break
    
    except KeyboardInterrupt:
        logger.info("Voice loop interrupted by user")
        if speak_enabled:
            speak("Voice mode interrupted.")
    
    except Exception as e:
        logger.error(f"Voice loop error: {e}", exc_info=True)
        if speak_enabled:
            speak(f"Voice mode error: {e}")
    
    finally:
        logger.info(
            f"Voice loop completed: {stats['successful_commands']} successful, "
            f"{stats['failed_commands']} failed"
        )
    
    return stats
