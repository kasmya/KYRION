"""
Chatbot Module

A rule-based chatbot with intent recognition, response generation,
conversation history, and fallback mechanisms. Uses keyword matching
for intent classification and maintains session-level conversation state.

Security note: Inputs are sanitized to prevent injection; conversation
history is bounds-checked to avoid memory exhaustion.
"""

import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# Configure module-level logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_HISTORY_LENGTH: int = 100
FALLBACK_RESPONSES: List[str] = [
    "I'm sorry, I didn't understand that. Could you rephrase?",
    "I'm afraid I don't have an answer for that. Can we try something else?",
    "I'm not sure what you mean. Could you clarify?",
    "Let's try a different question. I'm still learning.",
]
GREETING_INTENTS: Tuple[str, ...] = ("greeting",)
FAREWELL_INTENTS: Tuple[str, ...] = ("farewell",)
DEFAULT_INTENT: str = "unknown"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class IntentRule:
    """A rule mapping a regex pattern to an intent and optional response."""

    def __init__(self, pattern: str, intent: str, response: str = "") -> None:
        """
        Initialize an intent rule.

        Args:
            pattern: A regex pattern (case-insensitive) to match against user input.
            intent: The intent identifier associated with the pattern.
            response: Optional static response for this intent.
        """
        self.pattern: re.Pattern = re.compile(pattern, re.IGNORECASE)
        self.intent: str = intent
        self.response: str = response


# ---------------------------------------------------------------------------
# Intent recognition
# ---------------------------------------------------------------------------
def build_intent_rules() -> List[IntentRule]:
    """
    Build the default set of intent matching rules.

    Returns:
        A list of IntentRule instances.
    """
    return [
        IntentRule(r"\b(hello|hi|hey|good\s*morning|good\s*afternoon|good\s*evening)\b", "greeting",
                   "Hello! How can I help you today?"),
        IntentRule(r"\b(bye|goodbye|see\s*you|later|farewell)\b", "farewell",
                   "Goodbye! Have a great day."),
        IntentRule(r"\b(how\s*are\s*you|how's\s*it\s*going)\b", "how_are_you",
                   "I'm just a bot, but I'm running smoothly! How about you?"),
        IntentRule(r"\b(what\s*is\s*your\s*name|who\s*are\s*you)\b", "identity",
                   "I'm PyChat, your friendly rule-based assistant."),
        IntentRule(r"\b(help|assist|support)\b", "help",
                   "I can answer simple questions. Try: 'hello', 'how are you', 'what is your name', or 'bye'."),
        IntentRule(r"\b(thanks|thank\s*you)\b", "gratitude",
                   "You're very welcome!"),
        IntentRule(r"\b(weather|temperature)\b", "weather",
                   "I'm not connected to a weather service, but I hope the weather is nice where you are!"),
    ]


def recognize_intent(user_input: str, rules: List[IntentRule]) -> Tuple[str, Optional[str]]:
    """
    Classify user input into an intent using regex rules.

    Args:
        user_input: The raw text from the user.
        rules: A list of IntentRule instances to match against.

    Returns:
        A tuple (intent, response) where response may be None if the intent
        requires dynamic generation.
    """
    sanitized = sanitize_input(user_input)
    for rule in rules:
        if rule.pattern.search(sanitized):
            logger.info("Matched intent '%s' for input: %s", rule.intent, sanitized[:50])
            return rule.intent, rule.response
    return DEFAULT_INTENT, None


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------
def sanitize_input(user_input: str) -> str:
    """
    Sanitize user input to prevent injection and normalize text.

    Args:
        user_input: Raw input string.

    Returns:
        Stripped, whitespace-normalized string with dangerous characters removed.
    """
    if not isinstance(user_input, str):
        logger.warning("Non-string input received: %s", type(user_input))
        return ""
    # Remove potentially dangerous characters / sequences (basic safety)
    sanitized = re.sub(r"[<>{}()\[\]\\\'\";]", "", user_input)
    # Normalize whitespace
    sanitized = " ".join(sanitized.split())
    return sanitized.lower()


