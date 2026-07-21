"""
A simple rule-based chatbot with intent recognition, response generation,
conversation history, and fallback responses.

This module provides a ChatBot class that can be used to conduct a text-based
conversation. It uses keyword matching for intent recognition and selects
random responses from predefined lists. Conversation history is maintained
in memory.

Example:
    bot = ChatBot()
    response = bot.chat("Hello there!")
    print(response)
"""

import random
import re
from typing import Dict, List, Optional, Any


class ChatBot:
    """
    A rule-based chatbot with intent recognition and conversation history.

    Attributes:
        intents: A dictionary mapping intent names to patterns and responses.
        history: A list of conversation turns, each a dict with 'role' and 'content'.
        fallback_responses: A list of responses for unrecognized inputs.
    """

    def __init__(
        self,
        intents: Optional[Dict[str, Dict[str, List[str]]]] = None,
        fallback_responses: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize the chatbot with intents and fallback responses.

        Args:
            intents: A dictionary of intents. Each intent has 'patterns' (list of keywords)
                     and 'responses' (list of possible responses). If None, a default set is used.
            fallback_responses: A list of fallback responses. If None, a default list is used.

        Raises:
            ValueError: If intents or fallback_responses are provided but invalid.
        """
        # Default intents
        default_intents = {
            "greeting": {
                "patterns": ["hello", "hi", "hey", "greetings", "howdy"],
                "responses": [
                    "Hello! How can I help you today?",
                    "Hi there! What can I do for you?",
                    "Hey! Nice to see you.",
                ],
            },
            "goodbye": {
                "patterns": ["bye", "goodbye", "see you", "farewell", "later"],
                "responses": [
                    "Goodbye! Have a great day!",
                    "See you later! Take care.",
                    "Farewell! Come back soon.",
                ],
            },
            "thanks": {
                "patterns": ["thank you", "thanks", "thx", "appreciate it"],
                "responses": [
                    "You're welcome!",
                    "No problem at all!",
                    "Anytime! Happy to help.",
                ],
            },
            "help": {
                "patterns": ["help", "support", "assist", "what can you do"],
                "responses": [
                    "I can help with greetings, goodbyes, and thanks. Try saying hello!",
                    "I'm a simple bot. You can say hi, bye, or thank you.",
                    "Just chat with me! I respond to basic intents.",
                ],
            },
        }

        # Default fallback responses
        default_fallback = [
            "I'm not sure I understand. Could you rephrase that?",
            "Sorry, I didn't catch that. Can you try again?",
            "Hmm, I don't have a response for that. Try asking something else.",
        ]

        # Validate and assign intents
        if intents is not None:
            if not isinstance(intents, dict):
                raise ValueError("intents must be a dictionary")
            for intent_name, intent_data in intents.items():
                if not isinstance(intent_data, dict):
                    raise ValueError(f"Intent '{intent_name}' must be a dictionary")
                if "patterns" not in intent_data or "responses" not in intent_data:
                    raise ValueError(
                        f"Intent '{intent_name}' must have 'patterns' and 'responses' keys"
                    )
                if not isinstance(intent_data["patterns"], list) or not isinstance(
                    intent_data["responses"], list
                ):
                    raise ValueError(
                        f"Intent '{intent_name}' patterns and responses must be lists"
                    )
            self.intents = intents
        else:
            self.intents = default_intents

        # Validate and assign fallback responses
        if fallback_responses is not None:
            if not isinstance(fallback_responses, list):
                raise ValueError("fallback_responses must be a list")
            if not all(isinstance(r, str) for r in fallback_responses):
                raise ValueError("All fallback responses must be strings")
            self.fallback_responses = fallback_responses
        else:
            self.fallback_responses = default_fallback

        self.history: List[Dict[str, str]] = []

    def recognize_intent(self, text: str) -> str:
        """
        Recognize the intent of the user input based on keyword matching.

        Args:
            text: The user input string.

        Returns:
            The recognized intent name, or "fallback" if no intent matches.

        Raises:
            TypeError: If text is not a string.
        """
        if not isinstance(text, str):
            raise TypeError("Input text must be a string")

        # Normalize text: lowercase, remove punctuation
        normalized = re.sub(r"[^\w\s]", "", text.lower().strip())

        # Check each intent's patterns
        for intent_name, intent_data in self.intents.items():
            for pattern in intent_data["patterns"]:
                # Simple word boundary matching
                if re.search(rf"\b{re.escape(pattern)}\b", normalized):
                    return intent_name

        return "fallback"

    def generate_response(self, intent: str) -> str:
        """
        Generate a random response for the given intent.

        Args:
            intent: The intent name (e.g., "greeting", "fallback").

        Returns:
            A randomly selected response string.

        Raises:
            ValueError: If intent is not recognized (not in intents and not "fallback").
        """
        if intent == "fallback":
            responses = self.fallback_responses
        elif intent in self.intents:
            responses = self.intents[intent]["responses"]
        else:
            raise ValueError(f"Unknown intent: {intent}")

        if not responses:
            raise ValueError(f"No responses defined for intent: {intent}")

        return random.choice(responses)

    def add_to_history(self, role: str, message: str) -> None:
        """
        Add a message to the conversation history.

        Args:
            role: The role of the message sender ("user" or "assistant").
            message: The message content.

        Raises:
            ValueError: If role is not "user" or "assistant".
            TypeError: If message is not a string.
        """
        if role not in ("user", "assistant"):
            raise ValueError("Role must be 'user' or 'assistant'")
        if not isinstance(message, str):
            raise TypeError("Message must be a string")

        self.history.append({"role": role, "content": message})

    def get_history(self) -> List[Dict[str, str]]:
        """
        Get the conversation history.

        Returns:
            A list of dictionaries with 'role' and 'content' keys.
        """
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.history.clear()

    def chat(self, user_input: str) -> str:
        """
        Process user input, update history, and return the bot's response.

        Args:
            user_input: The user's message.

        Returns:
            The bot's response string.

        Raises:
            TypeError: If user_input is not a string.
        """
        if not isinstance(user_input, str):
            raise TypeError("User input must be a string")

        # Add user message to history
        self.add_to_history("user", user_input)

        # Recognize intent and generate response
        intent = self.recognize_intent(user_input)
        response = self.generate_response(intent)

        # Add assistant response to history
        self.add_to_history("assistant", response)

        return response


def main() -> None:
    """
    Run a simple command-line interface for the chatbot.

    This function creates a ChatBot instance and loops to get user input
    until the user types 'quit' or 'exit'.
    """
    bot = ChatBot()
    print("ChatBot: Hello! Type 'quit' or 'exit' to end the conversation.")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChatBot: Goodbye!")
            break

        if user_input.lower() in ("quit", "exit"):
            print("ChatBot: Goodbye!")
            break

        if not user_input:
            print("ChatBot: Please say something.")
            continue

        try:
            response = bot.chat(user_input)
            print(f"ChatBot: {response}")
        except Exception as e:
            print(f"ChatBot: An error occurred: {e}")


if __name__ == "__main__":
    main()