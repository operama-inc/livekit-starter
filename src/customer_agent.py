#!/usr/bin/env python
"""
Customer Agent for agent-to-agent communication.
This agent acts as a customer with questions or issues.
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


class CustomerAgent(Agent):
    """Customer agent that initiates support requests."""

    def __init__(self, session: agents.AgentSession):
        self.session = session
        self.conversation_turns = 0
        logger.info(f"[CUSTOMER] Agent initialized")

    async def on_enter(self):
        """Called when the agent enters the room."""
        logger.info(f"[CUSTOMER] on_enter called - Customer entering room")
        # Wait a moment then start the conversation
        await asyncio.sleep(3)
        await self.session.say("Hello? Is anyone there? I need help with my recent order.")
        self.conversation_turns += 1

    async def on_exit(self):
        """Called when the agent exits the room."""
        logger.info(f"[CUSTOMER] on_exit called - Customer leaving room")

    async def on_user_turn_completed(self, turn_ctx, user_message):
        """Called when a user completes their turn (stops speaking)."""
        text = user_message.text_content
        logger.info(f"[CUSTOMER] Heard from support: '{text}'")

        self.conversation_turns += 1

        # Customer responses based on support agent
        if "order number" in text.lower():
            response = "Yes, my order number is #12345. I ordered it last week but it hasn't arrived yet."
        elif "check your account" in text.lower() or "refund" in text.lower():
            response = "That would be great. I've been waiting for over a week now. Can you process the refund today?"
        elif "2-3 business days" in text.lower() or "shipping" in text.lower():
            response = "Thank you for checking! I appreciate your help with this."
        elif "anything else" in text.lower():
            response = "No, that's all for now. Thank you so much for your assistance!"
        elif "have a great" in text.lower() or "thank you for contacting" in text.lower():
            response = "Goodbye! Have a wonderful day!"
        else:
            # Default responses for continuing conversation
            if self.conversation_turns <= 2:
                response = "I placed an order last week and I still haven't received it. Can you help me?"
            elif self.conversation_turns <= 4:
                response = "I'm really concerned about my order. When will it arrive?"
            else:
                response = "Thank you for your help. I think that answers my questions."

        logger.info(f"[CUSTOMER] Responding with: '{response}'")
        await self.session.say(response)


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

    # Start the session
    await session.start(
        agent=customer_agent,
        room=ctx.room,
    )

    logger.info(f"[CUSTOMER] Session started successfully - agent is ready to interact")

    # Save transcript on shutdown
    async def save_transcript():
        """Save the conversation transcript when shutting down."""
        transcript_file = f"/tmp/transcript_customer_{ctx.room.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(transcript_file, "w") as f:
                json.dump(session.history.to_dict(), f, indent=2)
            logger.info(f"[CUSTOMER] Transcript saved to {transcript_file}")
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