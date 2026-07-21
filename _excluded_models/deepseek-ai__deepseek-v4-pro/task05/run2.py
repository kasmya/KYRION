"""
chatbot.py -- A rule-based chatbot with intent recognition, response generation,
conversation history, and fallback responses.

Uses only the Python standard library and no external dependencies.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable, Sequence

# Configure module-level logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    """A single message in a conversation."""
    role: str          # "user" or "bot"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, str]:
        """Return a JSON-serializable dictionary representation."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> ChatMessage:
        """Construct a ChatMessage from a dictionary."""
        return cls(
            role=data.get("role", "unknown"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
        )


# ---------------------------------------------------------------------------
# Intent recognition
# ---------------------------------------------------------------------------

class IntentRecognizer:
    """Rule-based intent recognizer using regex patterns and keyword scoring."""

    def __init__(self, intents_spec: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the recognizer with optional intent definitions.

        Args:
            intents_spec: A dictionary mapping intent names to configuration
                that includes 'patterns' (list of regex strings) and
                optional 'keywords' (list of words).
        """
        self._intents: Dict[str, Dict[str, Any]] = {}
        if intents_spec is not None:
            self.load_intents(intents_spec)

    def load_intents(self, intents_spec: Dict[str, Any]) -> None:
        """
        Load or update intent definitions.

        Args:
            intents_spec: Dictionary of intent configurations.

        Raises:
            ValueError: If the specification contains invalid data.
        """
        if not isinstance(intents_spec, dict):
            raise ValueError("intents_spec must be a dictionary")
        for intent_name, config in intents_spec.items():
            if not isinstance(config, dict):
                raise ValueError(f"Intent '{intent_name}' configuration must be a dictionary")
            patterns = config.get("patterns", [])
            keywords = config.get("keywords", [])
            if not isinstance(patterns, list) or not isinstance(keywords, list):
                raise ValueError(
                    f"Intent '{intent_name}' patterns and keywords must be lists"
                )
            compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
            self._intents[intent_name] = {
                "patterns": compiled,
                "keywords": [kw.lower() for kw in keywords],
            }
        logger.info("Loaded %d intents", len(self._intents))

    def recognize(self, text: str) -> Optional[str]:
        """
        Identify the most likely intent for the given text.

        Args:
            text: User input string.

        Returns:
            The name of the matched intent, or None if no match is found.
        """
        if not isinstance(text, str):
            logger.warning("recognize received non-string input: %s", type(text))
            return None

        text_lower = text.lower()
        best_intent: Optional[str] = None
        best_score = 0

        for intent_name, data in self._intents.items():
            score = 0
            # Pattern matching
            for pattern in data["patterns"]:
                if pattern.search(text):
                    score += 10  # pattern match is strong signal
            # Keyword matching
            for kw in data["keywords"]:
                if kw in text_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_intent = intent_name

        if best_intent is None:
            logger.info("No intent matched for input: '%s'", text)
        else:
            logger.info("Recognized intent '%s' with score %d", best_intent, best_score)
        return best_intent


# ---------------------------------------------------------------------------
# Response generation
# ---------------------------------------------------------------------------

class ResponseGenerator:
    """Generates responses based on intent and optional context."""

    def __init__(self, responses_spec: Optional[Dict[str, List[str]]] = None) -> None:
        """
        Initialize with a mapping of intent names to list of response templates.

        Args:
            responses_spec: Dictionary where keys are intent names and values are
                lists of response strings. Templates may contain "{user}" placeholders.
        """
        self._responses: Dict[str, List[str]] = defaultdict(list)
        if responses_spec is not None:
            self.load_responses(responses_spec)

    def load_responses(self, responses_spec: Dict[str, List[str]]) -> None:
        """
        Load or update response templates.

        Args:
            responses_spec: Intent -> [response templates] mapping.

        Raises:
            ValueError: If the spec is invalid.
        """
        if not isinstance(responses_spec, dict):
            raise ValueError("responses_spec must be a dictionary")
        for intent, templates in responses_spec.items():
            if not isinstance(templates, list):
                raise ValueError(f"Templates for intent '{intent}' must be a list")
            self._responses[intent] = templates
        logger.info("Loaded responses for %d intents", len(self._responses))

    def generate(self, intent: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Pick a random response for the given intent and fill placeholders.

        Args:
            intent: The matched intent name.
            context: Optional dictionary with context values (e.g., {"user": "Alice"}).

        Returns:
            The generated response string.
        """
        import random

        templates = self._responses.get(intent, [])
        if not templates:
            logger.warning("No templates for intent '%s', using fallback", intent)
            return "I'm not sure how to respond to that."

        template = random.choice(templates)
        # Safe placeholder substitution using format_map with safe fallback
        if context:
            # Avoid KeyErrors by using a defaultdict that returns the placeholder itself
            safe_context = defaultdict(str, context)
            # Replace only known placeholders
            try:
                response = template.format_map(safe_context)
            except Exception as exc:
                logger.error("Template formatting failed: %s", exc)
                response = template
        else:
            response = template
        return response


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

class ConversationHistory:
    """Thread-safe conversation history store."""

    MAX_HISTORY = 1000  # Prevent unbounded memory growth

    def __init__(self) -> None:
        """Initialize an empty history."""
        self._messages: List[ChatMessage] = []

    def add(self, role: str, content: str) -> None:
        """
        Add a message to the history.

        Args:
            role: "user" or "bot".
            content: The message text.

        Raises:
            ValueError: If role is not valid.
        """
        if role not in ("user", "bot"):
            raise ValueError("role must be 'user' or 'bot'")
        msg = ChatMessage(role=role, content=content)
        self._messages.append(msg)
        # Enforce max size
        if len(self._messages) > self.MAX_HISTORY:
            self._messages = self._messages[-self.MAX_HISTORY:]
        logger.debug("Added %s message: %s", role, content[:50])

    def get_history(self, max_messages: int = 10) -> List[Dict[str, str]]:
        """
        Return recent messages as dictionaries.

        Args:
            max_messages: Maximum number of recent messages to return.

        Returns:
            List of serialized messages.
        """
        return [msg.to_dict() for msg in self._messages[-max_messages:]]

    def clear(self) -> None:
        """Clear the entire conversation history."""
        self._messages.clear()
        logger.info("Conversation history cleared")


# ---------------------------------------------------------------------------
# Fallback handler
# ---------------------------------------------------------------------------

class FallbackHandler:
    """Provides fallback responses when no intent is recognized."""

    def __init__(self, fallbacks: Optional[List[str]] = None) -> None:
        """
        Initialize with a list of fallback response strings.

        Args:
            fallbacks: List of fallback strings. If empty, a default is used.
        """
        self._fallbacks = fallbacks if fallbacks else [
            "I didn't quite understand that.",
            "Could you rephrase?",
            "I'm not sure what you mean.",
            "Let me think about that...",
        ]

    def get(self) -> str:
        """Return a random fallback response."""
        import random
        return random.choice(self._fallbacks)


# ---------------------------------------------------------------------------
# Main chatbot class
# ---------------------------------------------------------------------------

class Chatbot:
    """
    A rule-based chatbot that combines intent recognition, response generation,
    conversation history, and fallback handling.
    """

    def __init__(
        self,
        recognizer: Optional[IntentRecognizer] = None,
        generator: Optional[ResponseGenerator] = None,
        history: Optional[ConversationHistory] = None,
        fallback: Optional[FallbackHandler] = None,
    ) -> None:
        """
        Initialize the chatbot with optional components.

        Args:
            recognizer: Intent recognizer instance.
            generator: Response generator instance.
            history: Conversation history instance.
            fallback: Fallback handler instance.
        """
        self.recognizer = recognizer or IntentRecognizer()
        self.generator = generator or ResponseGenerator()
        self.history = history or ConversationHistory()
        self.fallback = fallback or FallbackHandler()

    def process_message(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Process a single user message and return the bot's response.

        Args:
            user_input: The raw text from the user.
            context: Optional context dictionary for response templates.

        Returns:
            The bot's response string.
        """
        # Input validation
        if not isinstance(user_input, str):
            logger.error("Invalid input type: %s", type(user_input))
            return self.fallback.handle()

        sanitized = user_input.strip()
        if not sanitized:
            return "Please type something."

        # Add user message to history
        try:
            self.history.add("user", sanitized)
        except Exception as exc:
            logger.error("Failed to add user message to history: %s", exc)

        # Recognise intent
        intent = self.recognizer.recognize(sanitized)

        # Generate response
        if intent:
            response = self.generator.generate(intent, context)
        else:
            response = self.fallback.handle()

        # Add bot response to history
        try:
            self.history.add("bot", response)
        except Exception as exc:
            logger.error("Failed to add bot message to history: %s", exc)

        return response

    def get_history(self, max_messages: int = 10) -> List[Dict[str, str]]:
        """Return recent conversation history."""
        return self.history.get_history(max_messages)

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.history.clear()


# ---------------------------------------------------------------------------
# Default intents and responses (can be overridden)
# ---------------------------------------------------------------------------

DEFAULT_INTENTS = {
    "greeting": {
        "patterns": [r"\b(hi|hello|hey|good\s*(morning|afternoon|evening))\b"],
        "keywords": ["hi", "hello", "hey", "greetings"],
    },
    "goodbye": {
        "patterns": [r"\b(bye|goodbye|see\s*you|farewell)\b"],
        "keywords": ["bye", "goodbye", "see you"],
    },
    "thanks": {
        "patterns": [r"\b(thanks|thank\s*you|thx|appreciate)\b"],
        "keywords": ["thanks", "thank you", "appreciate"],
    },
    "help": {
        "patterns": [r"\b(help|support|assist)\b"],
        "keywords": ["help", "support", "assist"],
    },
}

DEFAULT_RESPONSES = {
    "greeting": [
        "Hello! How can I help you today?",
        "Hi there! What can I do for you?",
        "Hey! Nice to meet you.",
    ],
    "goodbye": [
        "Goodbye! Have a great day.",
        "See you later!",
        "Take care!",
    ],
    "thanks": [
        "You're welcome!",
        "Happy to help!",
        "No problem at all.",
    ],
    "help": [
        "I'm a simple chatbot. You can greet me, say goodbye, or ask for help.",
        "I can respond to greetings, goodbyes, thanks, and help requests.",
    ],
}


def create_default_chatbot() -> Chatbot:
    """Factory function that creates a Chatbot pre-loaded with default intents and responses."""
    recognizer = IntentRecognizer(DEFAULT_INTENTS)
    generator = ResponseGenerator(DEFAULT_RESPONSES)
    return Chatbot(recognizer=recognizer, generator=generator)


# ---------------------------------------------------------------------------
# Example interactive runner (not executed on import)
# ---------------------------------------------------------------------------

def main() -> None:
    """Simple interactive loop for testing the chatbot."""
    bot = create_default_chatbot()
    print("Chatbot ready. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if user_input.lower() in ("exit", "quit"):
            print("Bot: Goodbye!")
            break
        response = bot.process_message(user_input)
        print(f"Bot: {response}")


if __name__ == "__main__":
    main()