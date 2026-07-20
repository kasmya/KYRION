import logging
from typing import Dict, List
from transformers import pipeline
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords

# Initialize logging
logging.basicConfig(level=logging.INFO)

class ChatBot:
    def __init__(self, model_name: str = "distilbert-base-uncased"):
        """
        Initialize the chatbot with a pre-trained language model.

        Args:
        model_name (str): The name of the pre-trained language model. Defaults to "distilbert-base-uncased".
        """
        self.model_name = model_name
        self.model = pipeline("zero-shot-classification", model=model_name)
        self.stop_words = set(stopwords.words("english"))
        self.conversation_history = []

    def _preprocess_text(self, text: str) -> str:
        """
        Preprocess the input text by removing stop words and converting to lowercase.

        Args:
        text (str): The input text.

        Returns:
        str: The preprocessed text.
        """
        tokens = word_tokenize(text)
        tokens = [token for token in tokens if token.lower() not in self.stop_words]
        return " ".join(tokens).lower()

    def _recognize_intent(self, text: str) -> Dict:
        """
        Recognize the intent behind the input text.

        Args:
        text (str): The input text.

        Returns:
        Dict: A dictionary containing the recognized intent and its confidence score.
        """
        text = self._preprocess_text(text)
        result = self.model(text, ["greeting", "goodbye", "help", "unknown"])
        return result

    def _generate_response(self, intent: str) -> str:
        """
        Generate a response based on the recognized intent.

        Args:
        intent (str): The recognized intent.

        Returns:
        str: The generated response.
        """
        responses = {
            "greeting": "Hello! How can I assist you today?",
            "goodbye": "Goodbye! It was nice chatting with you.",
            "help": "I'd be happy to help you. Please provide more information about your issue.",
            "unknown": "I didn't understand that. Could you please rephrase?"
        }
        return responses.get(intent, "I didn't understand that. Could you please rephrase?")

    def _handle_unrecognized_intent(self) -> str:
        """
        Handle unrecognized intents by providing a fallback response.

        Returns:
        str: The fallback response.
        """
        return "I didn't understand that. Could you please rephrase?"

    def respond(self, text: str) -> str:
        """
        Respond to the input text.

        Args:
        text (str): The input text.

        Returns:
        str: The response.
        """
        intent = self._recognize_intent(text)
        if intent["scores"][0] > 0.5:
            return self._generate_response(intent["labels"][0])
        else:
            return self._handle_unrecognized_intent()

    def converse(self) -> None:
        """
        Engage in a conversation with the user.
        """
        while True:
            text = input("User: ")
            response = self.respond(text)
            print("ChatBot:", response)
            self.conversation_history.append((text, response))

def main() -> None:
    chatbot = ChatBot()
    chatbot.converse()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(e)