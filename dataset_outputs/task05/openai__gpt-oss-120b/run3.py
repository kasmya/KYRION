"""
Chatbot implementation with intent recognition, response generation,
conversation history, and fallback handling.

Features:
- Zero-shot intent classification using Hugging Face transformers.
- Rule‑based responses for known intents.
- Generative fallback using a language model (e.g., GPT‑2).
- Conversation history tracking.
- Input sanitisation and length limits for security.
"""

from __future__ import annotations

import logging
import random
import re
import sys
import string
from typing import Any, Dict, List, Tuple

from transformers import pipeline, Pipeline, set_seed
from transformers.pipelines.base import PipelineException

# --------------------------------------------------------------------------- #
# Configuration constants
# --------------------------------------------------------------------------- #
MAX_INPUT_LENGTH: int = 500          # characters
MAX_RESPONSE_TOKENS: int = 150        # tokens for generative fallback
RANDOM_SEED: int = 42                # reproducibility
DEVICE: int = -1                     # -1 = CPU, >=0 GPU id

INTENT_LABELS: List[str] = [
    "greeting",
    "goodbye",
    "weather",
    "joke",
    "thank_you",
    "unknown",
]

# Predefined responses for recognized intents
PREDEFINED_RESPONSES: Dict[str, List[str]] = {
    "greeting": [
        "Hello! How can I help you today?",
        "Hi there! What would you like to talk about?",
        "Hey! How's it going?",
    ],
    "goodbye": [
        "Goodbye! Have a great day!",
        "See you later! Take care!",
        "Farewell! Come back anytime.",
    ],
    "weather": [
        "I hope the weather is nice where you are!",
        "It's always good to check the forecast before heading out.",
    ],
    "joke": [
        "Why did the scarecrow win an award? Because he was outstanding in his field!",
        "I would tell you a construction joke, but I'm still working on it.",
    ],
    "thank_you": [
        "You're welcome!",
        "No problem at all!",
        "Glad I could help!",
    ],
}

FALLBACK_RESPONSES: List[str] = [
    "I'm not sure I understand. Could you rephrase?",
    "Sorry, I didn't catch that. Can you elaborate?",
    "I'm still learning. Can you give me more details?",
]

# --------------------------------------------------------------------------- #
# Utility functions
# --------------------------------------------------------------------------- #


def _clean_text(text: str) -> str:
    """
    Remove non‑printable characters and truncate to the max allowed length.
    """
    # Strip control characters and trim whitespace
    printable = set(string.printable)
    cleaned = "".join(ch for ch in text if ch in printable).strip()
    # Truncate to length limit
    if len(cleaned) > MAX_INPUT_LENGTH:
        cleaned = cleaned[:MAX_INPUT_LENGTH]
    return cleaned


def _log_error(msg: str, exc: BaseException | None = None) -> None:
    """Log errors consistently."""
    if exc:
        logging.error("%s: %s", msg, exc, exc_info=True)
    else:
        logging.error(msg)


# --------------------------------------------------------------------------- #
# Core chatbot class
# --------------------------------------------------------------------------- #


