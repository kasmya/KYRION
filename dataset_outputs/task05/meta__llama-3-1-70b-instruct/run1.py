import logging
import random
from typing import Dict, List
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load pre-trained language model and tokenizer
model_name = "distilbert-base-uncased-finetuned-sst-2-english"
model = AutoModelForSequenceClassification.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

# Define intents and responses
INTENTS: Dict[str, Dict[str, List[str]]] = {
    "greeting": {"patterns": ["hello", "hi", "hey"], "responses": ["Hi, how are you?", "Hello! How can I assist you?"]},
    "goodbye": {"patterns": ["bye", "see you later"], "responses": ["See you later!", "Goodbye!"]},
    "thanks": {"patterns": ["thanks", "thank you"], "responses": ["You're welcome!", "No problem!"]},
}

# Define fallback responses
FALLBACK_RESPONSES = ["I didn't understand that. Can you please rephrase?", "Sorry, I'm not sure I understand."]

# Initialize lemmatizer
lemmatizer = WordNetLemmatizer()

def lemmatize_text(text: str) -> str:
    """Lemmatize a given text."""
    tokens = word_tokenize(text)
    tokens = [lemmatizer.lemmatize(token) for token in tokens]
    return " ".join(tokens)

def recognize_intent(text: str) -> str:
    """Recognize the intent behind a given text."""
    # Tokenize and lemmatize the text
    text = lemmatize_text(text)
    inputs = tokenizer(text, return_tensors="pt")

    # Get the model's output
    outputs = model(**inputs)
    logits = outputs.logits

    # Get the predicted class
    predicted_class = logits.argmax(-1).item()

    # Map the predicted class to an intent
    intents = list(INTENTS.keys())
    intent = intents[predicted_class]

    return intent

def generate_response(intent: str, text: str) -> str:
    """Generate a response based on the recognized intent."""
    # Get the responses for the intent
    responses = INTENTS[intent]["responses"]

    # Return a random response
    return random.choice(responses)

def get_fallback_response() -> str:
    """Return a fallback response."""
    return random.choice(FALLBACK_RESPONSES)

def chatbot(text: str) -> str:
    """Main chatbot function."""
    try:
        # Recognize the intent
        intent = recognize_intent(text)

        # Generate a response
        response = generate_response(intent, text)
    except KeyError:
        # If the intent is not recognized, return a fallback response
        response = get_fallback_response()
    except Exception as e:
        # Log any exceptions and return a fallback response
        logger.error(f"An error occurred: {e}")
        response = get_fallback_response()

    return response

def main() -> None:
    """Main function."""
    conversation_history = []

    while True:
        # Get user input
        user_input = input("User: ")

        # Get the chatbot's response
        response = chatbot(user_input)

        # Print the chatbot's response
        print("Chatbot: ", response)

        # Add the user input and response to the conversation history
        conversation_history.append((user_input, response))

        # Exit if the user types 'exit'
        if user_input.lower() == "exit":
            break

if __name__ == "__main__":
    # Download required NLTK data
    nltk.download("punkt")
    nltk.download("wordnet")

    # Run the main function
    main()