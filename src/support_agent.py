#!/usr/bin/env python3
"""
Support Agent - Provides customer support in conversations
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


class SupportAgent(Agent):
    """Support agent that helps customers"""

    def __init__(self, persona):
        # Build instructions using the shared PromptBuilder
        instructions = PromptBuilder.build_livekit_agent_instructions(persona, None)

        super().__init__(
            instructions=instructions
        )


async def support_entrypoint(ctx: JobContext):
    """Support agent entry point"""
    logger.info(f"Support agent joining room: {ctx.room.name}")

    # Check for job metadata from explicit dispatch
    job_metadata = ctx.metadata if hasattr(ctx, 'metadata') else None
    logger.info(f"Job metadata: {job_metadata}")

    # Parse room metadata: "customer_id:support_id:max_turns"
    metadata = ctx.room.metadata or "cooperative_parent:default:5"
    parts = metadata.split(":")
    support_id = parts[1] if len(parts) > 1 else "default"

    # Load persona
    persona_service = PersonaService(tts_provider="cartesia")
    persona_service.load_default_personas()
    support_persona = persona_service.get_support_persona(support_id)

    if not support_persona:
        logger.error(f"Support persona '{support_id}' not found")
        return

    logger.info(f"Support: {support_persona.agent_name}")

    # Create agent and session
    agent = SupportAgent(support_persona)

    voice_id = support_persona.voice_config.voice_id if support_persona.voice_config else "fd2ada67-c2d9-4afe-b474-6386b87d8fc3"

    # Create voice session with models
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-streaming"),
        llm=openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4-mini")),
        tts=cartesia.TTS(voice=voice_id),
        vad=silero.VAD.load()
    )

    # Start the session with our agent - enable agent-to-agent communication
    await session.start(
        agent=agent,
        room=ctx.room
    )

    # Connect to room
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=support_entrypoint,
        agent_name="support-agent"  # Explicit name for dispatch
    ))