from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Tuple
import logging
import nltk
from nltk.stem import WordNetLemmatizer
from transformers import pipeline, set_tokenizers_max_length
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import json

# Initialize NLTK data (download if not present)
nltk.download('wordnet')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Intent(Enum):
    """Supported intents for the chatbot."""
    GREETING = "greeting"
    FAREWELL = "farewell"
    ASK_HELP = "ask_help"
    UNKNOWN = "unknown"

@dataclass
class Message:
    """Represents a message in the conversation."""
    text: str
    intent: Intent

class Chatbot:
    """
    A simple chatbot with intent recognition and response generation.

    Attributes:
    - model_name (str): Name of the pre-trained model for intent classification.
    - tokenizer (AutoTokenizer): Tokenizer for the model.
    - classifier (pipeline): Pipeline for text classification.
    - conversation_history (List[Message]): Stores the conversation history.
    - lemmatizer (WordNetLemmatizer): For lemmatization of words in rules-based approach.
    """

    def __init__(self, model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"):
        """
        Initializes the chatbot with a pre-trained model.

        Args:
        - model_name (str): Name of the pre-trained model.
        """
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        set_tokenizers_max_length(self.tokenizer, 512)  # Set max length to avoid truncation issues
        self.classifier = pipeline("text-classification", model=model_name, tokenizer=self.tokenizer)
        self.conversation_history = []
        self.lemmatizer = WordNetLemmatizer()
        self.intent_mappings = {
            "I'm glad you're here": Intent.GREETING,
            "See you later": Intent.FAREWELL,
            "Do you understand": Intent.ASK_HELP
        }
        self.response_generator = {
            Intent.GREETING: self._generate_greeting_response,
            Intent.FAREWELL: self._generate_farewell_response,
            Intent.ASK_HELP: self._generate_help_response,
            Intent.UNKNOWN: self._generate_fallback_response
        }

    def _normalize_text(self, text: str) -> str:
        """Lemmatizes the input text for rules-based intent matching."""
        words = nltk.word_tokenize(text)
        lemmatized_words = [self.lemmatizer.lemmatize(word.lower()) for word in words]
        return ' '.join(lemmatized_words)

    def recognize_intent(self, message: str) -> Intent:
        """
        Recognizes the intent behind the input message.

        First, attempts to match using a rules-based approach for demo simplicity.
        Falls back to the pre-trained model if no match is found.

        Args:
        - message (str): The input message.

        Returns:
        - Intent: The recognized intent.
        """
        try:
            # Rules-based approach for demo (normally, you'd use the model directly or a dedicated NLU service)
            normalized_message = self._normalize_text(message)
            for keyword, intent in self.intent_mappings.items():
                if any(word in normalized_message for word in keyword.split()):
                    return intent

            # Fallback to pre-trained model for intent recognition
            classification = self.classifier(message)[0]
            # Map model's labels to our Intent enum (assuming labels are exactly matching)
            predicted_intent = Intent(classification["label"].split("_")[-1].upper())
            logger.info(f"Intent recognized via model: {predicted_intent}")
            return predicted_intent

        except Exception as e:
            logger.error(f"Intent recognition failed: {e}")
            return Intent.UNKNOWN

    def _generate_response(self, intent: Intent) -> str:
        """Generates a response based on the intent."""
        return self.response_generator.get(intent, self._generate_fallback_response)()

    def _generate_greeting_response(self) -> str:
        """Generates a greeting response."""
        return "Hello! How can I assist you today?"

    def _generate_farewell_response(self) -> str:
        """Generates a farewell response."""
        return "Goodbye! It was nice chatting with you."

    def _generate_help_response(self) -> str:
        """Generates a help response."""
        return "Of course! I'm here to help with questions or tasks."

    def _generate_fallback_response(self) -> str:
        """Generates a fallback response for unrecognized intents."""
        return "Sorry, I didn't understand that. Could you please rephrase?"

    def respond(self, message: str) -> Tuple[str, Intent]:
        """
        Generates a response to the input message.

        Args:
        - message (str): The input message.

        Returns:
        - Tuple[str, Intent]: A tuple containing the response and the recognized intent.
        """
        try:
            intent = self.recognize_intent(message)
            response = self._generate_response(intent)
            self.conversation_history.append(Message(message, intent))
            return response, intent
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._generate_fallback_response(), Intent.UNKNOWN

    def get_conversation_history(self) -> List[Message]:
        """Returns the conversation history."""
        return self.conversation_history

# Example Usage
if __name__ == "__main__":
    chatbot = Chatbot()

    while True:
        user_input = input("User: ")
        if user_input.lower() == "quit":
            break
        response, intent = chatbot.respond(user_input)
        print(f"Chatbot: {response} (Intent: {intent})")
        print("Conversation History:")
        for msg in chatbot.get_conversation_history():
            print(f"- {msg.text} : {msg.intent}")
        print()