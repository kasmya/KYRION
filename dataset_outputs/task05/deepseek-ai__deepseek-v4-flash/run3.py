import re
import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

# nltk imports (ensure punkt and wordnet are downloaded)
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer

# ----------------------------------------------------------------------
# Configuration and setup
# ----------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Download required NLTK data (if not present)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet', quiet=True)

# ----------------------------------------------------------------------
# Data models
# ----------------------------------------------------------------------
@dataclass
class IntentPattern:
    """Represents a single intent pattern with associated responses."""
    tag: str
    patterns: List[str]
    responses: List[str]

@dataclass
class ConversationEntry:
    """Stores a single turn in the conversation history."""
    user_input: str
    bot_response: str
    detected_intent: Optional[str] = None

# ----------------------------------------------------------------------
# ChatBot class
# ----------------------------------------------------------------------
class RuleBasedChatBot:
    """
    A rule-based chatbot that uses keyword matching for intent recognition,
    generates responses from predefined templates, maintains conversation history,
    and falls back to a default response when no intent is matched.

    Attributes:
        intents (List[IntentPattern]): List of defined intents.
        lemmatizer (WordNetLemmatizer): NLTK lemmatizer for normalizing input.
        history (List[ConversationEntry]): Conversation history.
        fallback_response (str): Default response when no intent is matched.
    """

    def __init__(self, intents_data: List[Dict[str, any]], fallback_response: str = "I'm sorry, I didn't understand that."):
        """
        Initialize the chatbot with intents data and a fallback response.

        Args:
            intents_data: List of dictionaries, each with keys 'tag', 'patterns', 'responses'.
            fallback_response: Default response for unrecognized intents.

        Raises:
            ValueError: If intents_data is empty or malformed.
        """
        if not intents_data:
            raise ValueError("Intents data cannot be empty.")

        self.intents: List[IntentPattern] = []
        for intent_dict in intents_data:
            if not all(k in intent_dict for k in ('tag', 'patterns', 'responses')):
                raise ValueError(f"Intent data missing required keys: {intent_dict}")
            if not intent_dict['patterns'] or not intent_dict['responses']:
                raise ValueError(f"Intent '{intent_dict.get('tag', 'unknown')}' has empty patterns or responses.")
            self.intents.append(IntentPattern(
                tag=intent_dict['tag'],
                patterns=intent_dict['patterns'],
                responses=intent_dict['responses']
            ))

        self.lemmatizer = WordNetLemmatizer()
        self.history: List[ConversationEntry] = []
        self.fallback_response = fallback_response
        logger.info(f"ChatBot initialized with {len(self.intents)} intents.")

    def _normalize_text(self, text: str) -> str:
        """
        Normalize input text: lowercase, remove punctuation, lemmatize tokens.

        Args:
            text: Raw user input.

        Returns:
            Normalized string of lemmatized tokens separated by spaces.
        """
        # Security: strip extra spaces and sanitize input
        text = text.strip()
        if not text:
            return ""

        # Lowercase
        text = text.lower()

        # Remove punctuation (keep alphanumeric and spaces)
        text = re.sub(r'[^\w\s]', '', text)

        # Tokenize
        try:
            tokens = word_tokenize(text)
        except Exception as e:
            logger.error(f"Tokenization error: {e}")
            return text

        # Lemmatize each token
        lemmatized = [self.lemmatizer.lemmatize(token) for token in tokens]
        return ' '.join(lemmatized)

    def _detect_intent(self, user_input: str) -> Optional[str]:
        """
        Determine the intent tag that best matches the user input.

        Uses priority by the first pattern found in the lemmatized input.

        Args:
            user_input: Raw user input string.

        Returns:
            The tag of the matched intent, or None if no match.
        """
        normalized_input = self._normalize_text(user_input)
        if not normalized_input:
            return None

        for intent in self.intents:
            for pattern in intent.patterns:
                normalized_pattern = self._normalize_text(pattern)
                # Match if the pattern appears as a substring (can be improved with regex)
                if normalized_pattern in normalized_input:
                    return intent.tag
        return None

    def _get_response(self, intent_tag: str) -> str:
        """
        Retrieve a random response for the given intent tag.

        Args:
            intent_tag: The matched intent tag.

        Returns:
            A response string from the corresponding intent's responses list.

        Raises:
            ValueError: If intent tag is not found.
        """
        for intent in self.intents:
            if intent.tag == intent_tag:
                # Use simple round-robin for reproducible behavior (or random if desired)
                # Here we cycle through responses based on history length
                idx = len(self.history) % len(intent.responses)
                return intent.responses[idx]
        raise ValueError(f"Intent tag '{intent_tag}' not found in defined intents.")

    def get_response(self, user_input: str) -> str:
        """
        Main entry point to get a bot response for the user input.

        Handles intent detection, response generation, fallback, and saves to history.

        Args:
            user_input: The raw user input string.

        Returns:
            The bot's response string.

        Raises:
            ValueError: If user_input is empty or contains only whitespace.
        """
        # Input validation and security
        if not user_input or not user_input.strip():
            logger.warning("Empty input received.")
            raise ValueError("User input cannot be empty.")

        # Limit input length to prevent abuse
        if len(user_input) > 500:
            user_input = user_input[:500]
            logger.info("Input truncated to 500 characters.")

        # Detect intent
        intent_tag = self._detect_intent(user_input)
        if intent_tag is None:
            response = self.fallback_response
            logger.debug(f"No intent matched for input, using fallback.")
        else:
            try:
                response = self._get_response(intent_tag)
                logger.debug(f"Matched intent '{intent_tag}', responding: {response}")
            except ValueError as e:
                logger.error(f"Response generation error: {e}")
                response = self.fallback_response
                intent_tag = None  # treat as fallback

        # Save conversation history
        entry = ConversationEntry(
            user_input=user_input,
            bot_response=response,
            detected_intent=intent_tag
        )
        self.history.append(entry)

        # Security: sanitize response output (no HTML/script injection)
        # (responses are predefined, but we still ensure safety)
        response = response.replace('<', '&lt;').replace('>', '&gt;')
        return response

    def get_history(self) -> List[ConversationEntry]:
        """Return the full conversation history."""
        return self.history

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.history.clear()
        logger.info("Conversation history cleared.")

