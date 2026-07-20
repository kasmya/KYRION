import logging
from typing import Dict, List
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import nltk
from nltk.stem import WordNetLemmatizer
import re
import random

# Initialize the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Download required NLTK resources
nltk.download('wordnet')

class ChatBot:
    """
    A chatbot with intent recognition, response generation, conversation history, and fallback responses.
    """
    
    def __init__(self, model_name: str, intents: Dict[str, List[str]]) -> None:
        """
        Initialize the chatbot with a pre-trained language model and intents.

        Args:
        - model_name (str): The name of the pre-trained language model.
        - intents (Dict[str, List[str]]): A dictionary of intents and their corresponding responses.
        """
        self.model_name = model_name
        self.intents = intents
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.conversation_history = []
        self.lemmatizer = WordNetLemmatizer()

    def recognize_intent(self, input_text: str) -> str:
        """
        Recognize the intent behind the user's input.

        Args:
        - input_text (str): The user's input text.

        Returns:
        - intent (str): The recognized intent.
        """
        try:
            inputs = self.tokenizer(input_text, return_tensors='pt')
            outputs = self.model(**inputs)
            intent = self.model.config.id2label[outputs.logits.argmax(-1)]
            return intent
        except Exception as e:
            logger.error(f"Error recognizing intent: {e}")
            return None

    def generate_response(self, intent: str) -> str:
        """
        Generate a response based on the recognized intent.

        Args:
        - intent (str): The recognized intent.

        Returns:
        - response (str): The generated response.
        """
        try:
            responses = self.intents.get(intent)
            if responses:
                return random.choice(responses)
            else:
                return "I didn't understand that. Can you please rephrase?"
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm sorry, I didn't understand that."

    def update_conversation_history(self, input_text: str, response: str) -> None:
        """
        Update the conversation history with the user's input and the chatbot's response.

        Args:
        - input_text (str): The user's input text.
        - response (str): The chatbot's response.
        """
        self.conversation_history.append((input_text, response))

    def preprocess_input(self, input_text: str) -> str:
        """
        Preprocess the user's input text by removing special characters and lemmatizing the words.

        Args:
        - input_text (str): The user's input text.

        Returns:
        - preprocessed_text (str): The preprocessed input text.
        """
        try:
            preprocessed_text = re.sub(r'[^a-zA-Z0-9\s]', '', input_text)
            words = nltk.word_tokenize(preprocessed_text)
            lemmatized_words = [self.lemmatizer.lemmatize(word) for word in words]
            return ' '.join(lemmatized_words)
        except Exception as e:
            logger.error(f"Error preprocessing input: {e}")
            return input_text

    def respond(self, input_text: str) -> str:
        """
        Respond to the user's input.

        Args:
        - input_text (str): The user's input text.

        Returns:
        - response (str): The chatbot's response.
        """
        preprocessed_text = self.preprocess_input(input_text)
        intent = self.recognize_intent(preprocessed_text)
        response = self.generate_response(intent)
        self.update_conversation_history(input_text, response)
        return response

# Example usage:
if __name__ == "__main__":
    intents = {
        "greeting": ["Hello!", "Hi!", "Hey!"],
        "goodbye": ["Goodbye!", "See you later!", "Bye!"]
    }
    chatbot = ChatBot("distilbert-base-uncased", intents)
    while True:
        user_input = input("User: ")
        response = chatbot.respond(user_input)
        print("Chatbot:", response)