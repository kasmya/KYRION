"""
A rule-based chatbot implementation with intent recognition, response generation,
conversation history management, and fallback responses.

This module provides a self-contained chatbot system using only the Python standard library.
It implements pattern-based intent recognition, template-based response generation,
and maintains conversation context for more natural interactions.

Example:
    >>> bot = ChatBot()
    >>> response = bot.process_message("Hello, how are you?")
    >>> print(response)
    Hello! I'm doing well, thank you for asking.
"""

import re
import json
import logging
import html
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Pattern, Any, Tuple
from pathlib import Path


class IntentType(Enum):
    """Enumeration of supported intent types for the chatbot."""
    GREETING = "greeting"
    FAREWELL = "farewell"
    THANKS = "thanks"
    HELP = "help"
    QUESTION = "question"
    COMPLAINT = "complaint"
    COMPLIMENT = "compliment"
    UNKNOWN = "unknown"


@dataclass
class Message:
    """
    Represents a single message in the conversation history.
    
    Attributes:
        role: The role of the message sender ('user' or 'assistant').
        content: The text content of the message.
        timestamp: ISO format timestamp when the message was created.
        intent: The recognized intent type (for user messages).
        metadata: Additional metadata associated with the message.
    """
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    intent: Optional[IntentType] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationHistory:
    """
    Manages the conversation history with a configurable maximum length.
    
    Attributes:
        messages: List of Message objects in chronological order.
        max_length: Maximum number of messages to retain in history.
    """
    messages: List[Message] = field(default_factory=list)
    max_length: int = 50
    
    def add_message(self, message: Message) -> None:
        """
        Add a message to the conversation history.
        
        Args:
            message: The Message object to add.
            
        Raises:
            ValueError: If message is None or has invalid role.
        """
        if message is None:
            raise ValueError("Cannot add None message to history")
        if message.role not in ("user", "assistant"):
            raise ValueError(f"Invalid message role: {message.role}")
        
        self.messages.append(message)
        self._trim_history()
    
    def _trim_history(self) -> None:
        """Remove oldest messages if history exceeds maximum length."""
        while len(self.messages) > self.max_length:
            self.messages.pop(0)
    
    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """
        Get the most recent messages from history.
        
        Args:
            count: Number of recent messages to retrieve.
            
        Returns:
            List of recent Message objects (up to count).
        """
        return self.messages[-count:] if self.messages else []
    
    def get_context_summary(self) -> str:
        """
        Generate a text summary of recent conversation context.
        
        Returns:
            Formatted string summarizing recent conversation.
        """
        if not self.messages:
            return "No previous conversation."
        
        recent = self.get_recent_messages(5)
        summary_lines = []
        for msg in recent:
            role_label = "User" if msg.role == "user" else "Assistant"
            intent_info = f" [{msg.intent.value}]" if msg.intent else ""
            summary_lines.append(f"{role_label}{intent_info}: {msg.content[:100]}")
        
        return "\n".join(summary_lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize conversation history to a dictionary.
        
        Returns:
            Dictionary representation of the conversation history.
        """
        return {
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "intent": msg.intent.value if msg.intent else None,
                    "metadata": msg.metadata
                }
                for msg in self.messages
            ],
            "max_length": self.max_length
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationHistory":
        """
        Deserialize conversation history from a dictionary.
        
        Args:
            data: Dictionary containing serialized conversation data.
            
        Returns:
            ConversationHistory instance populated with the data.
        """
        history = cls(max_length=data.get("max_length", 50))
        for msg_data in data.get("messages", []):
            intent = None
            if msg_data.get("intent"):
                try:
                    intent = IntentType(msg_data["intent"])
                except ValueError:
                    intent = IntentType.UNKNOWN
            
            message = Message(
                role=msg_data["role"],
                content=msg_data["content"],
                timestamp=msg_data.get("timestamp", datetime.now().isoformat()),
                intent=intent,
                metadata=msg_data.get("metadata", {})
            )
            history.messages.append(message)
        return history


class IntentRecognizer:
    """
    Rule-based intent recognition using regex pattern matching.
    
    This class compiles patterns for each intent type and provides methods
    to classify user input into intent categories.
    """
    
    # Pattern definitions for each intent type
    INTENT_PATTERNS: Dict[IntentType, List[str]] = {
        IntentType.GREETING: [
            r"\b(hi|hello|hey|greetings|howdy|hiya|what's up|sup)\b",
            r"\b(good morning|good afternoon|good evening)\b",
        ],
        IntentType.FAREWELL: [
            r"\b(bye|goodbye|see you|farewell|take care|later|ciao|adios)\b",
            r"\b(see ya|catch you later|have a good one)\b",
        ],
        IntentType.THANKS: [
            r"\b(thanks|thank you|thx|ty|appreciate it|thanks a lot)\b",
            r"\b(much appreciated|thank you very much)\b",
        ],
        IntentType.HELP: [
            r"\b(help|assist|support|how do i|how can i|what can you do)\b",
            r"\b(commands|features|capabilities|instructions)\b",
        ],
        IntentType.QUESTION: [
            r"\b(what|who|where|when|why|how|which)\b.*\?",
            r"\b(can you|could you|would you|do you know)\b",
            r"\?$",
        ],
        IntentType.COMPLAINT: [
            r"\b(problem|issue|bug|error|broken|wrong|bad|terrible|awful)\b",
            r"\b(not working|doesn't work|failed|disappointed|frustrated)\b",
        ],
        IntentType.COMPLIMENT: [
            r"\b(great|awesome|excellent|amazing|wonderful|fantastic|perfect)\b",
            r"\b(good job|well done|impressive|helpful|useful|love it)\b",
        ],
    }
    
    def __init__(self) -> None:
        """Initialize the intent recognizer with compiled regex patterns."""
        self._compiled_patterns: Dict[IntentType, List[Pattern]] = {}
        self._compile_patterns()
        self.logger = logging.getLogger(__name__)
    
    def _compile_patterns(self) -> None:
        """Compile regex patterns for all intent types."""
        for intent_type, patterns in self.INTENT_PATTERNS.items():
            self._compiled_patterns[intent_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]
    
    def recognize(self, text: str) -> Tuple[IntentType, float]:
        """
        Recognize the intent of the given text.
        
        Args:
            text: The input text to analyze.
            
        Returns:
            Tuple of (IntentType, confidence_score) where confidence is 0.0-1.0.
            
        Raises:
            ValueError: If text is None or empty after stripping.
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be None or empty")
        
        sanitized_text = self._sanitize_input(text)
        scores: Dict[IntentType, int] = {intent: 0 for intent in IntentType}
        
        for intent_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(sanitized_text)
                scores[intent_type] += len(matches)
        
        # Find intent with highest score
        best_intent = max(scores, key=scores.get)
        max_score = scores[best_intent]
        
        # Calculate confidence (simple heuristic)
        total_matches = sum(scores.values())
        confidence = max_score / total_matches if total_matches > 0 else 0.0
        
        # If no patterns matched, return UNKNOWN with low confidence
        if max_score == 0:
            return IntentType.UNKNOWN, 0.1
        
        return best_intent, min(confidence, 1.0)
    
    def _sanitize_input(self, text: str) -> str:
        """
        Sanitize input text to prevent injection attacks.
        
        Args:
            text: Raw input text.
            
        Returns:
            Sanitized text safe for processing.
        """
        # HTML escape to prevent XSS if output is rendered in web context
        sanitized = html.escape(text.strip())
        # Limit length to prevent DoS
        return sanitized[:1000]


class ResponseGenerator:
    """
    Generates responses based on recognized intent and conversation context.
    
    Uses template-based responses with support for contextual variations
    and fallback handling.
    """
    
    # Response templates for each intent type
    RESPONSE_TEMPLATES: Dict[IntentType, List[str]] = {
        IntentType.GREETING: [
            "Hello! How can I help you today?",
            "Hi there! What can I do for you?",
            "Hey! Nice to see you. How are you doing?",
            "Greetings! How may I assist you?",
        ],
        IntentType.FAREWELL: [
            "Goodbye! Have a great day!",
            "See you later! Take care!",
            "Farewell! It was nice chatting with you.",
            "Bye! Come back anytime!",
        ],
        IntentType.THANKS: [
            "You're welcome! Happy to help.",
            "No problem at all! Let me know if you need anything else.",
            "My pleasure! Is there anything else I can do for you?",
            "Glad I could help!",
        ],
        IntentType.HELP: [
            "I can help you with various tasks! You can ask me questions, "
            "greet me, or just chat. Try saying hello or asking a question!",
            "Here's what I can do: answer questions, have conversations, "
            "and provide assistance. What would you like to know?",
            "I'm here to help! You can ask me anything or just say hi. "
            "What's on your mind?",
        ],
        IntentType.QUESTION: [
            "That's a great question! Let me think about that...",
            "Interesting question. I'll do my best to help.",
            "Hmm, let me consider that for a moment.",
        ],
        IntentType.COMPLAINT: [
            "I'm sorry to hear you're having trouble. Can you tell me more about the issue?",
            "I apologize for the inconvenience. Let me see how I can help resolve this.",
            "That sounds frustrating. I'd like to help make it right.",
        ],
        IntentType.COMPLIMENT: [
            "Thank you! That's very kind of you to say.",
            "I appreciate the compliment! It makes my day.",
            "Thanks! I'm glad I could be helpful.",
        ],
        IntentType.UNKNOWN: [
            "I'm not sure I understand. Could you rephrase that?",
            "That's interesting. Tell me more about what you mean.",
            "I'm still learning. Could you try asking in a different way?",
            "Hmm, I didn't quite catch that. What would you like to talk about?",
        ],
    }
    
    # Contextual follow-up responses
    CONTEXTUAL_RESPONSES: Dict[str, List[str]] = {
        "repeated_greeting": [
            "Hello again! Is there something specific I can help with?",
            "Hi there! We already said hello, but I'm happy to chat more!",
        ],
        "repeated_farewell": [
            "Take care! Safe travels!",
            "Goodbye! Looking forward to our next chat!",
        ],
        "after_help": [
            "Did that help? Let me know if you have more questions!",
            "Hope that was useful! Anything else you'd like to know?",
        ],
    }
    
    def __init__(self) -> None:
        """Initialize the response generator."""
        self.logger = logging.getLogger(__name__)
        self._last_intent: Optional[IntentType] = None
        self._intent_count: Dict[IntentType, int] = {intent: 0 for intent in IntentType}
    
    def generate(
        self,
        intent: IntentType,
        confidence: float,
        context: Optional[ConversationHistory] = None,
        user_input: str = ""
    ) -> str:
        """
        Generate a response based on intent, confidence, and context.
        
        Args:
            intent: The recognized intent type.
            confidence: Confidence score of the intent recognition (0.0-1.0).
            context: Optional conversation history for contextual responses.
            user_input: Original user input for potential reference.
            
        Returns:
            Generated response string.
            
        Raises:
            ValueError: If intent is None or confidence is out of range.
        """
        if intent is None:
            raise ValueError("Intent cannot be None")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {confidence}")
        
        try:
            # Update intent tracking
            self._intent_count[intent] = self._intent_count.get(intent, 0) + 1
            
            # Check for contextual responses
            contextual_response = self._get_contextual_response(intent, context)
            if contextual_response:
                self._last_intent = intent
                return contextual_response
            
            # Get template response
            templates = self.RESPONSE_TEMPLATES.get(intent, self.RESPONSE_TEMPLATES[IntentType.UNKNOWN])
            
            # Select response based on confidence and history
            response = self._select_response(templates, intent, confidence)
            
            # Add low confidence disclaimer if needed
            if confidence < 0.3 and intent != IntentType.UNKNOWN:
                response = f"I think you might be {intent.value}... " + response
            
            self._last_intent = intent
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            return self._get_fallback_response()
    
    def _get_contextual_response(
        self,
        intent: IntentType,
        context: Optional[ConversationHistory]
    ) -> Optional[str]:
        """
        Generate contextual response based on conversation history.
        
        Args:
            intent: Current intent type.
            context: Conversation history.
            
        Returns:
            Contextual response string or None if not applicable.
        """
        if not context or not context.messages:
            return None
        
        # Check for repeated intents
        if intent == IntentType.GREETING and self._intent_count.get(IntentType.GREETING, 0) > 1:
            return self._select_response(self.CONTEXTUAL_RESPONSES["repeated_greeting"], intent, 1.0)
        
        if intent == IntentType.FAREWELL and self._intent_count.get(IntentType.FAREWELL, 0) > 1:
            return self._select_response(self.CONTEXTUAL_RESPONSES["repeated_farewell"], intent, 1.0)
        
        if intent == IntentType.HELP and self._last_intent == IntentType.HELP:
            return self._select_response(self.CONTEXTUAL_RESPONSES["after_help"], intent, 1.0)
        
        return None
    
    def _select_response(
        self,
        templates: List[str],
        intent: IntentType,
        confidence: float
    ) -> str:
        """
        Select a response template based on various factors.
        
        Args:
            templates: List of response templates.
            intent: Current intent type.
            confidence: Confidence score.
            
        Returns:
            Selected response string.
        """
        if not templates:
            return self._get_fallback_response()
        
        # Simple selection: use intent count to cycle through templates
        count = self._intent_count.get(intent, 0)
        index = (count - 1) % len(templates)
        return templates[index]