# ----------------------------------------------------------------------
# Example usage and default intents
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Define some sample intents (can be loaded from a JSON file)
    sample_intents = [
        {
            "tag": "greeting",
            "patterns": ["hello", "hi", "good morning", "good evening", "hey"],
            "responses": ["Hello!", "Hi there!", "Greetings!", "How can I help you?"]
        },
        {
            "tag": "goodbye",
            "patterns": ["bye", "goodbye", "see you", "farewell"],
            "responses": ["Goodbye!", "See you later!", "Take care!", "Bye!"]
        },
        {
            "tag": "help",
            "patterns": ["help", "how can you help", "what can you do", "options"],
            "responses": ["I can greet you, say goodbye, or answer questions about the weather.", 
                          "Try saying 'hello' or 'bye'."]
        },
        {
            "tag": "weather",
            "patterns": ["weather", "temperature", "rain", "forecast", "cloudy", "sunny"],
            "responses": ["I'm not connected to a weather API, but you might want to check your local forecast.", 
                          "Weather inquiries are beyond my current abilities."]
        }
    ]

    # Create chatbot instance
    try:
        bot = RuleBasedChatBot(sample_intents)
    except ValueError as e:
        logger.error(f"Failed to create chatbot: {e}")
        exit(1)

    # Interactive loop (safety: limit loop iterations for demo)
    print("ChatBot started. Type 'quit' to exit.\n")
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ("quit", "exit", "stop"):
                print("Bot: Goodbye!")
                break
            response = bot.get_response(user_input)
            print(f"Bot: {response}")
        except ValueError as e:
            print(f"Bot: [Error: {e}]")
        except KeyboardInterrupt:
            print("\nBot: Interrupted. Exiting.")
            break
        except Exception as e:
            logger.exception("Unexpected error in main loop.")
            print("Bot: Something went wrong. Please try again.")

    # Show conversation history
    print("\n--- Conversation History ---")
    for entry in bot.get_history():
        print(f"Intent: {entry.detected_intent} | User: {entry.user_input[:40]}... | Bot: {entry.bot_response[:40]}...")