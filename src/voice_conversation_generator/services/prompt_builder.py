"""
Prompt Builder Service - Centralized prompt generation for both local and LiveKit implementations
This ensures consistency between all agent implementations
"""
from typing import Optional, Tuple, List
from ..models import CustomerPersona, SupportPersona, Turn, TurnType


class PromptBuilder:
    """
    Centralized prompt building service that ensures consistency between
    local simulation and LiveKit agents. This is the single source of truth
    for all prompt generation.
    """

    @staticmethod
    def build_customer_prompt(
        persona: CustomerPersona,
        context: str = ""
    ) -> Tuple[Optional[str], str]:
        """
        Build prompt for customer agent based on persona and conversation context.

        Args:
            persona: Customer persona with personality, issue, goal, etc.
            context: Formatted conversation history

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # Build the customer prompt (matching local_orchestrator.py lines 180-191)
        prompt = f"""You are {persona.name} receiving a call from customer support.
Your personality: {persona.personality}
Your issue/situation: {persona.issue}
Your goal: {persona.goal}
Emotional state: {persona.emotional_state.value}

Conversation so far:
{context}

Respond naturally based on your personality and situation.
{persona.special_behavior if persona.special_behavior else ''}
Keep your response under 2 sentences. Do not use any formatting or quotation marks. Just speak naturally."""

        # Add guardrails if any
        if persona.guardrails:
            prompt += f"\nGuardrails: {', '.join(persona.guardrails)}"

        # Use system prompt if provided
        system_prompt = persona.system_prompt if persona.system_prompt else None

        return system_prompt, prompt

    @staticmethod
    def build_support_prompt(
        persona: SupportPersona,
        context: str = "",
        is_opening: bool = False,
        is_closing: bool = False
    ) -> Tuple[str, str]:
        """
        Build prompt for support agent based on persona and conversation context.

        Args:
            persona: Support persona with company, policies, etc.
            context: Formatted conversation history
            is_opening: True if this is the opening greeting
            is_closing: True if this is the closing statement

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # Build the base system prompt (matching local_orchestrator.py lines 219-234)
        system_prompt = persona.system_prompt if persona.system_prompt else "You are a helpful customer support agent."

        # Add company and agent info
        if persona.company_name:
            system_prompt = f"You work for {persona.company_name}. " + system_prompt
        if persona.agent_name:
            system_prompt = f"Your name is {persona.agent_name}. " + system_prompt

        # Add policies
        if persona.policies:
            system_prompt += f"\n\nPolicies to follow:\n" + "\n".join(f"- {p}" for p in persona.policies)

        # Add guardrails
        if persona.guardrails:
            system_prompt += f"\n\nGuardrails:\n" + "\n".join(f"- {g}" for g in persona.guardrails)

        # Build user prompt based on conversation stage
        if is_opening:
            prompt = """This is the start of a new call. Greet the customer warmly and introduce yourself.
Follow your guidelines for the opening script. State your name, company, and the purpose of the call.
Keep it natural and conversational. Do not use any formatting or quotation marks."""
        elif is_closing:
            prompt = f"""Conversation so far:
{context}

The customer seems satisfied. Provide a warm closing to end the conversation.
Keep it under 2 sentences. Do not use any formatting or quotation marks."""
        else:
            prompt = f"""Conversation so far:
{context}

Respond professionally to help the customer. Keep it under 2 sentences.
Follow your guidelines and policies. Do not use any formatting or quotation marks."""

        return system_prompt, prompt

    @staticmethod
    def build_livekit_agent_instructions(
        persona: SupportPersona,
        max_turns: Optional[int] = None
    ) -> str:
        """
        Build complete instructions for LiveKit voice agents.
        This combines system and initial prompts for the agent's instructions.

        Args:
            persona: Support persona
            max_turns: Optional max number of conversation turns

        Returns:
            Complete instruction string for LiveKit agent
        """
        # Get the opening prompt
        system_prompt, opening_prompt = PromptBuilder.build_support_prompt(
            persona,
            context="",
            is_opening=True
        )

        # Combine for LiveKit agent instructions
        instructions = system_prompt + "\n\n" + opening_prompt

        if max_turns:
            instructions += f"\n\nNote: This conversation should be limited to {max_turns} exchanges."

        return instructions

    @staticmethod
    def build_customer_instructions(
        persona: CustomerPersona,
        max_turns: Optional[int] = None
    ) -> str:
        """
        Build complete instructions for customer agent.

        Args:
            persona: Customer persona
            max_turns: Optional max number of conversation turns

        Returns:
            Complete instruction string for customer agent
        """
        system_prompt, user_prompt = PromptBuilder.build_customer_prompt(
            persona,
            context=""
        )

        # Combine system and user prompts if system prompt exists
        if system_prompt:
            instructions = system_prompt + "\n\n" + user_prompt
        else:
            instructions = user_prompt

        if max_turns:
            instructions += f"\n\nNote: After {max_turns} exchanges, indicate you're satisfied and end the call."

        return instructions