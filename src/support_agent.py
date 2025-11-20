#!/usr/bin/env python
"""
Support Agent for agent-to-agent communication.
This agent acts as a customer support representative.
"""

import asyncio
import logging
import json
import os
from datetime import datetime

from livekit import agents, rtc, api
from livekit.agents import (
    Agent,
    JobContext,
    WorkerOptions,
    cli,
    RoomInputOptions,
    RoomOutputOptions,
    llm,
)
from livekit.plugins import openai, silero

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SupportAgent(Agent):
    """Support agent that responds to customer inquiries."""

    def __init__(self, session: agents.AgentSession):
        # Load system prompt first
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "support_agent_system_prompt.txt")
        try:
            with open(prompt_path, "r") as f:
                system_prompt = f.read()
            logger.info(f"[SUPPORT] Loaded system prompt from {prompt_path}")
        except Exception as e:
            logger.error(f"[SUPPORT] Failed to load system prompt: {e}")
            system_prompt = "You are a helpful customer support agent."

        # Initialize the base Agent class with instructions
        super().__init__(
            instructions=system_prompt
        )

        self._agent_session = session
        self.conversation_turns = 0
        logger.info(f"[SUPPORT] Agent initialized")

    async def on_enter(self):
        """Called when the agent enters the room."""
        logger.info(f"[SUPPORT] on_enter called - Support agent ready to help!")
        # Initial greeting after a short delay to ensure customer is connected
        await asyncio.sleep(2)

        # Greeting from the prompt
        greeting = "Hello... I am फ़ैज़ान speaking from Jodo, the official fee payment partner of Delhi Public School. Am I speaking to Yash?"

        # The base Agent class handles context management internally
        await self._agent_session.say(greeting)

    async def on_exit(self):
        """Called when the agent exits the room."""
        logger.info(f"[SUPPORT] on_exit called - Support agent signing off")

    async def on_user_turn_completed(self, turn_ctx, user_message):
        """Called when a user completes their turn (stops speaking)."""
        text = user_message.text_content
        logger.info(f"[SUPPORT] Heard from customer: '{text}'")

        # The Agent base class handles context management internally in v1.x
        # We don't need to manually manage ChatContext anymore
        # Just log what we heard for debugging
        logger.info(f"[SUPPORT] Processing response...")

        # The base Agent class will handle the response generation
        # We can add custom logic here if needed
        pass


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the support agent."""
    logger.info(f"[SUPPORT] Job started - job_id: {ctx.job.id}, room: {ctx.job.room.name}")

    # Connect to the room
    await ctx.connect()
    logger.info(f"[SUPPORT] Connected to room: {ctx.room.name}")

    # Log all participants in the room
    participants = list(ctx.room.remote_participants.values())
    logger.info(f"[SUPPORT] Remote participants in room: {len(participants)}")
    for p in participants:
        logger.info(f"[SUPPORT] - {p.identity}")

    # Configure the agent session
    session = agents.AgentSession(
        stt=agents.stt.StreamAdapter(
            stt=openai.STT(model="whisper-1"),
            vad=silero.VAD.load(),
        ),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(voice="nova"),
    )

    # Create the support agent
    support_agent = SupportAgent(session)

    logger.info(f"[SUPPORT] Starting session with agent-to-agent audio enabled")

    # Configure room input to listen to AGENT participants
    room_input_options = RoomInputOptions(
        participant_kinds=[api.ParticipantInfo.Kind.AGENT, api.ParticipantInfo.Kind.STANDARD],
    )

    # Start the session
    await session.start(
        agent=support_agent,
        room=ctx.room,
        room_input_options=room_input_options,
        room_output_options=RoomOutputOptions(),
    )

    logger.info(f"[SUPPORT] Session started successfully - agent is listening")

    # Save transcript on shutdown
    async def save_transcript():
        """Save the conversation transcript when shutting down."""
        transcript_file = f"/tmp/transcript_support_{ctx.room.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            # In v1.x, the Agent base class manages the conversation internally
            # We can save basic metadata for now
            with open(transcript_file, "w") as f:
                metadata = {
                    "room": ctx.room.name,
                    "agent": "support-agent",
                    "timestamp": datetime.now().isoformat()
                }
                json.dump(metadata, f, indent=2)
            logger.info(f"[SUPPORT] Metadata saved to {transcript_file}")
        except Exception as e:
            logger.error(f"[SUPPORT] Error saving transcript: {e}")

    ctx.add_shutdown_callback(save_transcript)

    # Keep the agent running
    logger.info(f"[SUPPORT] Agent ready and listening for customer messages")

    # Monitor conversation items
    @session.on("conversation_item_added")
    def on_item_added(ev):
        """Log when conversation items are added."""
        item = ev.item
        logger.info(f"[SUPPORT-ITEM] role={item.role} text={item.text_content!r}")


if __name__ == "__main__":
    # Configure the worker with explicit agent_name
    worker_opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="support-agent",  # CRITICAL: Explicit agent name for dispatch
    )

    # Run the CLI
    cli.run_app(worker_opts)