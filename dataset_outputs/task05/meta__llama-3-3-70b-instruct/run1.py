import nltk
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from typing import Dict, List, Tuple
import logging
import warnings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up warnings
warnings.filterwarnings("ignore")

# Initialize NLTK data
nltk.download('punkt')
nltk.download('wordnet')

class Intent:
    """Represents an intent with a name and a list of keywords."""
    def __init__(self, name: str, keywords: List[str]):
        self.name = name
        self.keywords = keywords

class Chatbot:
    """A simple chatbot with intent recognition, response generation, and conversation history."""
    def __init__(self, model_name: str = "distilbert-base-uncased"):
        """
        Initializes the chatbot with a pre-trained language model.

        Args:
            model_name (str): The name of the pre-trained language model.
        """
        self.model_name = model_name
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.intents: Dict[str, Intent] = {}
        self.conversation_history: List[str] = []
        self.fallback_response = "I didn't understand that. Please try again."
        self.lemmatizer = WordNetLemmatizer()

    def add_intent(self, intent: Intent):
        """
        Adds an intent to the chatbot.

        Args:
            intent (Intent): The intent to add.
        """
        self.intents[intent.name] = intent

    def recognize_intent(self, message: str) -> str:
        """
        Recognizes the intent of a message.

        Args:
            message (str): The message to recognize.

        Returns:
            str: The recognized intent.
        """
        try:
            inputs = self.tokenizer(message, return_tensors="pt")
            outputs = self.model(**inputs)
            logits = outputs.logits
            intent = torch.argmax(logits).item()
            return list(self.intents.keys())[intent]
        except Exception as e:
            logger.error(f"Error recognizing intent: {e}")
            return None

    def generate_response(self, intent: str) -> str:
        """
        Generates a response for an intent.

        Args:
            intent (str): The intent to respond to.

        Returns:
            str: The generated response.
        """
        try:
            # Simple response generation based on intent
            if intent == "greeting":
                return "Hello! How can I help you today?"
            elif intent == "goodbye":
                return "Goodbye! It was nice chatting with you."
            else:
                return self.fallback_response
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return self.fallback_response

    def process_message(self, message: str) -> str:
        """
        Processes a message and generates a response.

        Args:
            message (str): The message to process.

        Returns:
            str: The generated response.
        """
        try:
            intent = self.recognize_intent(message)
            if intent is None:
                return self.fallback_response
            response = self.generate_response(intent)
            self.conversation_history.append(message)
            self.conversation_history.append(response)
            return response
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return self.fallback_response

    def get_conversation_history(self) -> List[str]:
        """
        Gets the conversation history.

        Returns:
            List[str]: The conversation history.
        """
        return self.conversation_history

def main():
    chatbot = Chatbot()
    chatbot.add_intent(Intent("greeting", ["hello", "hi", "hey"]))
    chatbot.add_intent(Intent("goodbye", ["bye", "goodbye", "see you later"]))
    while True:
        message = input("You: ")
        response = chatbot.process_message(message)
        print(f"Chatbot: {response}")

if __name__ == "__main__":
    main()