#!/usr/bin/env python
"""
Customer Agent for agent-to-agent communication.
This agent acts as a customer with questions or issues.
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


class CustomerAgent(Agent):
    """Customer agent that initiates support requests."""

    def __init__(self, session: agents.AgentSession):
        # Load system prompt first
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "customer_agent_prompt.txt")
        try:
            with open(prompt_path, "r") as f:
                system_prompt = f.read()
            logger.info(f"[CUSTOMER] Loaded system prompt from {prompt_path}")
        except Exception as e:
            logger.error(f"[CUSTOMER] Failed to load system prompt: {e}")
            system_prompt = "You are a customer named Yash."

        # Initialize the base Agent class with instructions
        super().__init__(
            instructions=system_prompt
        )

        self._agent_session = session
        self.conversation_turns = 0
        logger.info(f"[CUSTOMER] Agent initialized")

    async def on_enter(self):
        """Called when the agent enters the room."""
        logger.info(f"[CUSTOMER] on_enter called - Customer entering room")
        # Wait for support agent to speak first
        # But if silence for too long, say hello
        await asyncio.sleep(5)
        # We don't want to interrupt if support agent is speaking, but we can't easily check that here without VAD events.
        # For now, let's just wait. The support agent is configured to speak after 2s.
        logger.info(f"[CUSTOMER] Waiting for support agent to speak...")

    async def on_exit(self):
        """Called when the agent exits the room."""
        logger.info(f"[CUSTOMER] on_exit called - Customer leaving room")

    async def on_user_turn_completed(self, turn_ctx, user_message):
        """Called when a user completes their turn (stops speaking)."""
        text = user_message.text_content
        logger.info(f"[CUSTOMER] Heard from support: '{text}'")

        self.conversation_turns += 1

        # The Agent base class handles context management internally in v1.x
        # We don't need to manually manage ChatContext anymore
        # Just log what we heard for debugging
        logger.info(f"[CUSTOMER] Turn {self.conversation_turns}: Processing response...")

        # The base Agent class will handle the response generation
        # We can add custom logic here if needed
        pass


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the customer agent."""
    logger.info(f"[CUSTOMER] Job started - job_id: {ctx.job.id}, room: {ctx.job.room.name}")

    # Connect to the room
    await ctx.connect()
    logger.info(f"[CUSTOMER] Connected to room: {ctx.room.name}")

    # Log all participants in the room
    participants = list(ctx.room.remote_participants.values())
    logger.info(f"[CUSTOMER] Remote participants in room: {len(participants)}")
    for p in participants:
        logger.info(f"[CUSTOMER] - {p.identity}")

    # Configure the agent session
    session = agents.AgentSession(
        stt=agents.stt.StreamAdapter(
            stt=openai.STT(model="whisper-1"),
            vad=silero.VAD.load(),
        ),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(voice="alloy"),  # Different voice from support
    )

    # Create the customer agent
    customer_agent = CustomerAgent(session)

    logger.info(f"[CUSTOMER] Starting session with agent-to-agent audio enabled")

    # Configure room input to listen to AGENT participants
    room_input_options = RoomInputOptions(
        participant_kinds=[api.ParticipantInfo.Kind.AGENT, api.ParticipantInfo.Kind.STANDARD],
    )

    # Start the session
    await session.start(
        agent=customer_agent,
        room=ctx.room,
        room_input_options=room_input_options,
        room_output_options=RoomOutputOptions(),
    )

    logger.info(f"[CUSTOMER] Session started successfully - agent is ready to interact")

    # Save transcript on shutdown
    async def save_transcript():
        """Save the conversation transcript when shutting down."""
        transcript_file = f"/tmp/transcript_customer_{ctx.room.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            # In v1.x, the Agent base class manages the conversation internally
            # We can save basic metadata for now
            with open(transcript_file, "w") as f:
                metadata = {
                    "room": ctx.room.name,
                    "agent": "customer-agent",
                    "timestamp": datetime.now().isoformat()
                }
                json.dump(metadata, f, indent=2)
            logger.info(f"[CUSTOMER] Metadata saved to {transcript_file}")
        except Exception as e:
            logger.error(f"[CUSTOMER] Error saving transcript: {e}")

    ctx.add_shutdown_callback(save_transcript)

    # Keep the agent running
    logger.info(f"[CUSTOMER] Agent ready and will initiate conversation")

    # Monitor conversation items
    @session.on("conversation_item_added")
    def on_item_added(ev):
        """Log when conversation items are added."""
        item = ev.item
        logger.info(f"[CUSTOMER-ITEM] role={item.role} text={item.text_content!r}")


if __name__ == "__main__":
    # Configure the worker with explicit agent_name
    worker_opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="customer-agent",  # CRITICAL: Explicit agent name for dispatch
    )

    # Run the CLI
    cli.run_app(worker_opts)