#!/usr/bin/env python3
"""
Unified Agent V2 - Fixed race condition with coordination via shared state
Single worker that can handle both customer and support roles
"""
import os
import logging
import json
import asyncio
from pathlib import Path
import sys
import time
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

# Coordination file for role assignment
COORDINATION_FILE = Path("/tmp/livekit_agent_roles.json")
COORDINATION_LOCK = Path("/tmp/livekit_agent_roles.lock")


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


def acquire_lock(timeout=5):
    """Simple file-based lock mechanism"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Try to create lock file exclusively
            COORDINATION_LOCK.touch(exist_ok=False)
            return True
        except FileExistsError:
            time.sleep(0.1)
    return False


def release_lock():
    """Release the lock"""
    try:
        COORDINATION_LOCK.unlink()
    except FileNotFoundError:
        pass


def get_role_for_room(room_name: str, job_id: str) -> str:
    """Determine role for this agent using coordination file"""

    # Acquire lock to prevent race condition
    if not acquire_lock():
        logger.error("Failed to acquire lock for role coordination")
        # Default to customer if we can't get lock
        return "customer"

    try:
        # Read existing coordination data
        coordination_data = {}
        if COORDINATION_FILE.exists():
            try:
                with open(COORDINATION_FILE, 'r') as f:
                    coordination_data = json.load(f)
            except:
                coordination_data = {}

        # Check if room already has role assignments
        room_data = coordination_data.get(room_name, {})

        # If this job already has a role, return it
        if job_id in room_data:
            role = room_data[job_id]
            logger.info(f"Job {job_id} already assigned role: {role}")
            return role

        # Determine new role based on existing assignments
        if not room_data:
            # First agent in room becomes customer
            role = "customer"
            room_data[job_id] = role
            logger.info(f"First agent in room {room_name}, assigning customer role")
        else:
            # Check if we already have a customer
            has_customer = "customer" in room_data.values()
            if not has_customer:
                role = "customer"
                logger.info(f"No customer in room yet, assigning customer role")
            else:
                role = "support"
                logger.info(f"Customer already exists, assigning support role")
            room_data[job_id] = role

        # Save updated coordination data
        coordination_data[room_name] = room_data
        with open(COORDINATION_FILE, 'w') as f:
            json.dump(coordination_data, f)

        return role

    finally:
        release_lock()


async def unified_entrypoint(ctx: JobContext):
    """Unified entry point that handles both customer and support roles"""

    job_id = ctx.job.id if hasattr(ctx, 'job') else "unknown"
    room_name = ctx.room.name

    logger.info("="*50)
    logger.info(f"UNIFIED AGENT V2: Received job request")
    logger.info(f"Room: {room_name}")
    logger.info(f"Job ID: {job_id}")
    logger.info("="*50)

    # Get role using coordination file
    role = get_role_for_room(room_name, job_id)
    logger.info(f"ASSIGNED ROLE: {role}")

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


def cleanup_old_room_data():
    """Clean up coordination data for old rooms"""
    if COORDINATION_FILE.exists():
        try:
            with open(COORDINATION_FILE, 'r') as f:
                data = json.load(f)

            # Keep only recent rooms (you could add timestamp tracking)
            # For now, just limit to 10 rooms
            if len(data) > 10:
                # Keep only the 10 most recent rooms
                rooms = list(data.keys())
                for room in rooms[:-10]:
                    del data[room]

                with open(COORDINATION_FILE, 'w') as f:
                    json.dump(data, f)
        except:
            pass


if __name__ == "__main__":
    # Clean up old coordination data periodically
    cleanup_old_room_data()

    cli.run_app(WorkerOptions(
        entrypoint_fnc=unified_entrypoint
        # No agent_name specified - this worker handles ALL dispatches
    ))