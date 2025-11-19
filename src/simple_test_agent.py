#!/usr/bin/env python3
"""
Simple test agent that can be either customer or support based on identity
"""
import os
import logging
from pathlib import Path
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestAgent(Agent):
    """Test agent that can be customer or support"""

    def __init__(self, role: str):
        self.role = role
        if role == "customer":
            instructions = """You are a customer calling support.
            Start by saying hello and asking for help with your account.
            Keep your responses brief, under 2 sentences.
            After 3 exchanges, thank the agent and say goodbye."""
        else:
            instructions = """You are a support agent helping customers.
            Be helpful and friendly. Keep responses brief, under 2 sentences.
            Ask how you can help and provide assistance."""

        super().__init__(instructions=instructions)


async def entrypoint(ctx: JobContext):
    """Main entry point"""
    # Determine role from room metadata or default to first agent
    room = ctx.room
    participants = room.remote_participants

    # Check if we're the first or second agent
    agent_count = sum(1 for p in participants.values() if "agent" in p.identity.lower())

    if agent_count == 0:
        role = "customer"
        logger.info("Starting as CUSTOMER agent")
    else:
        role = "support"
        logger.info("Starting as SUPPORT agent")

    # Create appropriate agent
    agent = TestAgent(role)

    # Create session with agent-to-agent audio
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-streaming"),
        llm=openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4-mini")),
        tts=cartesia.TTS(),
        vad=silero.VAD.load()
    )

    # Start session - agents can hear each other by default
    await session.start(
        agent=agent,
        room=ctx.room
    )

    # Connect to room
    await ctx.connect()

    # If we're the customer, wait a bit then start the conversation
    if role == "customer":
        await asyncio.sleep(2)
        await session.say("Hello, I need help with my account please.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint
    ))