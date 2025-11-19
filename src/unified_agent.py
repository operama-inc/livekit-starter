#!/usr/bin/env python3
"""
Unified Agent - Single worker that can handle both customer and support roles
This solves the dispatch routing issue by having one worker handle all dispatches
"""
import os
import logging
import json
import asyncio
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
    inference
)
from livekit import rtc
from livekit.plugins import openai, cartesia, silero

from voice_conversation_generator.services import PersonaService
from voice_conversation_generator.services.prompt_builder import PromptBuilder

load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnifiedAgent(Agent):
    """Unified agent that can be either customer or support based on configuration"""

    def __init__(self, role: str, persona):
        self.role = role
        self.persona = persona

        # Build instructions based on role
        if role == "customer":
            instructions = PromptBuilder.build_customer_instructions(persona, 5)
        else:
            instructions = PromptBuilder.build_livekit_agent_instructions(persona, None)

        super().__init__(instructions=instructions)


async def unified_entrypoint(ctx: JobContext):
    """Unified entry point that handles both customer and support roles"""

    logger.info("="*50)
    logger.info(f"UNIFIED AGENT: Received job request")
    logger.info(f"Room: {ctx.room.name}")
    logger.info(f"Job ID: {ctx.job.id if hasattr(ctx, 'job') else 'N/A'}")
    logger.info(f"Dispatch ID: {ctx.dispatch_id if hasattr(ctx, 'dispatch_id') else 'N/A'}")
    logger.info("="*50)

    # Try multiple ways to get the role
    role = None

    # Method 1: Check dispatch metadata (from explicit dispatch)
    if hasattr(ctx, 'dispatch') and hasattr(ctx.dispatch, 'metadata'):
        try:
            dispatch_metadata = json.loads(ctx.dispatch.metadata)
            role = dispatch_metadata.get('role')
            logger.info(f"Got role from dispatch metadata: {role}")
        except:
            pass

    # Method 2: Check job metadata
    if not role and hasattr(ctx, 'metadata'):
        try:
            job_metadata = json.loads(ctx.metadata) if isinstance(ctx.metadata, str) else ctx.metadata
            role = job_metadata.get('role')
            logger.info(f"Got role from job metadata: {role}")
        except:
            pass

    # Method 3: Parse room metadata
    if not role and ctx.room.metadata:
        metadata = ctx.room.metadata
        parts = metadata.split(":")

        # Check if we're looking at customer_id:support_id:max_turns format
        if len(parts) >= 2:
            # Determine role based on participant count
            participants = ctx.room.remote_participants
            agent_count = sum(1 for p in participants.values() if "agent" in p.identity.lower())

            if agent_count == 0:
                role = "customer"
                logger.info(f"First agent in room, taking customer role")
            else:
                role = "support"
                logger.info(f"Second agent in room, taking support role")

    # Method 4: Default based on participant count
    if not role:
        participants = ctx.room.remote_participants
        agent_count = sum(1 for p in participants.values() if "agent" in p.identity.lower())

        if agent_count == 0:
            role = "customer"
            logger.info(f"No agents in room, defaulting to customer role")
        else:
            role = "support"
            logger.info(f"Agent(s) already in room, defaulting to support role")

    logger.info(f"FINAL ROLE: {role}")

    # Parse room metadata for persona info
    metadata = ctx.room.metadata or "cooperative_parent:default:5"
    parts = metadata.split(":")
    customer_id = parts[0] if len(parts) > 0 else "cooperative_parent"
    support_id = parts[1] if len(parts) > 1 else "default"
    max_turns = int(parts[2]) if len(parts) > 2 else 5

    # Load personas
    persona_service = PersonaService(tts_provider="cartesia")
    persona_service.load_default_personas()

    # Get appropriate persona based on role
    if role == "customer":
        persona = persona_service.get_customer_persona(customer_id)
        if not persona:
            logger.error(f"Customer persona '{customer_id}' not found")
            return
        logger.info(f"Using customer persona: {persona.name}")
    else:
        persona = persona_service.get_support_persona(support_id)
        if not persona:
            logger.error(f"Support persona '{support_id}' not found")
            return
        logger.info(f"Using support persona: {persona.agent_name}")

    # Create agent
    agent = UnifiedAgent(role, persona)

    # Get voice ID
    voice_id = persona.voice_config.voice_id if persona.voice_config else "fd2ada67-c2d9-4afe-b474-6386b87d8fc3"

    # Create voice session
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-streaming"),
        llm=openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4-mini")),
        tts=cartesia.TTS(voice=voice_id),
        vad=silero.VAD.load()
    )

    # Start the session
    await session.start(
        agent=agent,
        room=ctx.room
    )

    # Connect to room
    await ctx.connect()

    logger.info(f"Connected as {role} agent")

    # If customer, initiate conversation after delay
    if role == "customer":
        await asyncio.sleep(3)
        logger.info("Customer initiating conversation...")
        await session.say("Hello, I need help with my account.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=unified_entrypoint
        # No agent_name specified - this worker handles ALL dispatches
    ))