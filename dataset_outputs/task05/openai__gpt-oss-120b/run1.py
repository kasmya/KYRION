"""
Simple chatbot implementation with:
- Intent recognition (rule‑based using regex & NLTK)
- Response generation (fallback using HuggingFace Transformers)
- Conversation history tracking
- Graceful error handling & basic security checks

Dependencies:
    pip install transformers nltk regex
"""

from __future__ import annotations

import re
import html
import logging
from typing import List, Tuple, Dict, Optional

import nltk
from nltk.tokenize import word_tokenize
from transformers import pipeline, PipelineException

# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #

# Download NLTK data (only once)
nltk.download("punkt", quiet=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Intent definitions
# --------------------------------------------------------------------------- #

Intent = Tuple[str, re.Pattern]  # (name, compiled regex)


def _compile_intents() -> List[Intent]:
    """Compile the regex patterns for each supported intent."""
    raw_intents: Dict[str, str] = {
        "greeting": r"\b(hi|hello|hey|good morning|good afternoon|good evening)\b",
        "goodbye": r"\b(bye|goodbye|see you|farewell)\b",
        "thanks": r"\b(thank you|thanks|much appreciated)\b",
        "weather": r"\b(weather|rain|sunny|forecast|temperature)\b",
        "time": r"\b(what.?s the time|current time|time now)\b",
    }
    return [(name, re.compile(pattern, flags=re.IGNORECASE)) for name, pattern in raw_intents.items()]


INTENTS: List[Intent] = _compile_intents()


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def _sanitize_input(user_input: str, max_length: int = 512) -> str:
    """
    Perform basic security sanitization:
    - Trim whitespace
    - Escape HTML to avoid injections in environments that render HTML
    - Truncate excessively long inputs
    """
    sanitized = html.escape(user_input.strip())
    if len(sanitized) > max_length:
        logger.warning("User input exceeded %s characters; truncating.", max_length)
        sanitized = sanitized[:max_length]
    return sanitized


def _recognize_intent(message: str) -> Optional[str]:
    """
    Return the name of the first matching intent, or None if no intent matches.
    """
    for intent_name, pattern in INTENTS:
        if pattern.search(message):
            logger.debug("Matched intent %s for message: %s", intent_name, message)
            return intent_name
    logger.debug("No intent matched for message: %s", message)
    return None


# --------------------------------------------------------------------------- #
# Core chatbot class
# --------------------------------------------------------------------------- #


class Chatbot:
    """
    Chatbot with intent recognition, pre‑defined responses, and a fallback
    generative model.

    Attributes
    ----------
    history : List[Tuple[str, str]]
        Chronological list of (speaker, message) pairs.
    fallback_generator : transformers.pipelines.Pipeline
        Text‑generation pipeline used when no intent matches.
    max_history : int
        Maximum number of exchanges kept in memory.
    """

    def __init__(self, fallback_model: str = "microsoft/DialoGPT-medium", max_history: int = 10) -> None:
        """
        Initialise the chatbot.

        Parameters
        ----------
        fallback_model : str, optional
            HuggingFace model identifier for the fallback generator.
        max_history : int, optional
            Number of most recent exchanges retained.
        """
        self.history: List[Tuple[str, str]] = []
        self.max_history = max_history

        try:
            self.fallback_generator = pipeline("text-generation", model=fallback_model, tokenizer=fallback_model)
            logger.info("Loaded fallback model: %s", fallback_model)
        except (PipelineException, OSError) as exc:
            logger.error("Failed to load fallback model %s: %s", fallback_model, exc)
            raise RuntimeError(f"Unable to initialise fallback model '{fallback_model}'.") from exc

        # Simple static responses per intent
        self.intent_responses: Dict[str, str] = {
            "greeting": "Hello! How can I assist you today?",
            "goodbye": "Goodbye! Have a great day!",
            "thanks": "You're welcome! Happy to help.",
            "weather": "I don't have real‑time weather data, but you can check a weather service like weather.com.",
            "time": "I'm not connected to a clock, but you can look at your device's time display.",
        }

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #

    def add_user_message(self, message: str) -> None:
        """
        Record a user message after sanitising it.

        Parameters
        ----------
        message : str
            Raw user input.
        """
        sanitized = _sanitize_input(message)
        self.history.append(("user", sanitized))
        self._trim_history()

    def generate_response(self) -> str:
        """
        Produce a response based on the latest user message.
        Returns
        -------
        str
            Bot reply.
        """
        if not self.history or self.history[-1][0] != "user":
            raise RuntimeError("No user message to respond to.")

        last_user_msg = self.history[-1][1]
        intent = _recognize_intent(last_user_msg)

        if intent and intent in self.intent_responses:
            reply = self.intent_responses[intent]
            logger.info("Responding with intent %s", intent)
        else:
            reply = self._fallback_response(last_user_msg)

        self.history.append(("bot", reply))
        self._trim_history()
        return reply

    def get_conversation_history(self) -> List[Tuple[str, str]]:
        """
        Return a copy of the conversation history.

        Returns
        -------
        List[Tuple[str, str]]
            List of (speaker, message) tuples.
        """
        return self.history.copy()

    # ------------------------------------------------------------------- #
    # Private helpers
    # ------------------------------------------------------------------- #

    def _fallback_response(self, user_message: str) -> str:
        """
        Use the generative model to create a response.

        Parameters
        ----------
        user_message : str
            Sanitised user input.

        Returns
        -------
        str
            Generated reply.
        """
        try:
            # Provide a short prompt that includes the user message.
            prompt = f"User: {user_message}\nBot:"
            generated = self.fallback_generator(
                prompt,
                max_length=150,
                num_return_sequences=1,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
            )
            raw_reply = generated[0]["generated_text"]
            # Extract only the bot part after the prompt.
            reply = raw_reply.split("Bot:", 1)[-1].strip()
            # Clean up any trailing newline or user prompts.
            reply = reply.split("\n", 1)[0].strip()
            logger.debug("Fallback generated reply: %s", reply)
            return reply or "I'm not sure how to respond to that."
        except Exception as exc:  # Broad catch for any generation errors
            logger.exception("Fallback generation failed: %s", exc)
            return "Sorry, I'm having trouble responding right now."

    def _trim_history(self) -> None:
        """Keep only the most recent `max_history` exchanges (user+bot pairs)."""
        if len(self.history) > self.max_history * 2:
            excess = len(self.history) - self.max_history * 2
            self.history = self.history[excess:]


# --------------------------------------------------------------------------- #
# Example interactive loop (can be removed when importing the class)
# --------------------------------------------------------------------------- #

def _run_demo() -> None:
    """Simple REPL demonstrating the Chatbot class."""
    bot = Chatbot()
    print("Chatbot ready! Type 'exit' to quit.")
    while True:
        try:
            user_input = input("You: ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if user_input.lower().strip() in {"exit", "quit"}:
            print("Bot: Goodbye!")
            break

        try:
            bot.add_user_message(user_input)
            response = bot.generate_response()
            print(f"Bot: {response}")
        except Exception as err:
            logger.exception("Unexpected error: %s", err)
            print("Bot: Oops! Something went wrong.")


if __name__ == "__main__":
    _run_demo()