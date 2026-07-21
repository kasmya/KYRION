"""
Simple rule‑based chatbot module.

Features
--------
* Intent recognition using regular‑expression patterns.
* Response generation with a small set of predefined replies.
* Conversation history tracking (user ↔ bot messages).
* Fallback response when no intent matches.
* Input validation, length limits and error handling.
* Logging of interactions for debugging (no sensitive data logged).

Only the Python standard library is used, making the module easy to install and
run in any environment.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Pattern, Tuple

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

_MAX_INPUT_LENGTH = 500  # characters; protects against extremely long payloads

# Mapping of intent names to a tuple of (compiled regex pattern, list of possible replies)
_INTENT_DEFINITIONS: Dict[str, Tuple[Pattern[str], List[str]]] = {
    "greeting": (
        re.compile(r"\b(hi|hello|hey|good (morning|afternoon|evening))\b", re.IGNORECASE),
        ["Hello! How can I help you today?", "Hi there! What can I do for you?"],
    ),
    "farewell": (
        re.compile(r"\b(bye|goodbye|see you|farewell)\b", re.IGNORECASE),
        ["Goodbye! Have a great day.", "See you later!"],
    ),
    "thanks": (
        re.compile(r"\b(thank you|thanks|thx)\b", re.IGNORECASE),
        ["You're welcome!", "No problem! Happy to help."],
    ),
    "weather_query": (
        re.compile(r"\bweather\b.*\b(in|at)\b\s*(?P<location>\w+)", re.IGNORECASE),
        ["I don't have live weather data, but you can check online for {location}."],
    ),
    # Add more intents as needed...
}

_FALLBACK_RESPONSES: List[str] = [
    "I'm not sure I understand. Could you rephrase?",
    "Sorry, I didn't get that. Can you try saying it differently?",
    "I didn't catch that. Could you elaborate?",
]

# --------------------------------------------------------------------------- #
# Logging setup (debug level can be changed by the user of the module)
# --------------------------------------------------------------------------- #

_logger = logging.getLogger(__name__)
_handler = logging.StreamHandler()
_formatter = logging.Formatter(
    fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_handler.setFormatter(_formatter)
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class Message:
    """A single message in the conversation."""
    sender: str  # "user" or "bot"
    content: str


@dataclass
class ConversationHistory:
    """Tracks the ordered list of messages exchanged."""
    messages: List[Message] = field(default_factory=list)

    def add(self, sender: str, content: str) -> None:
        """Append a new message to the history."""
        if sender not in {"user", "bot"}:
            raise ValueError(f"Invalid sender '{sender}'. Must be 'user' or 'bot'.")
        self.messages.append(Message(sender=sender, content=content))
        _logger.debug("Added message: %s: %s", sender, content)

    def get_last_n(self, n: int) -> List[Message]:
        """Return the last *n* messages (most recent first)."""
        if n < 0:
            raise ValueError("Parameter n must be non‑negative.")
        return self.messages[-n:][::-1]

    def clear(self) -> None:
        """Remove all stored messages."""
        self.messages.clear()
        _logger.debug("Conversation history cleared.")


# --------------------------------------------------------------------------- #
# Core chatbot implementation
# --------------------------------------------------------------------------- #

class Chatbot:
    """
    Rule‑based chatbot providing intent recognition, response generation,
    and conversation history management.
    """

    def __init__(self, max_input_length: int = _MAX_INPUT_LENGTH) -> None:
        """
        Initialise the chatbot.

        Parameters
        ----------
        max_input_length: int
            Maximum allowed length for user inputs. Exceeding this raises
            ``ValueError``.
        """
        if max_input_length <= 0:
            raise ValueError("max_input_length must be positive.")
        self._max_input_length = max_input_length
        self.history = ConversationHistory()
        _logger.info("Chatbot initialised with max_input_length=%d", max_input_length)

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #

    def respond(self, user_input: str) -> str:
        """
        Process a user message and return the bot's reply.

        Parameters
        ----------
        user_input: str
            Raw text entered by the user.

        Returns
        -------
        str
            Generated bot response.

        Raises
        ------
        ValueError
            If ``user_input`` is empty or exceeds the allowed length.
        """
        sanitized = self._sanitize_input(user_input)
        self.history.add(sender="user", content=sanitized)

        intent_name, extracted = self._recognize_intent(sanitized)
        if intent_name:
            reply = self._generate_response(intent_name, extracted)
        else:
            reply = self._fallback_response()

        self.history.add(sender="bot", content=reply)
        _logger.info("User: %s | Bot: %s", sanitized, reply)
        return reply

    def get_history(self, last_n: Optional[int] = None) -> List[Message]:
        """
        Retrieve conversation history.

        Parameters
        ----------
        last_n: Optional[int]
            Number of recent messages to return. If ``None``, returns all.

        Returns
        -------
        List[Message]
            Ordered list of messages (oldest first).
        """
        if last_n is None:
            return self.history.messages.copy()
        if last_n < 0:
            raise ValueError("last_n cannot be negative.")
        return self.history.messages[-last_n:]

    def reset(self) -> None:
        """Clear the conversation history."""
        self.history.clear()
        _logger.info("Chatbot conversation reset.")

    # ------------------------------------------------------------------- #
    # Internal helpers
    # ------------------------------------------------------------------- #

    def _sanitize_input(self, user_input: str) -> str:
        """
        Validate and clean user input.

        Strips leading/trailing whitespace and enforces length limits.

        Parameters
        ----------
        user_input: str

        Returns
        -------
        str
            Sanitised input.

        Raises
        ------
        ValueError
            If input is empty after stripping or exceeds length limit.
        """
        if not isinstance(user_input, str):
            raise TypeError("user_input must be a string.")
        cleaned = user_input.strip()
        if not cleaned:
            raise ValueError("Input cannot be empty or whitespace only.")
        if len(cleaned) > self._max_input_length:
            raise ValueError(
                f"Input exceeds maximum length of {self._max_input_length} characters."
            )
        _logger.debug("Sanitized input: %s", cleaned)
        return cleaned

    def _recognize_intent(self, text: str) -> Tuple[Optional[str], Dict[str, str]]:
        """
        Identify the intent of the given text.

        Parameters
        ----------
        text: str

        Returns
        -------
        Tuple[Optional[str], Dict[str, str]]
            ``intent_name`` if a pattern matches, otherwise ``None``; and a
            dictionary of named capture groups (may be empty).
        """
        for intent, (pattern, _) in _INTENT_DEFINITIONS.items():
            match = pattern.search(text)
            if match:
                groups = {k: v for k, v in match.groupdict().items() if v}
                _logger.debug("Intent recognized: %s with groups %s", intent, groups)
                return intent, groups
        _logger.debug("No intent matched for text: %s", text)
        return None, {}

    def _generate_response(
        self, intent_name: str, slots: Dict[str, str]
    ) -> str:
        """
        Produce a response string for a recognised intent.

        Parameters
        ----------
        intent_name: str
            Name of the matched intent.
        slots: Dict[str, str]
            Extracted named groups from the regex pattern.

        Returns
        -------
        str
            Selected response with slot substitution if applicable.
        """
        _, responses = _INTENT_DEFINITIONS[intent_name]
        template = random.choice(responses)
        try:
            response = template.format(**slots)
        except KeyError as exc:
            # Missing slot – log and return template unchanged
            _logger.warning(
                "Missing slot %s for intent %s; returning unformatted template.",
                exc.args[0],
                intent_name,
            )
            response = template
        _logger.debug("Generated response for intent %s: %s", intent_name, response)
        return response

    def _fallback_response(self) -> str:
        """Return a random fallback message."""
        response = random.choice(_FALLBACK_RESPONSES)
        _logger.debug("Fallback response selected: %s", response)
        return response


# --------------------------------------------------------------------------- #
# Example usage guard (does not execute on import)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # Simple REPL for manual testing; not part of the library API.
    bot = Chatbot()
    print("Chatbot ready. Type 'exit' to quit.")
    while True:
        try:
            user_msg = input("> ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
        if user_msg.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        try:
            reply = bot.respond(user_msg)
            print(reply)
        except Exception as exc:  # broad to keep REPL robust
            _logger.exception("Error processing input")
            print(f"Error: {exc}")