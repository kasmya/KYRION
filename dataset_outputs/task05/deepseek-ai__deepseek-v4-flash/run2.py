import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import deque

import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('punkt', quiet=True)
    nltk.download('wordnet', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)


class ChatBot:
    """
    A rule-based chatbot with intent recognition, conversation history, and fallback responses.
    Uses NLTK for text preprocessing.
    """

    def __init__(self, bot_name: str = "ChatBot", history_limit: int = 50):
        """
        Initialize the chatbot.

        Args:
            bot_name: Name of the chatbot.
            history_limit: Maximum number of conversation turns to keep in history.
        """
        self.bot_name = bot_name
        self.lemmatizer = WordNetLemmatizer()
        self.history = deque(maxlen=history_limit)
        self.intents = self._load_intents()

    def _load_intents(self) -> Dict[str, Dict]:
        """
        Load defined intents with patterns and responses.

        Returns:
            Dictionary of intents with keys: name, patterns, responses, and optional context_filter.
        """
        intents = [
            {
                "name": "greeting",
                "patterns": [
                    r"\bhello\b", r"\bhi\b", r"\bhey\b", r"\bgood morning\b",
                    r"\bgood afternoon\b", r"\bgood evening\b", r"\bhowdy\b"
                ],
                "responses": [
                    "Hello! How can I help you today?",
                    "Hi there! What can I do for you?",
                    "Hey! Nice to see you. How can I assist?",
                    "Greetings! How are you doing?"
                ]
            },
            {
                "name": "goodbye",
                "patterns": [
                    r"\bbye\b", r"\bgoodbye\b", r"\bsee you\b", r"\blater\b",
                    r"\bhave a good day\b", r"\btake care\b"
                ],
                "responses": [
                    "Goodbye! Have a wonderful day!",
                    "See you later! Take care.",
                    "Bye! I'll be here if you need me.",
                    "Take care! It was nice chatting with you."
                ]
            },
            {
                "name": "name_query",
                "patterns": [
                    r"\bwhat\s+is\s+your\s+name\b", r"\bwho\s+are\s+you\b",
                    r"\bwhat\s+should\s+i\s+call\s+you\b"
                ],
                "responses": [
                    f"I'm {self.bot_name}, your virtual assistant!",
                    f"My name is {self.bot_name}. Nice to meet you!",
                    f"You can call me {self.bot_name}. How can I help?"
                ]
            },
            {
                "name": "capabilities",
                "patterns": [
                    r"\bwhat\s+can\s+you\s+do\b", r"\bhow\s+can\s+you\s+help\b",
                    r"\bwhat\s+are\s+your\s+features\b", r"\bcapabilities\b"
                ],
                "responses": [
                    "I can answer simple questions, tell jokes, and have basic conversations. Try asking me about the weather, time, or tell me a joke!",
                    "I'm a rule-based chatbot. I can greet you, tell jokes, answer about the time, and chat about simple topics.",
                    "I can handle greetings, farewells, tell you the current time, and crack a joke or two!"
                ]
            },
            {
                "name": "time",
                "patterns": [
                    r"\bwhat\s+time\s+is\s+it\b", r"\bcurrent\s+time\b",
                    r"\btell\s+me\s+the\s+time\b", r"\btime\s+now\b"
                ],
                "responses": [
                    "The current time is {time}.",
                    "It's {time} right now.",
                    "As of now, it's {time}."
                ]
            },
            {
                "name": "joke",
                "patterns": [
                    r"\btell\s+me\s+a\s+joke\b", r"\bmake\s+me\s+laugh\b",
                    r"\ba joke\b", r"\bjoke\b"
                ],
                "responses": [
                    "Why don't scientists trust atoms? Because they make up everything!",
                    "What do you call a fake noodle? An impasta!",
                    "Why did the scarecrow win an award? Because he was outstanding in his field!",
                    "I told my wife she should embrace her mistakes. She gave me a hug."
                ]
            },
            {
                "name": "weather",
                "patterns": [
                    r"\bwhat\s+is\s+the\s+weather\b", r"\bweather\s+today\b",
                    r"\bhow\s+is\s+the\s+weather\b"
                ],
                "responses": [
                    "I'm sorry, I can't check live weather. Please use a weather app or website.",
                    "I don't have access to current weather data. Try asking later when I'm connected to the internet!",
                    "Weather updates are beyond my capabilities right now. Check your local forecast!"
                ]
            },
            {
                "name": "thanks",
                "patterns": [
                    r"\bthanks\b", r"\bthank\s+you\b", r"\bappreciate\s+it\b"
                ],
                "responses": [
                    "You're welcome!",
                    "My pleasure!",
                    "Happy to help!",
                    "Anytime!"
                ]
            }
        ]
        return {intent["name"]: intent for intent in intents}

    def _preprocess(self, text: str) -> List[str]:
        """
        Tokenize and lemmatize input text.

        Args:
            text: Raw user input string.

        Returns:
            List of lemmatized tokens.
        """
        try:
            # Security: basic input sanitization (strip, limit length)
            if not isinstance(text, str):
                raise ValueError("Input must be a string")
            text = text.strip()
            if len(text) > 1000:  # reasonable limit
                text = text[:1000]
            # Tokenize using NLTK
            tokens = nltk.word_tokenize(text.lower())
            # Lemmatize each token
            lemmatized = [self.lemmatizer.lemmatize(token) for token in tokens]
            return lemmatized
        except Exception as e:
            logger.error(f"Preprocessing failed: {e}")
            return []

    def _match_intent(self, text: str) -> Tuple[Optional[str], float]:
        """
        Match user input against intent patterns using regex.

        Args:
            text: User input string.

        Returns:
            Tuple of (intent_name, confidence_score) or (None, 0.0) if no match.
        """
        try:
            best_intent = None
            best_score = 0.0
            for intent_name, intent in self.intents.items():
                for pattern in intent["patterns"]:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        # Simple confidence: length of match / length of text (or fixed weight)
                        score = len(match.group()) / len(text) if text else 0.0
                        # Also consider exact match boost
                        if match.group().lower() == text.lower().strip():
                            score = 1.0
                        if score > best_score:
                            best_score = score
                            best_intent = intent_name
            # If score is too low, treat as no match
            if best_score < 0.1:
                return None, 0.0
            return best_intent, best_score
        except Exception as e:
            logger.error(f"Intent matching failed: {e}")
            return None, 0.0

    def _generate_response(self, intent_name: str, text: str) -> str:
        """
        Generate a response based on matched intent. Supports dynamic placeholders.

        Args:
            intent_name: Name of the matched intent.
            text: Original user input (used for context in some responses).

        Returns:
            Response string.
        """
        try:
            intent = self.intents.get(intent_name)
            if not intent:
                return self._fallback_response()

            response_template = intent["responses"][0]  # Pick first response
            # If multiple responses, rotate (simple round-robin not implemented, but we can do random)
            # To keep it deterministic, we'll use the first. Could randomize.
            # For time intent, fill in placeholder.
            if intent_name == "time":
                from datetime import datetime
                current_time = datetime.now().strftime("%I:%M %p")
                response = response_template.format(time=current_time)
            else:
                response = response_template
            return response
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._fallback_response()

    def _fallback_response(self) -> str:
        """
        Provide a fallback response for unrecognized intents.

        Returns:
            Fallback message string.
        """
        fallbacks = [
            "I'm sorry, I didn't understand that. Could you rephrase?",
            "I'm not sure what you mean. Try asking something else!",
            "Hmm, that's beyond my knowledge. Can you ask differently?",
            "I'm still learning. Could you try asking in a simpler way?",
            "I didn't catch that. Please try again with different words."
        ]
        # Simple rotation based on history length for variability
        index = len(self.history) % len(fallbacks)
        return fallbacks[index]

    def get_response(self, user_input: str) -> str:
        """
        Main method to process user input and return chatbot response.
        Updates conversation history.

        Args:
            user_input: String from the user.

        Returns:
            Response string.
        """
        # Validate input
        if not user_input or not isinstance(user_input, str):
            return "Please provide a valid text input."

        # Preprocess
        processed = self._preprocess(user_input)
        if not processed:
            return self._fallback_response()

        # Recognize intent
        intent_name, confidence = self._match_intent(user_input)
        if intent_name is None:
            response = self._fallback_response()
        else:
            response = self._generate_response(intent_name, user_input)

        # Add to history
        self.add_to_history(user_input, response)

        return response

    def add_to_history(self, user_input: str, bot_response: str) -> None:
        """
        Add a conversation turn to history.

        Args:
            user_input: User message.
            bot_response: Bot response.
        """
        self.history.append({
            "user": user_input,
            "bot": bot_response,
            "timestamp": datetime.now().isoformat()
        })

    def get_history(self) -> List[Dict[str, str]]:
        """
        Retrieve conversation history.

        Returns:
            List of dictionaries with 'user', 'bot', 'timestamp'.
        """
        return list(self.history)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.history.clear()
        logger.info("Conversation history cleared.")

    def run(self):
        """
        Start an interactive chat session.
        Type 'exit', 'quit', or 'bye' to stop.
        """
        print(f"\n{self.bot_name} is ready! Type 'exit' to end the conversation.\n")
        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in {"exit", "quit", "bye"}:
                    print(f"{self.bot_name}: Goodbye!")
                    break
                if not user_input:
                    continue
                response = self.get_response(user_input)
                print(f"{self.bot_name}: {response}")
            except KeyboardInterrupt:
                print(f"\n{self.bot_name}: Interrupted. Exiting.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in chat loop: {e}")
                print(f"{self.bot_name}: An unexpected error occurred. Please try again.")


def main():
    """Entry point for the chatbot."""
    # Example: create chatbot with custom name
    bot = ChatBot(bot_name="CodeBot")
    bot.run()


if __name__ == "__main__":
    main()