class ChatBot:
    """
    A simple chatbot supporting intent recognition, rule‑based and generative
    responses, and conversation history.
    """

    def __init__(
        self,
        intent_labels: List[str] | None = None,
        fallback_model_name: str = "gpt2",
        device: int = DEVICE,
    ) -> None:
        """
        Initialise pipelines for intent classification and response generation.

        Args:
            intent_labels: List of candidate intent strings.
            fallback_model_name: Name of a generative model for fallback.
            device: Device identifier for transformers (-1 for CPU).
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.intent_labels = intent_labels or INTENT_LABELS
        self.history: List[Dict[str, str]] = []

        # Zero‑shot classification pipeline for intent recognition
        try:
            self.intent_classifier: Pipeline = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=device,
            )
        except Exception as exc:
            _log_error("Failed to initialise intent classifier pipeline", exc)
            raise RuntimeError("Intent classifier initialisation failed") from exc

        # Text‑generation pipeline for fallback responses
        try:
            self.generator: Pipeline = pipeline(
                "text-generation",
                model=fallback_model_name,
                device=device,
                framework="pt",
            )
            set_seed(RANDOM_SEED)
        except Exception as exc:
            _log_error("Failed to initialise text generation pipeline", exc)
            raise RuntimeError("Response generator initialisation failed") from exc

        self.logger.info("ChatBot initialised with intents: %s", self.intent_labels)

    # --------------------------------------------------------------------- #
    # History handling
    # --------------------------------------------------------------------- #

    def add_to_history(self, role: str, content: str) -> None:
        """
        Append a message to the conversation history.

        Args:
            role: Either "user" or "assistant".
            content: Message text.
        """
        self.history.append({"role": role, "content": content})

    def get_history(self) -> List[Dict[str, str]]:
        """Return a copy of the conversation history."""
        return list(self.history)

    # --------------------------------------------------------------------- #
    # Intent recognition
    # --------------------------------------------------------------------- #

    def recognize_intent(self, text: str) -> Tuple[str, float]:
        """
        Determine the most likely intent for the given text.

        Returns:
            A tuple of (intent_label, confidence_score). If the confidence is
            below a threshold, "unknown" is returned.
        """
        try:
            result = self.intent_classifier(
                sequences=text,
                candidate_labels=self.intent_labels,
                multi_label=False,
            )
            top_label: str = result["labels"][0]
            score: float = float(result["scores"][0])
            # Treat low confidence as unknown intent
            if score < 0.4 or top_label == "unknown":
                return "unknown", score
            return top_label, score
        except PipelineException as exc:
            _log_error("Intent classification pipeline error", exc)
            return "unknown", 0.0
        except Exception as exc:
            _log_error("Unexpected error during intent recognition", exc)
            return "unknown", 0.0

    # --------------------------------------------------------------------- #
    # Response generation
    # --------------------------------------------------------------------- #

    def _rule_based_response(self, intent: str) -> str | None:
        """Select a predefined response for a known intent, if available."""
        responses = PREDEFINED_RESPONSES.get(intent)
        if responses:
            return random.choice(responses)
        return None

    def _fallback_response(self, user_input: str) -> str:
        """Generate a fallback response using the generative model."""
        prompt = f"User: {user_input}\nAssistant:"
        try:
            generated = self.generator(
                prompt,
                max_new_tokens=MAX_RESPONSE_TOKENS,
                num_return_sequences=1,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                truncation=True,
            )
            text = generated[0]["generated_text"]
            # Remove the prompt part and any trailing whitespace
            response = re.sub(r".*Assistant:\s*", "", text, flags=re.DOTALL).strip()
            # Ensure a non‑empty response
            return response or random.choice(FALLBACK_RESPONSES)
        except Exception as exc:
            _log_error("Error during fallback generation", exc)
            return random.choice(FALLBACK_RESPONSES)

    def generate_response(self, intent: str, user_input: str) -> str:
        """
        Produce a response based on the detected intent.

        Args:
            intent: Detected intent label.
            user_input: Original user message (sanitised).

        Returns:
            Assistant reply string.
        """
        # Try rule‑based first
        response = self._rule_based_response(intent)
        if response:
            return response
        # Otherwise use generative fallback
        return self._fallback_response(user_input)

    # --------------------------------------------------------------------- #
    # Main interaction method
    # --------------------------------------------------------------------- #

    def respond(self, raw_input: str) -> str:
        """
        Process user input, update history, and return the bot's reply.

        Args:
            raw_input: Raw text from the user.

        Returns:
            The assistant's response.
        """
        user_input = _clean_text(raw_input)
        if not user_input:
            return "Please say something so I can help you."

        self.add_to_history("user", user_input)

        intent, confidence = self.recognize_intent(user_input)
        self.logger.debug(
            "Recognised intent: %s (confidence: %.2f)", intent, confidence
        )

        response = self.generate_response(intent, user_input)
        self.add_to_history("assistant", response)

        return response


# --------------------------------------------------------------------------- #
# Simple command‑line interface for manual testing
# --------------------------------------------------------------------------- #


def main() -> None:
    """Run a REPL loop for interacting with the chatbot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    bot = ChatBot()
    print("ChatBot is ready! Type 'exit' or 'quit' to end the conversation.\n")

    while True:
        try:
            user_msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_msg.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        reply = bot.respond(user_msg)
        print(f"Bot: {reply}")

    # Optional: print conversation history before exiting
    # print("\nConversation history:")
    # for entry in bot.get_history():
    #     print(f"{entry['role'].title()}: {entry['content']}")


if __name__ == "__main__":
    main()