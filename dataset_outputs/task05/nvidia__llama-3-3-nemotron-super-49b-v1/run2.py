"""
ChatBot Implementation with Intent Recognition and Response Generation
====================================================================

Features:
- Intent Recognition
- Response Generation
- Conversation History
- Fallback Responses for Unrecognised Intents

Dependencies:
- Standard Library
- `transformers` for Pre-trained Language Model
- `nltk` for NLP Tasks

Security and Best Practices:
- Input Validation
- Error Handling
- Type Hints and Docstrings
"""

import logging
from typing import Dict, List, Optional
from transformers import pipelines, AutoModelForSequenceClassification, AutoTokenizer
import nltk
from nltk.tokenize import word_tokenize
import re

# Initialize Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DownloadRequired NLTK Data
nltk.download('punkt')

class ChatBot:
    """
    A ChatBot class with intent recognition and response generation capabilities.
    """

    def __init__(self, model_name: str = "distilbert-base-uncased-finetuned-sst-2-0"):
        """
        Initialize the ChatBot with a pre-trained language model.

        Args:
        - model_name (str): Name of the Hugging Face model to use for intent recognition.
        """
        self.model_name = model_name
        self.pipeline = pipelines("zero-shot-classification", model=model_name)
        self.tokenizer = AutoTokenizer.from_prepared_model(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.conversation_history: List[str] = []
        self.intents: Dict[str, List[str]] = {
            "greeting": ["hello", "hi", "hey"],
            "goodbye": ["bye", "see you later"],
            # Add more intents as needed
        }
        self.responses: Dict[str, List[str]] = {
            "greeting": ["Hello! How can I assist you?", "Hi, what's on your mind?"],
            "goodbye": ["See you later!", "Goodbye!"],
            "fallback": ["Sorry, I didn't understand that.", "Could you please rephrase?"],
        }

    def _validate_input(self, message: str) -> bool:
        """
        Validate user input to prevent common security vulnerabilities.

        Args:
        - message (str): User's message.

        Returns:
        - bool: True if input is valid, False otherwise.
        """
        # Basic Input Validation (e.g., against XSS, SQL Injection patterns)
        if re.search(r"[<>;']", message):
            logger.warning("Potentially malicious input detected.")
            return False
        return True

    def recognize_intent(self, message: str) -> Optional[str]:
        """
        Recognize the intent behind the user's message.

        Args:
        - message (str): User's message.

        Returns:
        - Optional[str]: Identified intent or None if unrecognised.
        """
        if not self._validate_input(message):
            return None  # Invalid input
        # Simple Intent Recognition using Pre-defined Intents
        for intent, keywords in self.intents.items():
            if any(keyword in word_tokenize(message).lower() for keyword in keywords):
                return intent
        # Fallback to Zero-Shot Classification if no simple match
        try:
            result = self.pipeline(message, self.intents.keys())
            return result["label"]
        except Exception as e:
            logger.error(f"Intent recognition failed: {e}")
            return None

    def generate_response(self, intent: str) -> str:
        """
        Generate a response based on the identified intent.

        Args:
        - intent (str): Identified intent.

        Returns:
        - str: Generated response.
        """
        if intent in self.responses:
            # Simple Response Selection (e.g., random or based on history)
            return self.responses[intent][0]  # For simplicity, always pick the first response
        else:
            # Fallback Response
            return self.responses["fallback"][0]

    def respond(self, message: str) -> str:
        """
        Main method to handle user message and return a response.

        Args:
        - message (str): User's message.

        Returns:
        - str: ChatBot's response.
        """
        if not message:  # Check for empty input
            return self.responses["fallback"][0]
        self.conversation_history.append(message)
        intent = self.recognize_intent(message)
        if intent:
            response = self.generate_response(intent)
        else:
            response = self.generate_response("fallback")
        self.conversation_history.append(response)  # Log response in conversation history
        return response

def main():
    """
    Example Usage of the ChatBot.
    """
    chatbot = ChatBot()
    
    while True:
        message = input("User: ")
        if message.lower() == "quit":
            break
        response = chatbot.respond(message)
        print("ChatBot:", response)

if __name__ == "__main__":
    main()