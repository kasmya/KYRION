import random
from typing import List, Dict, Tuple
from transformers import pipeline
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

nltk.download('wordnet')
nltk.download('punkt')

class ChatBot:
    """
    A simple chatbot using a pre-trained language model and rule-based approach.
    
    Features:
    - Intent recognition
    - Response generation
    - Conversation history
    - Fallback responses for unrecognised intents
    """

    def __init__(self):
        self.intent_recognizer = pipeline('zero-shot-classification', model='facebook/bart-large-mnli')
        self.response_generator = pipeline('text-generation', model='t5-base')
        self.conversation_history = []
        self.intents = {
            'greeting': ['hello', 'hi', 'hey'],
            'goodbye': ['bye', 'see you later', 'goodbye'],
            'thanks': ['thank you', 'thanks']
        }
        self.fallback_responses = ['Sorry, I didn\'t understand that.', 'Can you please rephrase?']

    def _lemmatize_text(self, text: str) -> str:
        """
        Lemmatize the input text to reduce words to their base form.
        
        Args:
        text (str): The input text.
        
        Returns:
        str: The lemmatized text.
        """
        lemmatizer = WordNetLemmatizer()
        tokens = word_tokenize(text)
        lemmatized_tokens = [lemmatizer.lemmatize(token) for token in tokens]
        return ' '.join(lemmatized_tokens)

    def _recognize_intent(self, text: str) -> Tuple[str, float]:
        """
        Recognize the intent behind the input text using a pre-trained language model.
        
        Args:
        text (str): The input text.
        
        Returns:
        Tuple[str, float]: A tuple containing the recognized intent and its confidence score.
        """
        intent_labels = list(self.intents.keys())
        result = self.intent_recognizer(text, intent_labels)
        return result['labels'][0], result['scores'][0]

    def _generate_response(self, intent: str, text: str) -> str:
        """
        Generate a response based on the recognized intent and input text.
        
        Args:
        intent (str): The recognized intent.
        text (str): The input text.
        
        Returns:
        str: The generated response.
        """
        if intent == 'greeting':
            return random.choice(['Hello!', 'Hi!', 'Hey!'])
        elif intent == 'goodbye':
            return random.choice(['See you later!', 'Goodbye!', 'Bye!'])
        elif intent == 'thanks':
            return random.choice(['You\'re welcome!', 'No problem!', 'Anytime!'])
        else:
            return random.choice(self.fallback_responses)

    def chat(self, text: str) -> str:
        """
        Engage in a conversation with the chatbot.
        
        Args:
        text (str): The input text.
        
        Returns:
        str: The chatbot's response.
        """
        lemmatized_text = self._lemmatize_text(text)
        intent, confidence = self._recognize_intent(lemmatized_text)
        response = self._generate_response(intent, text)
        self.conversation_history.append((text, response))
        return response

    def get_conversation_history(self) -> List[Tuple[str, str]]:
        """
        Get the conversation history.
        
        Returns:
        List[Tuple[str, str]]: A list of tuples containing the input text and the chatbot's response.
        """
        return self.conversation_history


# Example usage
if __name__ == '__main__':
    chatbot = ChatBot()
    while True:
        user_input = input('User: ')
        if user_input.lower() == 'quit':
            break
        response = chatbot.chat(user_input)
        print('Chatbot:', response)
    print('Conversation history:')
    for user_input, response in chatbot.get_conversation_history():
        print(f'User: {user_input}')
        print(f'Chatbot: {response}')