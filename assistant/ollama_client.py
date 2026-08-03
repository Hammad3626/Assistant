"""Small standard-library Ollama client for local LLM responses."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaClient:
    """HTTP client for a local Ollama server."""

    model: str = "llama3.2:1b"
    host: str = "http://127.0.0.1:11434"
    timeout_seconds: int = 60
    num_predict: int = 160
    num_gpu: int = 0
    system_prompt: str | None = None

    def generate(self, prompt: str, memory_context: str | None = None) -> str:
        """Generate a short local answer with Ollama.
        
        Returns error message instead of raising, for graceful degradation.
        """
        payload = {
            "model": self.model,
            "prompt": self._build_prompt(
                prompt,
                memory_context=memory_context,
                system_prompt=self.system_prompt,
            ),
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": self.num_predict,
                # Keep generation conservative on mixed-GPU Windows PCs.
                "num_gpu": self.num_gpu,
            },
        }
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            # Graceful error return instead of raising
            return f"Ollama error: {detail}"
        except TimeoutError as exc:
            # Return user-friendly message for timeout
            return "Ollama is taking too long. Try a smaller model or close other heavy apps."
        except urllib.error.URLError as exc:
            # Return helpful message when Ollama unavailable
            return "Ollama is not running. Start Ollama, then try again. (http://127.0.0.1:11434)"
        except json.JSONDecodeError as exc:
            # Handle malformed responses
            return "Ollama returned invalid data. Check if Ollama is running correctly."
        except Exception as exc:
            # Catch-all for unexpected errors
            return f"Error generating response: {str(exc)}"

        answer = str(data.get("response", "")).strip()
        if not answer:
            return "Ollama returned an empty response. Try again with a different prompt."
        return answer

    @staticmethod
    def _build_prompt(
        user_text: str,
        memory_context: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        memory_block = ""
        if memory_context:
            memory_block = (
                "Saved user memories, explicitly provided by the user:\n"
                f"{memory_context}\n\n"
            )

        instructions = system_prompt or (
            "You are a local offline PC assistant. Answer briefly and clearly.\n"
            "Use saved memories only when they are relevant to the user's request.\n"
            "Do not claim you opened apps, changed files, sent messages, or ran commands.\n"
            "If the user asks for unsafe computer control, say that feature needs confirmation "
            "and is not enabled yet."
        )
        return (
            f"{instructions}\n\n"
            f"{memory_block}"
            f"User: {user_text}\n"
            "Assistant:"
        )
