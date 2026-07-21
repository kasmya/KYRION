"""
chatbot.py
~~~~~~~~~~

A lightweight, rule‑based chatbot implementation suitable for inclusion in
small projects or as a teaching example.  Features:

* Intent recognition using regular expressions.
* Simple response generation with optional placeholders.
* Conversation history tracking (timestamped user ↔ bot exchanges).
* Graceful fallback when no intent matches.
* Full type hints, comprehensive docstrings, and explicit error handling.

Only the Python standard library is required.
"""

from __future__ import annotations

import datetime
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Pattern, Tuple

# --------------------------------------------------------------------------- #
# Logging configuration (security‑aware: no sensitive data is logged)
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class MessageRecord:
    """A single exchange entry in the conversation history."""
    timestamp: datetime.datetime
    user_message: str
    bot_message: str


# --------------------------------------------------------------------------- #
# Core chatbot class
# --------------------------------------------------------------------------- #
class ChatBot:
    """
    Rule‑based chatbot with intent recognition, response generation,
    and conversation history.

    Parameters
    ----------
    intents : Optional[Dict[str, Dict[str, Any]]]
        Mapping of intent names to a dictionary containing:
        * ``patterns`` – list of regex strings to match the intent.
        * ``responses`` – list of possible response templates.
        If omitted, a default set of intents is used.
    fallback_response : str
        Message returned when no intent matches. Defaults to a polite generic reply.
    """

    _DEFAULT_INTENTS: Dict[str, Dict[str, List[str]]] = {
        "greeting": {
            "patterns": [r"\bhi\b", r"\bhello\b", r"\bhey\b", r"\bgood (morning|afternoon|evening)\b"],
            "responses": ["Hello! How can I assist you today?", "Hi there! What can I do for you?"],
        },
        "farewell": {
            "patterns": [r"\bbye\b", r"\bgoodbye\b", r"\bsee you\b", r"\btake care\b"],
            "responses": ["Goodbye! Have a great day.", "See you later!"],
        },
        "thanks": {
            "patterns": [r"\bthanks\b", r"\bthank you\b", r"\bthx\b"],
            "responses": ["You're welcome!", "Happy to help!"],
        },
        "time_query": {
            "patterns": [r"\bwhat time\b", r"\bcurrent time\b", r"\btime now\b"],
            "responses": ["The current time is {time}."],
        },
    }

    def __init__(
        self,
        intents: Optional[Dict[str, Dict[str, List[str]]]] = None,
        fallback_response: str = "I'm not sure how to respond to that. Could you rephrase?",
    ) -> None:
        self._intents = intents or self._DEFAULT_INTENTS
        self._fallback_response = fallback_response
        self._compiled_patterns: Dict[str, List[Pattern[str]]] = self._compile_intent_patterns()
        self._history: List[MessageRecord] = []
        self._history_lock = threading.Lock()
        logger.info("ChatBot initialized with %d intent(s).", len(self._intents))

    # --------------------------------------------------------------------- #
    # Private helpers
    # --------------------------------------------------------------------- #
    def _compile_intent_patterns(self) -> Dict[str, List[Pattern[str]]]:
        """
        Compile regex patterns for all intents.

        Returns
        -------
        Dict[str, List[Pattern[str]]]
            Mapping from intent name to compiled regex objects.
        """
        compiled: Dict[str, List[Pattern[str]]] = {}
        for intent, data in self._intents.items():
            try:
                compiled[intent] = [re.compile(p, re.IGNORECASE) for p in data["patterns"]]
            except re.error as exc:
                logger.error("Invalid regex pattern for intent '%s': %s", intent, exc)
                raise ValueError(f"Invalid regex pattern for intent '{intent}'.") from exc
        return compiled

    def _recognize_intent(self, message: str) -> Optional[str]:
        """
        Identify the intent of a user message.

        Parameters
        ----------
        message : str
            The raw user input.

        Returns
        -------
        Optional[str]
            The name of the matching intent, or ``None`` if no match is found.
        """
        for intent, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(message):
                    logger.debug("Message matched intent '%s' with pattern '%s'.", intent, pattern.pattern)
                    return intent
        logger.debug("No intent matched for message: %s", message)
        return None

    def _generate_response(self, intent: str, message: str) -> str:
        """
        Produce a response string for a recognized intent.

        Parameters
        ----------
        intent : str
            The recognized intent name.
        message : str
            The original user message (may be used for placeholder substitution).

        Returns
        -------
        str
            A response selected from the intent's response pool.

        Raises
        ------
        KeyError
            If the intent is not defined in the internal intent dictionary.
        """
        try:
            responses = self._intents[intent]["responses"]
        except KeyError as exc:
            logger.error("Intent '%s' not found in intents dictionary.", intent)
            raise

        # Simple random choice without external dependencies
        response_template = responses[0] if len(responses) == 1 else responses[hash(message) % len(responses)]

        # Placeholder handling (e.g., current time)
        if "{time}" in response_template:
            current_time = datetime.datetime.now().strftime("%H:%M")
            response = response_template.replace("{time}", current_time)
        else:
            response = response_template

        logger.debug("Generated response for intent '%s': %s", intent, response)
        return response

    def _add_to_history(self, user_msg: str, bot_msg: str) -> None:
        """
        Record a user‑bot exchange in the conversation history.

        Parameters
        ----------
        user_msg : str
            Message sent by the user.
        bot_msg : str
            Message generated by the bot.
        """
        record = MessageRecord(timestamp=datetime.datetime.utcnow(),
                               user_message=user_msg,
                               bot_message=bot_msg)
        with self._history_lock:
            self._history.append(record)
        logger.debug("Added to history: %s", record)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def process_message(self, message: str) -> str:
        """
        Process an incoming user message and return the bot's reply.

        Parameters
        ----------
        message : str
            The user's input text.

        Returns
        -------
        str
            The chatbot's response.

        Raises
        ------
        TypeError
            If ``message`` is not a string.
        ValueError
            If ``message`` is an empty string after stripping.
        """
        if not isinstance(message, str):
            logger.error("Invalid input type: expected str, got %s.", type(message).__name__)
            raise TypeError("Message must be a string.")
        stripped = message.strip()
        if not stripped:
            logger.error("Received empty or whitespace‑only message.")
            raise ValueError("Message cannot be empty.")

        intent = self._recognize_intent(stripped)
        if intent:
            try:
                response = self._generate_response(intent, stripped)
            except Exception as exc:  # Catch unexpected errors in response generation
                logger.exception("Error generating response for intent '%s'.", intent)
                response = self._fallback_response
        else:
            response = self._fallback_response

        self._add_to_history(stripped, response)
        return response

    def get_history(self, limit: Optional[int] = None) -> List[Tuple[datetime.datetime, str, str]]:
        """
        Retrieve the conversation history.

        Parameters
        ----------
        limit : Optional[int]
            Maximum number of recent exchanges to return. If ``None``, returns all.

        Returns
        -------
        List[Tuple[datetime.datetime, str, str]]
            A list of tuples containing (timestamp, user_message, bot_message).
        """
        with self._history_lock:
            sliced = self._history[-limit:] if limit is not None else self._history[:]
            history = [(rec.timestamp, rec.user_message, rec.bot_message) for rec in sliced]
        logger.debug("Returned %d history record(s).", len(history))
        return history

    def clear_history(self) -> None:
        """
        Remove all stored conversation records.

        This method is thread‑safe and logs the operation.
        """
        with self._history_lock:
            self._history.clear()
        logger.info("Conversation history cleared.")


# --------------------------------------------------------------------------- #
# Convenience function for quick one‑off usage
# --------------------------------------------------------------------------- #
def chat(message: str, bot: Optional[ChatBot] = None) -> str:
    """
    One‑line helper that creates a temporary ``ChatBot`` (if none supplied)
    and returns the bot's reply to ``message``.

    Parameters
    ----------
    message : str
        User input.
    bot : Optional[ChatBot]
        Existing chatbot instance to reuse. If omitted, a new instance is created.

    Returns
    -------
    str
        Bot response.
    """
    if bot is None:
        bot = ChatBot()
    return bot.process_message(message)


__all__ = ["ChatBot", "chat", "MessageRecord"]