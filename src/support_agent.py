#!/usr/bin/env python
"""
Support Agent for agent-to-agent communication.
This agent acts as a customer support representative.
"""

import asyncio
import logging
import json
from datetime import datetime

from livekit import agents, rtc
from livekit.agents import (
    Agent,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import openai, silero

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SupportAgent(Agent):
    """Support agent that responds to customer inquiries."""

    def __init__(self, session: agents.AgentSession):
        self.session = session
        self.conversation_turns = 0
        logger.info(f"[SUPPORT] Agent initialized")

    async def on_enter(self):
        """Called when the agent enters the room."""
        logger.info(f"[SUPPORT] on_enter called - Support agent ready to help!")
        # Initial greeting after a short delay to ensure customer is connected
        await asyncio.sleep(2)
        await self.session.say("Hello! This is customer support. How can I help you today?")

    async def on_exit(self):
        """Called when the agent exits the room."""
        logger.info(f"[SUPPORT] on_exit called - Support agent signing off")

    async def on_user_turn_completed(self, turn_ctx, user_message):
        """Called when a user completes their turn (stops speaking)."""
        text = user_message.text_content
        logger.info(f"[SUPPORT] Heard from customer: '{text}'")

        # Support agent responses
        if "refund" in text.lower():
            response = "I understand you'd like a refund. Let me check your account details. Can you provide your order number?"
        elif "order" in text.lower():
            response = "I can help you with your order. What seems to be the issue?"
        elif "shipping" in text.lower():
            response = "I'll check the shipping status for you right away. Your package should arrive within 2-3 business days."
        elif "thank" in text.lower():
            response = "You're very welcome! Is there anything else I can help you with today?"
        elif "bye" in text.lower() or "goodbye" in text.lower():
            response = "Thank you for contacting support. Have a great day!"
        else:
            response = f"I understand you said '{text}'. How can I assist you with that?"

        logger.info(f"[SUPPORT] Responding with: '{response}'")
        await self.session.say(response)


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

    # Start the session
    await session.start(
        agent=support_agent,
        room=ctx.room,
    )

    logger.info(f"[SUPPORT] Session started successfully - agent is listening")

    # Save transcript on shutdown
    async def save_transcript():
        """Save the conversation transcript when shutting down."""
        transcript_file = f"/tmp/transcript_support_{ctx.room.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(transcript_file, "w") as f:
                json.dump(session.history.to_dict(), f, indent=2)
            logger.info(f"[SUPPORT] Transcript saved to {transcript_file}")
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