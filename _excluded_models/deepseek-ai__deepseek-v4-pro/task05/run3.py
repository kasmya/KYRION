"""
chatbot.py

A rule-based chatbot module providing intent recognition, response generation,
conversation history management, and fallback responses. Designed with type hints,
comprehensive docstrings, and explicit error handling. Uses only the Python standard
library and the widely-used `re` module for pattern matching.

Security best practices:
- Input sanitization via length limits.
- No eval/exec of user input.
- History capped to prevent memory exhaustion.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    """Represents a single exchange in the conversation history."""
    user_input: str
    bot_response: str


@dataclass
class IntentRule:
    """
    A rule for matching user input to an intent.

    Attributes:
        name: Unique intent identifier.
        patterns: List of compiled regex patterns to match against user input.
        responses: List of possible response templates. The first group captured
                   by a pattern can be referenced as {0} in the template.
        priority: Higher priority rules are checked first. Default 0.
    """
    name: str
    patterns: List[re.Pattern]
    responses: List[str]
    priority: int = 0

    def match(self, text: str) -> Optional[str]:
        """
        Attempt to match the text against the rule's patterns.

        Args:
            text: User input string.

        Returns:
            The matched intent name if any pattern matches, else None.

        Raises:
            TypeError: If text is not a string.
        """
        if not isinstance(text, str):
            raise TypeError("Input text must be a string.")
        for pattern in self.patterns:
            if pattern.search(text):
                return self.name
        return None

    def generate_response(self, text: str) -> str:
        """
        Generate a response for a matched intent.

        Picks the first pattern that matches and uses the first matching
        response template, formatting it with captured groups if present.

        Args:
            text: User input string.

        Returns:
            Formatted response string.

        Raises:
            ValueError: If no pattern matches the text.
        """
        for pattern, template in zip(self.patterns, self.responses):
            match = pattern.search(text)
            if match:
                try:
                    return template.format(*match.groups())
                except (IndexError, KeyError) as e:
                    # Fallback to raw template if formatting fails
                    return template
        raise ValueError(f"No pattern matched for intent '{self.name}'")


# ---------------------------------------------------------------------------
# Chatbot class
# ---------------------------------------------------------------------------

class Chatbot:
    """
    A rule-based chatbot with intent recognition, response generation,
    conversation history, and fallback handling.

    Attributes:
        rules: List of IntentRule objects defining the chatbot's behaviour.
        fallback_responses: Responses used when no intent is matched.
        history: List of ConversationTurn objects.
        max_history: Maximum number of turns to retain.
    """

    def __init__(
        self,
        rules: Optional[List[IntentRule]] = None,
        fallback_responses: Optional[List[str]] = None,
        max_history: int = 100,
    ) -> None:
        """
        Initialize the chatbot.

        Args:
            rules: Intent rules. If None, a minimal default set is used.
            fallback_responses: Fallback responses. If None, a default list is used.
            max_history: Maximum conversation turns to store (security measure).

        Raises:
            ValueError: If max_history is less than 1.
        """
        if max_history < 1:
            raise ValueError("max_history must be at least 1.")

        self.rules: List[IntentRule] = rules or self._default_rules()
        # Sort rules by descending priority so higher priority checked first
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        self.fallback_responses: List[str] = fallback_responses or [
            "I'm sorry, I didn't quite understand that. Could you rephrase?",
            "I'm not sure how to respond to that. Can you try asking something else?",
            "Hmm, I don't have an answer for that yet.",
        ]
        self.max_history: int = max_history
        self.history: List[ConversationTurn] = []

    @staticmethod
    def _default_rules() -> List[IntentRule]:
        """
        Provide a minimal set of intent rules for demonstration.

        Returns:
            List of IntentRule objects.
        """
        return [
            IntentRule(
                name="greeting",
                patterns=[
                    re.compile(r"\b(hello|hi|hey|good\s*morning|good\s*evening)\b", re.IGNORECASE),
                ],
                responses=["Hello! How can I help you today?", "Hi there! What can I do for you?"],
                priority=10,
            ),
            IntentRule(
                name="farewell",
                patterns=[
                    re.compile(r"\b(bye|goodbye|see\s*you|farewell)\b", re.IGNORECASE),
                ],
                responses=["Goodbye! Have a great day.", "See you later! Take care."],
                priority=10,
            ),
            IntentRule(
                name="thanks",
                patterns=[
                    re.compile(r"\b(thanks|thank\s*you|thx)\b", re.IGNORECASE),
                ],
                responses=["You're welcome!", "Happy to help!"],
                priority=5,
            ),
            IntentRule(
                name="name_query",
                patterns=[
                    re.compile(r"what\s+is\s+your\s+name\??", re.IGNORECASE),
                    re.compile(r"who\s+are\s+you\??", re.IGNORECASE),
                ],
                responses=["I'm Chatbot, your virtual assistant.", "You can call me Chatbot."],
                priority=5,
            ),
            IntentRule(
                name="how_are_you",
                patterns=[
                    re.compile(r"how\s+are\s+you\??", re.IGNORECASE),
                    re.compile(r"how('s| is)\s+it\s+going\??", re.IGNORECASE),
                ],
                responses=[
                    "I'm doing well, thank you for asking!",
                    "All systems operational! How about you?",
                ],
                priority=5,
            ),
        ]

    def _sanitize_input(self, user_input: str) -> str:
        """
        Sanitize and truncate user input to prevent abuse.

        Args:
            user_input: Raw input string.

        Returns:
            Sanitized string stripped of leading/trailing whitespace and truncated
            to a safe maximum length (500 characters).
        """
        if not isinstance(user_input, str):
            raise TypeError("User input must be a string.")
        # Limit length to prevent resource exhaustion
        MAX_LENGTH = 500
        return user_input.strip()[:MAX_LENGTH]

    def _recognize_intent(self, text: str) -> Optional[IntentRule]:
        """
        Find the highest-priority matching intent rule for the given text.

        Args:
            text: Sanitized user input.

        Returns:
            The matching IntentRule, or None if no rule matches.
        """
        for rule in self.rules:
            if rule.match(text):
                return rule
        return None

    def _generate_response(self, rule: IntentRule, text: str) -> str:
        """
        Generate a response using the matched intent rule.

        Args:
            rule: The matched IntentRule.
            text: Sanitized user input.

        Returns:
            Response string.

        Raises:
            RuntimeError: If response generation fails unexpectedly.
        """
        try:
            return rule.generate_response(text)
        except Exception as e:
            raise RuntimeError(f"Response generation failed for intent '{rule.name}': {e}") from e

    def _fallback_response(self) -> str:
        """
        Select a fallback response when no intent is matched.

        Uses a simple round-robin based on history length to vary responses.

        Returns:
            A fallback response string.
        """
        if not self.fallback_responses:
            return "I'm not sure how to respond."
        index = len(self.history) % len(self.fallback_responses)
        return self.fallback_responses[index]

    def _add_to_history(self, user_input: str, bot_response: str) -> None:
        """
        Append a turn to the conversation history, enforcing the max limit.

        Args:
            user_input: Sanitized user input.
            bot_response: Generated bot response.
        """
        turn = ConversationTurn(user_input=user_input, bot_response=bot_response)
        self.history.append(turn)
        # Trim oldest entries if exceeding max_history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_response(self, user_input: str) -> str:
        """
        Process user input and return the bot's response.

        Full pipeline: sanitize -> intent recognition -> response generation
        (or fallback) -> update history -> return response.

        Args:
            user_input: Raw string from the user.

        Returns:
            Bot response string.

        Raises:
            TypeError: If user_input is not a string.
            RuntimeError: If an unexpected error occurs during processing.
        """
        if not isinstance(user_input, str):
            raise TypeError("user_input must be a string.")

        try:
            sanitized = self._sanitize_input(user_input)
        except TypeError:
            raise  # re-raise type errors directly
        except Exception as e:
            raise RuntimeError(f"Input sanitization failed: {e}") from e

        try:
            rule = self._recognize_intent(sanitized)
            if rule:
                response = self._generate_response(rule, sanitized)
            else:
                response = self._fallback_response()
        except Exception as e:
            # Catch-all for unexpected failures; still provide a fallback
            response = self._fallback_response()

        try:
            self._add_to_history(sanitized, response)
        except Exception as e:
            # Non-critical; log could be added in production
            pass

        return response

    def clear_history(self) -> None:
        """Clear the entire conversation history."""
        self.history.clear()

    def get_history(self) -> List[Dict[str, str]]:
        """
        Return the conversation history as a list of dictionaries.

        Returns:
            List of dicts with 'user' and 'bot' keys.
        """
        return [
            {"user": turn.user_input, "bot": turn.bot_response}
            for turn in self.history
        ]


# ---------------------------------------------------------------------------
# Example usage (runs only when executed directly)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    bot = Chatbot()
    print("Chatbot ready. Type 'quit' to exit.")
    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if user_input.lower() in ("quit", "exit"):
            print("Bot: Goodbye!")
            break
        response = bot.get_response(user_input)
        print(f"Bot: {response}")