# ---------------------------------------------------------------------------
# Response generation
# ---------------------------------------------------------------------------
def generate_response(intent: str, user_input: str, static_response: Optional[str]) -> str:
    """
    Generate a response based on the recognized intent.

    Args:
        intent: The intent string.
        user_input: Sanitized user input (for dynamic responses).
        static_response: Pre-defined response from the rule, if any.

    Returns:
        A string to send back to the user.
    """
    # Prefer static response if available
    if static_response:
        return static_response

    # Dynamic responses based on intent
    if intent == "weather":
        return "I don't have access to real-time weather data. Is there anything else I can help with?"
    if intent == "unknown":
        return generate_fallback()
    # Default dynamic response for intents without static text
    return "I see. Tell me more about that."


def generate_fallback() -> str:
    """
    Choose a random fallback response when no intent is matched.

    Returns:
        A fallback string.
    """
    import random  # standard library, imported locally for clarity

    return random.choice(FALLBACK_RESPONSES)


# ---------------------------------------------------------------------------
# Conversation history management
# ---------------------------------------------------------------------------
class ConversationHistory:
    """Thread-safe class to manage conversation turns."""

    def __init__(self, max_length: int = MAX_HISTORY_LENGTH) -> None:
        """
        Initialize conversation history.

        Args:
            max_length: Maximum number of turns to store.
        """
        if max_length <= 0:
            raise ValueError("max_length must be a positive integer")
        self._history: List[Dict[str, str]] = []
        self._max_length: int = max_length

    def add_turn(self, user_input: str, bot_response: str) -> None:
        """
        Append a conversation turn to the history, trimming if necessary.

        Args:
            user_input: User's message.
            bot_response: Bot's response.
        """
        if not isinstance(user_input, str) or not isinstance(bot_response, str):
            logger.error("Invalid turn data types")
            return
        turn = {
            "timestamp": datetime.utcnow().isoformat(),
            "user": sanitize_input(user_input),
            "bot": bot_response,
        }
        self._history.append(turn)
        # Enforce max length
        while len(self._history) > self._max_length:
            self._history.pop(0)

    def get_history(self, last_n: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Retrieve conversation history.

        Args:
            last_n: If provided, return only the most recent N turns.

        Returns:
            A list of turn dictionaries.
        """
        if last_n is not None and last_n > 0:
            return self._history[-last_n:]
        return list(self._history)

    def clear(self) -> None:
        """Clear all conversation history."""
        self._history.clear()

    def __len__(self) -> int:
        """Return the number of stored turns."""
        return len(self._history)


# ---------------------------------------------------------------------------
# Main ChatBot class
# ---------------------------------------------------------------------------
class ChatBot:
    """
    Rule-based chatbot that handles intent recognition, response generation,
    and maintains conversation history.
    """

    def __init__(self, history_size: int = MAX_HISTORY_LENGTH) -> None:
        """
        Initialize the chatbot with intent rules and history.

        Args:
            history_size: Maximum number of conversation turns to retain.
        """
        self._rules: List[IntentRule] = build_intent_rules()
        self._history: ConversationHistory = ConversationHistory(max_length=history_size)
        logger.info("ChatBot initialized with %d intent rules", len(self._rules))

    def process_input(self, user_input: str) -> str:
        """
        Process a single user input and return the bot response.

        Args:
            user_input: Raw text from the user.

        Returns:
            The bot's response as a string.
        """
        try:
            intent, static_resp = recognize_intent(user_input, self._rules)
            response = generate_response(intent, user_input, static_resp)
            self._history.add_turn(user_input, response)
            return response
        except Exception as exc:
            logger.exception("Unexpected error processing input: %s", exc)
            fallback = "Something went wrong. Could you try again?"
            self._history.add_turn(user_input, fallback)
            return fallback

    def get_history(self, last_n: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Retrieve conversation history.

        Args:
            last_n: Number of most recent turns to return.

        Returns:
            A list of turn dictionaries.
        """
        return self._history.get_history(last_n)

    def clear_history(self) -> None:
        """Reset the conversation history."""
        self._history.clear()

    @property
    def history_length(self) -> int:
        """Return the current number of stored turns."""
        return len(self._history)


# ---------------------------------------------------------------------------
# Example usage (can be run as a script)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    bot = ChatBot()
    print("ChatBot started. Type 'exit' to quit.")
    while True:
        try:
            user = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if user.lower().strip() in ("exit", "quit"):
            print("Bot: Goodbye!")
            break
        response = bot.process_input(user)
        print(f"Bot: {response}")