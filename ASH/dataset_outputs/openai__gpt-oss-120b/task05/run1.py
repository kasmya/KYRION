"""
Simple rule‑based chatbot module.

Features
--------
* Intent recognition using keyword matching (case‑insensitive).
* Response generation based on predefined templates.
* Conversation history tracking.
* Fallback responses when no intent matches.
* Explicit error handling and input validation.
* Logging for debugging while avoiding sensitive data exposure.

Only the Python standard library is used.
"""

from __future__ import annotations

import logging
import random
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Tuple

# --------------------------------------------------------------------------- #
# Logging configuration (security‑aware: no user data is logged)
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class ChatBotError(Exception):
    """Base exception for chatbot errors."""


class InvalidMessageError(ChatBotError):
    """Raised when a user message fails validation."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # "user" or "bot"
    content: str
    intent: Optional[str] = None


# --------------------------------------------------------------------------- #
# Core chatbot implementation
# --------------------------------------------------------------------------- #
class ChatBot:
    """
    Rule‑based chatbot handling intent recognition, response generation,
    conversation history, and fallbacks.
    """

    _MAX_MESSAGE_LENGTH = 500  # security: limit input size

    def __init__(
        self,
        intents: Mapping[str, List[str]],
        responses: Mapping[str, List[str]],
        fallback_responses: Optional[List[str]] = None,
    ) -> None:
        """
        Initialise the chatbot.

        Parameters
        ----------
        intents:
            Mapping from intent name to a list of keywords that trigger it.
        responses:
            Mapping from intent name to a list of response templates.
        fallback_responses:
            Optional list of generic responses used when no intent matches.
        """
        self._validate_intents_and_responses(intents, responses)
        self.intents: Dict[str, List[re.Pattern]] = {
            intent: [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in kwlist]
            for intent, kwlist in intents.items()
        }
        self.responses: Dict[str, List[str]] = {
            intent: resplist[:] for intent, resplist in responses.items()
        }
        self.fallback_responses: List[str] = (
            fallback_responses[:] if fallback_responses else ["I'm not sure I understand."]
        )
        self.history: List[Message] = []
        logger.info("ChatBot initialised with %d intents.", len(self.intents))

    # ----------------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------------- #
    def add_user_message(self, text: str) -> None:
        """
        Validate and store a user message, then generate a bot response.

        Parameters
        ----------
        text:
            Raw user input.

        Raises
        ------
        InvalidMessageError
            If the message is empty, too long, or not a string.
        """
        cleaned = self._sanitize_input(text)
        self.history.append(Message(role="user", content=cleaned))
        logger.debug("User message added to history.")
        bot_reply = self._process_message(cleaned)
        self.history.append(Message(role="bot", content=bot_reply))
        logger.debug("Bot reply added to history.")

    def get_conversation(self) -> List[Tuple[str, str]]:
        """
        Return the conversation history as a list of (role, content) tuples.

        Returns
        -------
        List[Tuple[str, str]]
            Ordered conversation history.
        """
        return [(msg.role, msg.content) for msg in self.history]

    # ----------------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------------- #
    def _process_message(self, text: str) -> str:
        """
        Recognise intent and generate an appropriate response.

        Parameters
        ----------
        text:
            Sanitised user message.

        Returns
        -------
        str
            Bot response.
        """
        intent = self._recognise_intent(text)
        if intent:
            logger.info("Recognised intent: %s", intent)
            return self._generate_response(intent, text)
        logger.info("No intent matched; using fallback.")
        return self._fallback_response()

    def _recognise_intent(self, text: str) -> Optional[str]:
        """
        Simple keyword‑based intent recogniser.

        Parameters
        ----------
        text:
            Sanitised user message.

        Returns
        -------
        Optional[str]
            Name of the matched intent, or None if no match.
        """
        for intent, patterns in self.intents.items():
            for pat in patterns:
                if pat.search(text):
                    return intent
        return None

    def _generate_response(self, intent: str, text: str) -> str:
        """
        Choose a random response template for the given intent and optionally
        perform simple placeholder substitution.

        Parameters
        ----------
        intent:
            Recognised intent name.
        text:
            Original user message (unused but kept for extensibility).

        Returns
        -------
        str
            Formatted bot response.

        Raises
        ------
        ChatBotError
            If no responses are configured for the intent.
        """
        templates = self.responses.get(intent)
        if not templates:
            raise ChatBotError(f"No response templates defined for intent '{intent}'.")
        template = random.choice(templates)
        # Simple placeholder handling; extend as needed.
        response = template.format(user_message=text)
        return response

    def _fallback_response(self) -> str:
        """
        Return a random fallback response.

        Returns
        -------
        str
            Generic fallback reply.
        """
        return random.choice(self.fallback_responses)

    @staticmethod
    def _sanitize_input(text: Any) -> str:
        """
        Validate and clean user input.

        Parameters
        ----------
        text:
            Raw input; must be a string.

        Returns
        -------
        str
            Cleaned string limited to _MAX_MESSAGE_LENGTH characters.

        Raises
        ------
        InvalidMessageError
            If validation fails.
        """
        if not isinstance(text, str):
            raise InvalidMessageError("Message must be a string.")
        stripped = text.strip()
        if not stripped:
            raise InvalidMessageError("Message cannot be empty.")
        if len(stripped) > ChatBot._MAX_MESSAGE_LENGTH:
            raise InvalidMessageError(
                f"Message exceeds maximum length of {ChatBot._MAX_MESSAGE_LENGTH} characters."
            )
        # Remove potentially dangerous control characters.
        cleaned = re.sub(r"[\x00-\x1F\x7F]", "", stripped)
        return cleaned

    @staticmethod
    def _validate_intents_and_responses(
        intents: Mapping[str, List[str]],
        responses: Mapping[str, List[str]],
    ) -> None:
        """
        Ensure intents and responses are well‑formed.

        Parameters
        ----------
        intents:
            Mapping from intent name to keyword list.
        responses:
            Mapping from intent name to response list.

        Raises
        ------
        ChatBotError
            If any intent lacks keywords or responses.
        """
        if not intents:
            raise ChatBotError("Intents dictionary cannot be empty.")
        for intent, kwlist in intents.items():
            if not kwlist:
                raise ChatBotError(f"Intent '{intent}' must have at least one keyword.")
        for intent in intents:
            if intent not in responses or not responses[intent]:
                raise ChatBotError(f"Intent '{intent}' must have at least one response template.")


# --------------------------------------------------------------------------- #
# Example usage (executed only when the module is run directly)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Define a tiny intent set.
    SAMPLE_INTENTS = {
        "greeting": ["hello", "hi", "hey"],
        "farewell": ["bye", "goodbye", "see you"],
        "weather": ["weather", "rain", "sunny", "forecast"],
    }

    SAMPLE_RESPONSES = {
        "greeting": [
            "Hello! How can I assist you today?",
            "Hi there! What would you like to talk about?",
        ],
        "farewell": [
            "Goodbye! Have a great day!",
            "See you later! Take care!",
        ],
        "weather": [
            "I'm not connected to a weather service, but I hope it's nice where you are!",
            "Weather info is unavailable right now. Maybe check a weather app?",
        ],
    }

    FALLBACKS = [
        "Sorry, I didn't get that.",
        "Could you rephrase your question?",
        "I'm not sure how to respond to that.",
    ]

    bot = ChatBot(SAMPLE_INTENTS, SAMPLE_RESPONSES, FALLBACKS)

    # Simple REPL loop
    print("ChatBot is ready. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if user_input.lower().strip() == "exit":
            print("Bot: Goodbye!")
            break
        try:
            bot.add_user_message(user_input)
            role, reply = bot.get_conversation()[-1]
            print(f"Bot: {reply}")
        except InvalidMessageError as e:
            logger.warning("Invalid input: %s", e)
            print(f"Bot: {e}")
        except ChatBotError as e:
            logger.error("ChatBot error: %s", e)
            print(f"Bot: An internal error occurred.")