import re
import html
import logging
from typing import Dict, List, Optional, Tuple

# Optional: use nltk for word tokenization and stopwords (fallback if available)
try:
    import nltk
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    NLTK_AVAILABLE = True
    # Ensure required nltk data is downloaded (run once)
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
except ImportError:
    NLTK_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class IntentRule:
    """
    Represents a single intent with patterns and responses.

    Attributes:
        name (str): The intent name identifier.
        patterns (List[str]): List of regex patterns to match user input.
        responses (List[str]): List of possible responses for this intent.
    """

    def __init__(self, name: str, patterns: List[str], responses: List[str]) -> None:
        """
        Initialize an IntentRule.

        Args:
            name: Intent name.
            patterns: Regex patterns (case-insensitive matching).
            responses: Response strings (can include {name} placeholder for personalization).

        Raises:
            ValueError: If name, patterns, or responses are empty.
        """
        if not name:
            raise ValueError("Intent name must not be empty")
        if not patterns:
            raise ValueError("Intent must have at least one pattern")
        if not responses:
            raise ValueError("Intent must have at least one response")

        self.name = name
        self.patterns = patterns
        self.responses = responses

    def compile_patterns(self) -> List[re.Pattern]:
        """
        Compile regex patterns for efficient matching.

        Returns:
            List of compiled regex patterns.
        """
        compiled = []
        for pattern in self.patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.error(f"Invalid regex pattern '{pattern}': {e}")
                raise
        return compiled


