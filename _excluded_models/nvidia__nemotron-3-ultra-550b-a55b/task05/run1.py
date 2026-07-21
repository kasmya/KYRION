"""
A rule-based chatbot with intent recognition, response generation,
conversation history, and fallback responses.

This module provides a `ChatBot` class that can be used to conduct
text-based conversations. It uses regular expressions for intent
matching and supports extensible intent definitions.
"""

import re
import random
import logging
from typing import List, Dict, Pattern, Optional, Tuple, Any

# Configure module-level logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ChatBotError(Exception):
    """Base exception for chatbot errors."""
    pass


class IntentConfigurationError(ChatBotError):
    """Raised when an intent configuration is invalid."""
    pass


class ChatBot:
    """
    A rule-based chatbot that matches user input to intents using regex patterns
    and generates responses. Maintains conversation history and provides fallback
    responses when no intent matches.
    """

    def __init__(
        self,
        fallback_responses: Optional[List[str]] = None,
        max_history: int = 100
    ) -> None:
        """
        Initialize the chatbot.

        Args:
            fallback_responses: List of fallback responses to use when no intent matched.
                Defaults to a generic list.
            max_history: Maximum number of conversation turns to keep in history.
                Older entries are discarded when the limit is exceeded.

        Raises:
            ValueError: If max_history is not a positive integer.
        """
        if not isinstance(max_history, int) or max_history <= 0:
            raise ValueError("max_history must be a positive integer")

        self._intents: Dict[str, Dict[str, Any]] = {}
        self._compiled_patterns: Dict[str, List[Pattern]] = {}
        self._history: List[Tuple[str, str]] = []
        self._max_history = max_history

        self._fallback_responses = fallback_responses or [
            "I'm not sure I understand. Could you rephrase that?",
            "That's interesting, but I don't have a response for that.",
            "I'm still learning. Can you ask me something else?",
        ]

    def add_intent(
        self,
        name: str,
        patterns: List[str],
        responses: List[str],
        case_sensitive: bool = False
    ) -> None:
        """
        Add a new intent to the chatbot.

        Args:
            name: Unique identifier for the intent.
            patterns: List of regex patterns that trigger this intent.
            responses: List of possible responses for this intent.
            case_sensitive: Whether pattern matching should be case sensitive.

        Raises:
            IntentConfigurationError: If name is duplicate, patterns/responses are empty,
                or a pattern fails to compile.
            ValueError: If patterns or responses are not lists of strings.
        """
        if not isinstance(name, str) or not name:
            raise IntentConfigurationError("Intent name must be a non-empty string")

        if name in self._intents:
            raise IntentConfigurationError(f"Intent '{name}' already exists")

        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            raise ValueError("patterns must be a list of strings")
        if not patterns:
            raise IntentConfigurationError("At least one pattern is required")

        if not isinstance(responses, list) or not all(isinstance(r, str) for r in responses):
            raise ValueError("responses must be a list of strings")
        if not responses:
            raise IntentConfigurationError("At least one response is required")

        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, flags))
            except re.error as exc:
                raise IntentConfigurationError(
                    f"Invalid regex pattern '{pattern}': {exc}"
                ) from exc

        self._intents[name] = {
            "patterns": patterns,
            "responses": responses,
            "case_sensitive": case_sensitive,
        }
        self._compiled_patterns[name] = compiled
        logger.debug("Added intent '%s' with %d patterns", name, len(patterns))

    def remove_intent(self, name: str) -> bool:
        """
        Remove an intent by name.

        Args:
            name: The intent name to remove.

        Returns:
            True if the intent was found and removed, False otherwise.
        """
        if name in self._intents:
            del self._intents[name]
            del self._compiled_patterns[name]
            logger.debug("Removed intent '%s'", name)
            return True
        return False

    def _match_intent(self, user_input: str) -> Optional[str]:
        """
        Find the first intent that matches the user input.

        Args:
            user_input: The user's message.

        Returns:
            The matched intent name, or None if no match.
        """
        for intent_name, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(user_input):
                    logger.debug("Matched intent '%s' with pattern '%s'", intent_name, pattern.pattern)
                    return intent_name
        return None

    def _select_response(self, intent_name: str) -> str:
        """
        Select a random response for the given intent.

        Args:
            intent_name: The name of the matched intent.

        Returns:
            A response string.

        Raises:
            ChatBotError: If intent_name is not found.
        """
        if intent_name not in self._intents:
            raise ChatBotError(f"Intent '{intent_name}' not found")
        responses = self._intents[intent_name]["responses"]
        return random.choice(responses)

    def _get_fallback_response(self) -> str:
        """Select a random fallback response."""
        return random.choice(self._fallback_responses)

    def process_message(self, user_input: str) -> str:
        """
        Process a user message and generate a bot response.

        Args:
            user_input: The user's message. Leading/trailing whitespace is stripped.

        Returns:
            The bot's response.

        Raises:
            ValueError: If user_input is not a string.
        """
        if not isinstance(user_input, str):
            raise ValueError("user_input must be a string")

        cleaned_input = user_input.strip()
        if not cleaned_input:
            response = "Please say something."
        else:
            intent = self._match_intent(cleaned_input)
            if intent:
                response = self._select_response(intent)
            else:
                response = self._get_fallback_response()

        # Update history
        self._history.append((cleaned_input, response))
        if len(self._history) > self._max_history:
            self._history.pop(0)

        logger.info("User: %s | Bot: %s", cleaned_input, response)
        return response

    def get_history(self) -> List[Tuple[str, str]]:
        """
        Get a copy of the conversation history.

        Returns:
            List of (user_message, bot_response) tuples, oldest first.
        """
        return list(self._history)

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._history.clear()
        logger.debug("Conversation history cleared")

    def list_intents(self) -> List[str]:
        """
        Get a list of all registered intent names.

        Returns:
            List of intent names.
        """
        return list(self._intents.keys())

    def get_intent_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration details for a specific intent.

        Args:
            name: The intent name.

        Returns:
            Dictionary with keys 'patterns', 'responses', 'case_sensitive',
            or None if the intent does not exist.
        """
        return self._intents.get(name)


def create_default_chatbot() -> ChatBot:
    """
    Create a chatbot pre-loaded with some basic intents.

    Returns:
        A configured ChatBot instance.
    """
    bot = ChatBot()

    # Greeting intent
    bot.add_intent(
        name="greeting",
        patterns=[
            r"\b(hi|hello|hey|greetings|howdy)\b",
            r"\bgood\s+(morning|afternoon|evening)\b",
        ],
        responses=[
            "Hello! How can I help you today?",
            "Hi there! What can I do for you?",
            "Hey! Nice to see you.",
        ],
    )

    # Farewell intent
    bot.add_intent(
        name="farewell",
        patterns=[
            r"\b(bye|goodbye|see you|farewell|catch you later)\b",
            r"\b(good\s+night|have a good (day|night))\b",
        ],
        responses=[
            "Goodbye! Have a great day!",
            "See you later!",
            "Take care!",
        ],
    )

    # Thanks intent
    bot.add_intent(
        name="thanks",
        patterns=[
            r"\b(thanks|thank you|thx|appreciate it)\b",
        ],
        responses=[
            "You're welcome!",
            "Happy to help!",
            "Anytime!",
        ],
    )

    # Help intent
    bot.add_intent(
        name="help",
        patterns=[
            r"\b(help|assist|support|what can you do)\b",
        ],
        responses=[
            "I can chat with you! Try saying hello, asking how I am, or saying goodbye.",
            "I'm a simple rule-based bot. I respond to greetings, farewells, thanks, and a few other things.",
        ],
    )

    # Identity intent
    bot.add_intent(
        name="identity",
        patterns=[
            r"\b(who are you|what are you|your name)\b",
        ],
        responses=[
            "I'm a rule-based chatbot built for demonstration purposes.",
            "You can call me ChatBot.",
        ],
    )

    return bot


if __name__ == "__main__":
    # Example usage when run as a script
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    chatbot = create_default_chatbot()
    print("ChatBot started. Type 'quit' to exit.")
    print("Try: hello, thanks, who are you, goodbye")

    while True:
        try:
            user_text = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if user_text.lower().strip() in {"quit", "exit", "q"}:
            print("Bot: Goodbye!")
            break

        try:
            bot_reply = chatbot.process_message(user_text)
            print(f"Bot: {bot_reply}")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Error processing message")
            print(f"Bot: Sorry, an error occurred: {exc}")

    # Print conversation history
    print("\n--- Conversation History ---")
    for user_msg, bot_msg in chatbot.get_history():
        print(f"You: {user_msg}")
        print(f"Bot: {bot_msg}")