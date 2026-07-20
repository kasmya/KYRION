"""
chatbot.py

A minimal chatbot that combines rule‑based intent recognition with a
pre‑trained language model for response generation.  Features:

* Intent detection via simple regex patterns (expandable).
* Response generation using Hugging‑Face 🤗 `transformers` pipeline.
* Conversation history with timestamps.
* Fallback responses for unknown intents.
* Type hints, docstrings, extensive error handling and basic security
  sanitisation.
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Callable

# Third‑party libraries – make sure they are installed.
# pip install transformers nltk
try:
    from transformers import pipeline, Pipeline
except Exception as exc:  # pragma: no cover
    raise ImportError("transformers library is required") from exc

try:
    import nltk
    from nltk.tokenize import word_tokenize
except Exception as exc:  # pragma: no cover
    raise ImportError("nltk library is required") from exc

# --------------------------------------------------------------------------- #
# Logging configuration (security‑aware: no user data is logged directly)
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Utility functions
# --------------------------------------------------------------------------- #
def _sanitize_input(user_input: str) -> str:
    """
    Remove potentially dangerous control characters and limit length.
    """
    # strip non‑printable characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", user_input)
    # truncate overly long messages (avoid DoS)
    return cleaned[:1024].strip()


# --------------------------------------------------------------------------- #
# Intent recognition
# --------------------------------------------------------------------------- #
class IntentRecognizer:
    """
    Simple rule‑based intent recogniser.  Patterns can be extended or
    replaced with a ML model later.
    """

    def __init__(self) -> None:
        # intent -> compiled regex pattern
        self._patterns: Dict[str, re.Pattern] = {
            "greeting": re.compile(r"\b(hi|hello|hey|greetings)\b", re.I),
            "goodbye": re.compile(r"\b(bye|farewell|see you)\b", re.I),
            "time": re.compile(r"\b(what time|current time|time now)\b", re.I),
            "weather": re.compile(r"\b(weather|forecast|rain|sunny)\b", re.I),
        }

    def recognize(self, text: str) -> Optional[str]:
        """
        Return the intent name if a pattern matches, otherwise ``None``.
        """
        for intent, pattern in self._patterns.items():
            if pattern.search(text):
                logger.debug("Intent '%s' matched for text: %s", intent, text)
                return intent
        logger.debug("No intent matched for text: %s", text)
        return None

    def add_intent(self, name: str, pattern: str) -> None:
        """
        Dynamically add a new intent.

        Raises:
            ValueError: If the regex pattern is invalid.
        """
        try:
            compiled = re.compile(pattern, re.I)
        except re.error as exc:
            raise ValueError(f"Invalid regex for intent '{name}': {exc}") from exc
        self._patterns[name] = compiled
        logger.info("Added new intent '%s' with pattern '%s'", name, pattern)


# --------------------------------------------------------------------------- #
# Response generation
# --------------------------------------------------------------------------- #
class ResponseGenerator:
    """
    Generates responses either from predefined rules (for known intents)
    or via a language model fallback.
    """

    def __init__(
        self,
        model_name: str = "distilgpt2",
        max_new_tokens: int = 50,
        temperature: float = 0.7,
    ) -> None:
        """
        Initialise the language model pipeline.

        Args:
            model_name: Name of the HuggingFace model.
            max_new_tokens: Upper bound for generated tokens.
            temperature: Sampling temperature.
        """
        try:
            self.generator: Pipeline = pipeline(
                "text-generation",
                model=model_name,
                tokenizer=model_name,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                device=self._detect_device(),
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to load model %s", model_name)
            raise RuntimeError(f"Could not load model {model_name}") from exc

        # Simple rule‑based responses for selected intents.
        self._fallback_responses: Dict[str, Callable[[str], str]] = {
            "greeting": lambda _: "Hello! How can I assist you today?",
            "goodbye": lambda _: "Goodbye! Have a great day!",
            "time": self._handle_time_intent,
            "weather": lambda _: "I’m not connected to a weather service right now.",
        }

    @staticmethod
    def _detect_device() -> int:
        """
        Returns the appropriate device id for transformers:
        -1 = CPU, 0+ = GPU index.
        """
        try:
            import torch  # type: ignore

            return 0 if torch.cuda.is_available() else -1
        except Exception:
            return -1

    @staticmethod
    def _handle_time_intent(_: str) -> str:
        """Return current system time formatted nicely."""
        return f"The current time is {datetime.now().strftime('%H:%M:%S')}."

    def generate(self, user_input: str, intent: Optional[str]) -> str:
        """
        Generate a response based on intent.

        Args:
            user_input: Sanitised user message.
            intent: Detected intent string or ``None``.

        Returns:
            A string response.
        """
        # Rule‑based fallback for known intents
        if intent in self._fallback_responses:
            try:
                return self._fallback_responses[intent](user_input)
            except Exception as exc:  # pragma: no cover
                logger.exception("Error in rule‑based response for %s", intent)
                # fall through to LLM generation

        # LLM fallback – prepend a short prompt
        prompt = f"User: {user_input}\nAssistant:"
        try:
            generated = self.generator(prompt, pad_token_id=self.generator.tokenizer.eos_token_id)
            # The pipeline returns a list of dicts.
            text: str = generated[0]["generated_text"]
            # Remove the prompt we gave to the model.
            response = text[len(prompt) :].strip()
            # Basic safety: limit length and strip any control characters
            response = _sanitize_input(response)[:200]
            return response or "I'm not sure how to respond to that."
        except Exception as exc:  # pragma: no cover
            logger.exception("LLM generation failed")
            return "Sorry, I couldn't process that request."


# --------------------------------------------------------------------------- #
# Conversation history
# --------------------------------------------------------------------------- #
class ConversationHistory:
    """
    Stores a chronological list of exchanges.
    """

    def __init__(self) -> None:
        self._history: List[Tuple[datetime, str, str]] = []

    def add_turn(self, timestamp: datetime, speaker: str, text: str) -> None:
        """
        Record a single turn.

        Args:
            timestamp: When the turn occurred.
            speaker: Either ``'user'`` or ``'bot'``.
            text: The raw text.
        """
        self._history.append((timestamp, speaker, text))

    def to_json(self) -> str:
        """Serialise the full conversation to JSON."""
        serialisable = [
            {"timestamp": ts.isoformat(), "speaker": spk, "text": txt}
            for ts, spk, txt in self._history
        ]
        return json.dumps(serialisable, ensure_ascii=False, indent=2)

    def __len__(self) -> int:
        return len(self._history)


# --------------------------------------------------------------------------- #
# Main chatbot orchestration
# --------------------------------------------------------------------------- #
class ChatBot:
    """
    High‑level interface tying intent recognition, response generation,
    and history together.
    """

    def __init__(self, model_name: str = "distilgpt2") -> None:
        self.intent_recogniser = IntentRecognizer()
        self.response_generator = ResponseGenerator(model_name=model_name)
        self.history = ConversationHistory()

    def process(self, raw_user_input: str) -> str:
        """
        Full processing pipeline: sanitise, recognise intent, generate reply,
        store the exchange.

        Returns:
            Bot response as a plain string.
        """
        user_input = _sanitize_input(raw_user_input)
        if not user_input:
            return "Please say something."

        intent = self.intent_recogniser.recognize(user_input)

        try:
            bot_reply = self.response_generator.generate(user_input, intent)
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected error while generating response")
            bot_reply = "Oops! Something went wrong."

        now = datetime.utcnow()
        self.history.add_turn(now, "user", user_input)
        self.history.add_turn(now, "bot", bot_reply)

        return bot_reply

    def export_history(self, filepath: str) -> None:
        """
        Write conversation history to a JSON file.

        Raises:
            OSError: If writing to ``filepath`` fails.
        """
        try:
            with open(filepath, "w", encoding="utf-8") as fp:
                fp.write(self.history.to_json())
            logger.info("Conversation history saved to %s", filepath)
        except OSError as exc:
            logger.exception("Failed to write conversation history")
            raise


# --------------------------------------------------------------------------- #
# Simple command‑line interface for manual testing
# --------------------------------------------------------------------------- #
def _run_cli() -> None:
    """
    Run an interactive loop reading from stdin and writing to stdout.
    Type ``/exit`` to quit, ``/save <path>`` to export history.
    """
    bot = ChatBot()
    print("ChatBot ready. Type your message, '/exit' to quit, '/save <file>' to export history.")
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if user_input.lower() == "/exit":
            break
        if user_input.lower().startswith("/save"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    bot.export_history(parts[1])
                except Exception as exc:
                    print(f"Failed to save: {exc}")
                continue
            else:
                print("Usage: /save <filepath>")
                continue

        response = bot.process(user_input)
        print(f"Bot: {response}")


if __name__ == "__main__":
    _run_cli()