class RuleBasedChatbot:
    """
    A simple rule-based chatbot with intent recognition, response generation,
    conversation history, and fallback responses.

    Security features:
        - Input sanitization (strip, escape HTML)
        - Use of compiled regex (safe from ReDoS with small patterns)
        - Logging instead of printing sensitive info
    """

    def __init__(self, intents: List[IntentRule], fallback_responses: List[str]) -> None:
        """
        Initialize the chatbot with a list of defined intents and fallback responses.

        Args:
            intents: List of IntentRule objects defining the chatbot's capabilities.
            fallback_responses: List of generic responses for unrecognized intents.

        Raises:
            ValueError: If intents list is empty.
        """
        if not intents:
            raise ValueError("At least one intent must be defined")

        self._intents: List[IntentRule] = intents
        self._fallback_responses: List[str] = fallback_responses
        self._conversation_history: List[Dict[str, str]] = []  # each entry: {"user": ..., "bot": ...}
        self._compiled_intents: List[Tuple[str, List[re.Pattern], List[str]]] = self._compile_intents()

    def _compile_intents(self) -> List[Tuple[str, List[re.Pattern], List[str]]]:
        """
        Pre-compile all intent patterns for performance.

        Returns:
            List of tuples (intent_name, compiled_patterns, responses).
        """
        compiled = []
        for intent in self._intents:
            try:
                compiled_patterns = intent.compile_patterns()
            except re.error:
                # If invalid pattern, skip this intent (or raise)
                logger.warning(f"Intent '{intent.name}' has invalid patterns and will be skipped")
                continue
            compiled.append((intent.name, compiled_patterns, intent.responses))
        return compiled

    def _sanitize_input(self, user_input: str) -> str:
        """
        Sanitize user input to prevent injection attacks and trim whitespace.

        Args:
            user_input: Raw user input.

        Returns:
            Sanitized string.
        """
        # Strip leading/trailing whitespace and null bytes
        cleaned = user_input.strip().strip('\x00')
        # Escape HTML characters to prevent XSS if responses are displayed in web
        cleaned = html.escape(cleaned, quote=True)
        # Limit length to avoid excessive memory usage
        max_len = 1000
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len]
            logger.info("Input truncated to %d characters", max_len)
        return cleaned

    def _preprocess_text(self, text: str) -> str:
        """
        Optionally perform basic NLP preprocessing (lowercase, remove punctuation).

        If nltk is available, tokenize and remove stopwords for better pattern matching.
        Otherwise, just lowercase and strip punctuation.

        Args:
            text: Input text.

        Returns:
            Preprocessed text.
        """
        # Always lowercase
        text = text.lower()
        if NLTK_AVAILABLE:
            try:
                tokens = word_tokenize(text)
                stop_words = set(stopwords.words('english'))
                # Remove punctuation tokens and stopwords (optional, keep some for patterns)
                filtered = [token for token in tokens if token.isalpha() and token not in stop_words]
                return " ".join(filtered)
            except Exception as e:
                logger.warning("NLTK preprocessing failed: %s. Falling back to simple method.", e)
        # Fallback: remove non-alphanumeric characters (except spaces)
        return re.sub(r'[^\w\s]', '', text)

    def recognize_intent(self, user_input: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Recognize intent from user input by matching compiled patterns.

        Args:
            user_input: Sanitized user input string.

        Returns:
            Tuple (intent_name, matched_response) where intent_name is None for fallback,
            and matched_response is a response string or None if no pattern matched.
        """
        preprocessed = self._preprocess_text(user_input)
        # Use both original and preprocessed for matching (preprocessed for robustness)
        candidates = [user_input.lower(), preprocessed] if preprocessed else [user_input.lower()]

        for intent_name, patterns, responses in self._compiled_intents:
            for candidate in candidates:
                for pattern in patterns:
                    if pattern.search(candidate):
                        # Return the first matching intent and a randomly selected response
                        import random
                        response = random.choice(responses)
                        logger.info("Intent '%s' recognized with pattern '%s'", intent_name, pattern.pattern)
                        return intent_name, response

        # No intent matched
        logger.info("No intent recognized for input: %s", user_input[:50])
        return None, None

    def generate_response(self, user_input: str, user_name: str = "User") -> str:
        """
        Generate a response for the given user input.

        Steps:
            1. Sanitize input.
            2. Recognize intent.
            3. If intent found, use its response (optionally personalize with user name).
            4. If not found, pick a fallback response.

        Args:
            user_input: Raw input from user.
            user_name: Optional name for personalization (default "User").

        Returns:
            Bot response string.
        """
        # Sanitize input
        try:
            sanitized_input = self._sanitize_input(user_input)
        except Exception as e:
            logger.error("Input sanitization failed: %s", e)
            return "I'm sorry, I couldn't process that input."

        # Recognize intent
        try:
            intent_name, response = self.recognize_intent(sanitized_input)
        except Exception as e:
            logger.error("Intent recognition failed: %s", e)
            self._add_to_history(user_input, "Sorry, an internal error occurred.")
            return "Sorry, something went wrong while understanding you."

        # If no intent matched, use fallback
        if response is None:
            import random
            if self._fallback_responses:
                response = random.choice(self._fallback_responses)
            else:
                response = "I'm not sure how to respond to that."
            logger.info("Fallback response used.")

        # Personalize response with user name if placeholder exists
        try:
            response = response.format(name=user_name)
        except KeyError:
            # Ignore if placeholder {name} not in response
            pass

        # Add to conversation history
        self._add_to_history(user_input, response)
        return response

    def _add_to_history(self, user_input: str, bot_response: str) -> None:
        """
        Append a turn to the conversation history.

        Args:
            user_input: The user's message.
            bot_response: The bot's response.
        """
        self._conversation_history.append({
            "user": user_input,
            "bot": bot_response
        })
        # Keep history limited to last 100 messages to avoid memory issues
        if len(self._conversation_history) > 100:
            self._conversation_history.pop(0)
            logger.info("Conversation history trimmed to last 100 entries.")

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Return a copy of the conversation history.

        Returns:
            List of dicts with keys 'user' and 'bot'.
        """
        return self._conversation_history.copy()

    def clear_history(self) -> None:
        """Clear all conversation history."""
        self._conversation_history.clear()
        logger.info("Conversation history cleared.")


# ---------- Example usage / simple chat loop ----------
def main() -> None:
    """
    Demonstrate the chatbot with a predefined set of intents and a command-line interface.
    Press Ctrl+C or type 'quit' to exit.
    """
    # Define intents (patterns: regex, responses: list of strings)
    intents = [
        IntentRule(
            name="greeting",
            patterns=[r"\bhello\b", r"\bhi\b", r"\bhey\b", r"\bgood\s*morning\b"],
            responses=["Hello {name}!", "Hi there!", "Greetings!"]
        ),
        IntentRule(
            name="goodbye",
            patterns=[r"\bbye\b", r"\bgoodbye\b", r"\bsee\s*you\b", r"\blater\b"],
            responses=["Goodbye {name}!", "See you later!", "Bye!"]
        ),
        IntentRule(
            name="how_are_you",
            patterns=[r"\bhow\s+are\s+you\b", r"\bhow's\s+it\b", r"\bhow\s*go(es|ing)\b"],
            responses=["I'm doing great, thanks for asking!", "All good here!", "I'm fine, how about you?"]
        ),
        IntentRule(
            name="name",
            patterns=[r"\bwhat(?:'s| is)\s*your\s*name\b", r"\bwho\s+are\s+you\b"],
            responses=["I'm a simple rule-based chatbot.", "You can call me ChatBot."]
        ),
        IntentRule(
            name="help",
            patterns=[r"\bhelp\b", r"\bwhat\s+can\s+you\s+do\b", r"\bcommands\b"],
            responses=["I can greet you, say goodbye, answer how I am, or tell you my name. Try asking about the weather (I'll use a fallback)."]
        )
    ]

    fallback_responses = [
        "I'm sorry, I don't understand that yet. Can you rephrase?",
        "I'm not sure what you mean. Try asking about my name or saying hello.",
        "Hmm, I don't have an answer for that. Perhaps ask something else?"
    ]

    # Create chatbot instance
    try:
        chatbot = RuleBasedChatbot(intents, fallback_responses)
    except ValueError as e:
        logger.error("Failed to create chatbot: %s", e)
        return

    print("Welcome to the Rule-Based Chatbot! Type 'quit' to exit.")
    history = chatbot.get_conversation_history()  # start empty

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if user_input.lower() in ("quit", "exit", "stop"):
            print("ChatBot: Goodbye!")
            break

        # Generate response (includes sanitization, intent recognition, fallback)
        response = chatbot.generate_response(user_input, user_name="User")
        print(f"ChatBot: {response}")

        # Optionally print conversation length
        # print(f"(History length: {len(chatbot.get_conversation_history())})")


if __name__ == "__main__":
    main()