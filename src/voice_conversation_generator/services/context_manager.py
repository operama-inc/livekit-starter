"""
Context Manager Service - Centralized conversation context management
This ensures consistent context formatting across all implementations
"""
from typing import List, Optional, Dict, Any
from ..models import Turn, TurnType


class ContextManager:
    """
    Centralized context management service that ensures consistent
    conversation history formatting between local and LiveKit implementations.
    """

    @staticmethod
    def format_context(turns: List[Turn], last_n: int = 6) -> str:
        """
        Format conversation history as a string for prompt context.
        This matches the exact implementation from conversation.py line 164-167.

        Args:
            turns: List of conversation turns
            last_n: Number of recent turns to include (default 6)

        Returns:
            Formatted string of conversation history
        """
        if not turns:
            return ""

        # Get the last N turns
        recent_turns = turns[-last_n:] if len(turns) > last_n else turns

        # Format as "Speaker: Text" on separate lines
        return "\n".join([f"{turn.speaker.value}: {turn.text}" for turn in recent_turns])

    @staticmethod
    def format_context_from_messages(messages: List[Dict[str, Any]], last_n: int = 6) -> str:
        """
        Format conversation history from a list of message dictionaries.
        Useful for LiveKit agents that track messages differently.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            last_n: Number of recent messages to include

        Returns:
            Formatted string of conversation history
        """
        if not messages:
            return ""

        # Get the last N messages
        recent_messages = messages[-last_n:] if len(messages) > last_n else messages

        # Format based on role
        formatted = []
        for msg in recent_messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            # Map roles to speaker format
            if role in ['user', 'human', 'customer']:
                speaker = "Customer"
            elif role in ['assistant', 'agent', 'support']:
                speaker = "Support"
            else:
                speaker = role.capitalize()

            formatted.append(f"{speaker}: {content}")

        return "\n".join(formatted)

    @staticmethod
    def create_turn_from_message(
        text: str,
        speaker_type: TurnType,
        timestamp: Optional[float] = None
    ) -> Turn:
        """
        Helper method to create a Turn object from a message.

        Args:
            text: The message text
            speaker_type: Whether this is from customer or support
            timestamp: Optional timestamp for the turn

        Returns:
            Turn object
        """
        import time
        return Turn(
            speaker=speaker_type,
            text=text,
            timestamp=timestamp or time.time()
        )

    @staticmethod
    def extract_last_customer_message(context: str) -> Optional[str]:
        """
        Extract the last customer message from a formatted context string.
        Useful for agents that need to respond to the most recent customer input.

        Args:
            context: Formatted conversation context

        Returns:
            The last customer message text, or None if not found
        """
        if not context:
            return None

        lines = context.strip().split('\n')
        for line in reversed(lines):
            if line.startswith('Customer:'):
                return line.replace('Customer:', '').strip()

        return None

    @staticmethod
    def extract_last_support_message(context: str) -> Optional[str]:
        """
        Extract the last support message from a formatted context string.
        Useful for tracking what the agent last said.

        Args:
            context: Formatted conversation context

        Returns:
            The last support message text, or None if not found
        """
        if not context:
            return None

        lines = context.strip().split('\n')
        for line in reversed(lines):
            if line.startswith('Support:'):
                return line.replace('Support:', '').strip()

        return None

    @staticmethod
    def count_turns(context: str) -> int:
        """
        Count the number of turns in a formatted context string.

        Args:
            context: Formatted conversation context

        Returns:
            Number of turns (customer + support messages)
        """
        if not context:
            return 0

        lines = context.strip().split('\n')
        return sum(1 for line in lines if line.startswith(('Customer:', 'Support:')))

    @staticmethod
    def is_conversation_ending(context: str, keywords: List[str] = None) -> bool:
        """
        Check if the conversation appears to be ending based on context.

        Args:
            context: Formatted conversation context
            keywords: Optional list of ending keywords to check for

        Returns:
            True if conversation seems to be ending
        """
        if not context:
            return False

        default_keywords = [
            'thank you', 'thanks', 'goodbye', 'bye', 'have a nice day',
            'take care', 'appreciate your help', 'that\'s all', 'all set',
            'problem solved', 'issue resolved', 'satisfied'
        ]

        keywords = keywords or default_keywords

        # Check last few messages for ending indicators
        last_lines = context.lower().split('\n')[-3:]  # Last 3 messages
        combined_text = ' '.join(last_lines)

        return any(keyword in combined_text for keyword in keywords)