import logging
from typing import Dict, List
from transformers import pipeline
import nltk
from nltk.stem import WordNetLemmatizer
import re
from functools import wraps

# Initialize Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize NLTK Resources
nltk.download('wordnet')
lemmatizer = WordNetLemmatizer()

# Security Decorator for Input Validation
def validate_input(func):
    """Validate user input to prevent potential security vulnerabilities."""
    @wraps(func)
    def wrapper(self, user_input: str, *args, **kwargs):
        # Basic Input Sanitization (e.g., remove special characters except for certain allowed ones)
        sanitized_input = re.sub(r'[^\w\s\.,!?\'\"]', '', user_input)
        if sanitized_input != user_input:
            logger.warning("Input sanitized due to special characters.")
            # Optionally, you could return an error here if you want to reject sanitized inputs
            # For this example, we proceed with the sanitized input
        return func(self, sanitized_input, *args, **kwargs)
    return wrapper

class IntentRecognizer:
    """Rule-Based Intent Recognizer with Basic Patterns."""
    
    def __init__(self):
        self.intents: Dict[str, List[str]] = {
            'greeting': ['hello', 'hi', 'hey'],
            'goodbye': ['bye', 'see you later'],
            'thanks': ['thanks', 'thank you']
        }
        
    def recognize(self, input_text: str) -> str:
        """Identify the intent behind the input text."""
        input_text = input_text.lower()
        for intent, patterns in self.intents.items():
            for pattern in patterns:
                if pattern in input_text:
                    return intent
        return 'unrecognised'
        
class ResponseGenerator:
    """Simple Response Generator based on Intent."""
    
    def __init__(self):
        self.responses: Dict[str, str] = {
            'greeting': 'Hello! How can I assist you today?',
            'goodbye': 'See you later!',
            'thanks': 'You\'re welcome!',
            'unrecognised': 'Sorry, I didn\'t understand that. Could you please rephrase?'
        }
        
    def generate(self, intent: str) -> str:
        """Produce a response based on the identified intent."""
        return self.responses.get(intent, self.responses['unrecognised'])
        
class ChatBot:
    """Chatbot Implementation with Intent Recognition, Response Generation, and Conversation History."""
    
    def __init__(self, intent_recognizer: IntentRecognizer, response_generator: ResponseGenerator):
        self.intent_recognizer = intent_recognizer
        self.response_generator = response_generator
        self.conversation_history: List[str] = []
        
    @validate_input
    def respond(self, user_input: str) -> str:
        """Process user input and return a response."""
        try:
            intent = self.intent_recognizer.recognize(user_input)
            response = self.response_generator.generate(intent)
            self.conversation_history.append(f"User: {user_input}\nBot: {response}")
            return response
        except Exception as e:
            logger.error(f"Error in response generation: {e}")
            return "An error occurred. Please try again."
            
    def get_conversation_history(self) -> List[str]:
        """Retrieve the conversation history."""
        return self.conversation_history.copy()
        
# Alternative Transformer-Based Approach for Intent Recognition (Commented Out)
# class TransformerIntentRecognizer:
#     """Intent Recognizer using a Pre-Trained Transformer Model."""
#     
#     def __init__(self, model_name: str = "distilbert-base-uncased"):
#         self.model = pipeline("zero-shot-classification", model=model_name)
#         self.intents = ['greeting', 'goodbye', 'thanks']
#         
#     def recognize(self, input_text: str) -> str:
#         """Identify the intent using a transformer model."""
#         result = self.model(input_text, self.intents)
#         return result["label"][0]
        
# Usage Example
if __name__ == "__main__":
    intent_recognizer = IntentRecognizer()
    response_generator = ResponseGenerator()
    chatbot = ChatBot(intent_recognizer, response_generator)
    
    # Example Conversation
    print(chatbot.respond("Hello!"))
    print(chatbot.respond("Thanks for the help!"))
    print(chatbot.respond("This is an unrecognized intent"))
    print("Conversation History:")
    for entry in chatbot.get_conversation_history():
        print(entry)
        
    # Uncomment for Transformer-Based Approach (ensure you have the model downloaded or it will download automatically)
    # transformer_recognizer = TransformerIntentRecognizer()
    # print(transformer_recognizer.recognize("Hello"))  # Requires internet for model download if not already present