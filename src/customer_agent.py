#!/usr/bin/env python3
"""
Customer Agent - Simulates customer in support conversations
"""
import os
import logging
from pathlib import Path
import sys
from dotenv import load_dotenv

# Load environment variables from .env.local
load_dotenv(Path(__file__).parent.parent / ".env.local")

sys.path.insert(0, str(Path(__file__).parent.parent))

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    inference,
    voice
)
from livekit import rtc
from livekit.plugins import openai, cartesia, silero

from voice_conversation_generator.services import PersonaService
from voice_conversation_generator.services.prompt_builder import PromptBuilder
from voice_conversation_generator.services.context_manager import ContextManager

load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomerAgent(Agent):
    """Customer agent that responds to support"""

    def __init__(self, persona, max_turns=5):
        self.persona = persona
        self.turn_count = 0
        self.max_turns = max_turns

        # Build instructions using the shared PromptBuilder
        instructions = PromptBuilder.build_customer_instructions(persona, max_turns)

        super().__init__(
            instructions=instructions
        )


async def customer_entrypoint(ctx: JobContext):
    """Customer agent entry point"""
    logger.info(f"Customer agent joining room: {ctx.room.name}")

    # Check for job metadata from explicit dispatch
    job_metadata = ctx.metadata if hasattr(ctx, 'metadata') else None
    logger.info(f"Job metadata: {job_metadata}")

    # Parse room metadata: "customer_id:support_id:max_turns"
    metadata = ctx.room.metadata or "cooperative_parent:default:5"
    parts = metadata.split(":")
    customer_id = parts[0] if len(parts) > 0 else "cooperative_parent"
    max_turns = int(parts[2]) if len(parts) > 2 else 5

    # Load persona
    persona_service = PersonaService(tts_provider="cartesia")
    persona_service.load_default_personas()
    customer_persona = persona_service.get_customer_persona(customer_id)

    if not customer_persona:
        logger.error(f"Customer persona '{customer_id}' not found")
        return

    logger.info(f"Customer: {customer_persona.name}")

    # Create agent and session
    agent = CustomerAgent(customer_persona, max_turns)

    voice_id = customer_persona.voice_config.voice_id if customer_persona.voice_config else "fd2ada67-c2d9-4afe-b474-6386b87d8fc3"

    # Create voice session with models
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-streaming"),
        llm=openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4-mini")),
        tts=cartesia.TTS(voice=voice_id),
        vad=silero.VAD.load()
    )

    # Start the session with our agent - agents can hear each other by default
    await session.start(
        agent=agent,
        room=ctx.room
    )

    # Connect to room
    await ctx.connect()

    # Customer starts the conversation after a short delay
    import asyncio
    await asyncio.sleep(2)
    await session.say("Hello, I need help with my account.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=customer_entrypoint,
        agent_name="customer-agent"  # Explicit name for dispatch
    ))