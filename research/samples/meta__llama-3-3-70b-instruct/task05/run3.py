import logging
from typing import Dict, List
import transformers
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
import torch

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize NLTK data
nltk.download('punkt')
nltk.download('wordnet')

class IntentRecognizer:
    """
    Recognizes the intent behind a user's message.
    """

    def __init__(self, model_name: str):
        """
        Initializes the intent recognizer with a pre-trained model.

        Args:
        model_name (str): The name of the pre-trained model to use.
        """
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def recognize_intent(self, message: str) -> str:
        """
        Recognizes the intent behind a user's message.

        Args:
        message (str): The user's message.

        Returns:
        str: The recognized intent.
        """
        inputs = self.tokenizer(message, return_tensors='pt')
        outputs = self.model(**inputs)
        logits = outputs.logits
        intent = torch.argmax(logits).item()
        return intent

class ResponseGenerator:
    """
    Generates a response to a user's message based on the recognized intent.
    """

    def __init__(self, intents: Dict[int, str]):
        """
        Initializes the response generator with a dictionary of intents and responses.

        Args:
        intents (Dict[int, str]): A dictionary mapping intent IDs to responses.
        """
        self.intents = intents

    def generate_response(self, intent: int) -> str:
        """
        Generates a response to a user's message based on the recognized intent.

        Args:
        intent (int): The recognized intent.

        Returns:
        str: The generated response.
        """
        return self.intents.get(intent, "I didn't understand that.")

class ConversationHistory:
    """
    Keeps track of the conversation history.
    """

    def __init__(self):
        """
        Initializes the conversation history.
        """
        self.history = []

    def add_message(self, message: str):
        """
        Adds a message to the conversation history.

        Args:
        message (str): The message to add.
        """
        self.history.append(message)

    def get_history(self) -> List[str]:
        """
        Gets the conversation history.

        Returns:
        List[str]: The conversation history.
        """
        return self.history

class Chatbot:
    """
    A chatbot that uses a pre-trained language model to recognize intents and generate responses.
    """

    def __init__(self, model_name: str, intents: Dict[int, str]):
        """
        Initializes the chatbot with a pre-trained model and a dictionary of intents and responses.

        Args:
        model_name (str): The name of the pre-trained model to use.
        intents (Dict[int, str]): A dictionary mapping intent IDs to responses.
        """
        self.intent_recognizer = IntentRecognizer(model_name)
        self.response_generator = ResponseGenerator(intents)
        self.conversation_history = ConversationHistory()

    def chat(self, message: str) -> str:
        """
        Chats with the user.

        Args:
        message (str): The user's message.

        Returns:
        str: The chatbot's response.
        """
        try:
            intent = self.intent_recognizer.recognize_intent(message)
            response = self.response_generator.generate_response(intent)
            self.conversation_history.add_message(message)
            return response
        except Exception as e:
            logger.error(f"Error: {e}")
            return "I didn't understand that."

def main():
    # Define the intents and responses
    intents = {
        0: "Hello! How can I help you today?",
        1: "I'm not sure I understand. Can you please rephrase?",
        2: "That's a great question! The answer is..."
    }

    # Create the chatbot
    chatbot = Chatbot("distilbert-base-uncased", intents)

    # Chat with the user
    while True:
        message = input("User: ")
        response = chatbot.chat(message)
        print(f"Chatbot: {response}")

if __name__ == "__main__":
    main()