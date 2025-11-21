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
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")

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
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SupportAgent(Agent):
    """Support agent that responds to customer inquiries."""

    def __init__(self):
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

        self.conversation_turns = 0
        logger.info(f"[SUPPORT] Agent initialized")

    async def on_enter(self):
        """Called when the agent enters the room."""
        logger.info(f"[SUPPORT] on_enter called - Support agent ready to help!")
        # Initial greeting after a short delay to ensure customer is connected
        await asyncio.sleep(2)

        # Support initiates the conversation with instructions
        await self.session.generate_reply(
            instructions=(
                "You are calling the customer about a failed or delayed payment. "
                "Greet them briefly by saying 'Hello... I am फ़ैज़ान speaking from Jodo, "
                "the official fee payment partner of Delhi Public School. Am I speaking to Yash?' "
                "Wait for their response."
            ),
            allow_interruptions=True,
        )

    async def on_exit(self):
        """Called when the agent exits the room."""
        logger.info(f"[SUPPORT] on_exit called - Support agent signing off")

    async def on_user_turn_completed(self, turn_ctx, user_message):
        """Called when a user completes their turn (stops speaking)."""
        text = user_message.text_content
        logger.info(f"[SUPPORT] Heard from customer: '{text}'")

        # Increment conversation turns
        self.conversation_turns += 1
        logger.info(f"[SUPPORT] Turn {self.conversation_turns} of max 6")

        # After max turns, close the conversation
        if self.conversation_turns >= 6:
            logger.info(f"[SUPPORT] Max turns reached, ending conversation")
            await self.session.generate_reply(
                instructions=(
                    "Politely summarize any agreement about rescheduling the payment, "
                    "thank the customer, and clearly end the call. Do not ask any new questions."
                ),
                allow_interruptions=False,
            )
            return  # Skip normal processing

        # Otherwise continue normal pipeline
        await super().on_user_turn_completed(turn_ctx, user_message)


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the support agent."""
    # Enhanced logging for job dispatch debugging
    logger.info(f"[SUPPORT] ==================== JOB RECEIVED ====================")
    logger.info(f"[SUPPORT] Job ID: {ctx.job.id}")
    logger.info(f"[SUPPORT] Room Name: {ctx.job.room.name}")
    logger.info(f"[SUPPORT] Room SID: {ctx.job.room.sid}")
    logger.info(f"[SUPPORT] Agent Name in Job: {ctx.job.agent_name if hasattr(ctx.job, 'agent_name') else 'N/A'}")
    logger.info(f"[SUPPORT] Participant Identity: {ctx.job.participant_identity if hasattr(ctx.job, 'participant_identity') else 'N/A'}")
    logger.info(f"[SUPPORT] =====================================================")

    # Connect to the room
    logger.info(f"[SUPPORT] Attempting to connect to room...")
    await ctx.connect()
    logger.info(f"[SUPPORT] Successfully connected to room: {ctx.room.name}")

    # Log all participants in the room
    participants = list(ctx.room.remote_participants.values())
    logger.info(f"[SUPPORT] Remote participants in room: {len(participants)}")
    for p in participants:
        logger.info(f"[SUPPORT] - {p.identity}")

    # Configure the agent session with proper VAD and turn detection
    session = agents.AgentSession(
        stt=openai.STT(model="whisper-1"),
        llm=openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4o-mini")),
        tts=openai.TTS(voice="nova"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
        allow_interruptions=True,
    )

    # Create the support agent
    support_agent = SupportAgent()

    logger.info(f"[SUPPORT] Starting session with agent-to-agent audio enabled")

    # Configure room input to listen ONLY to AGENT participants
    room_input_options = RoomInputOptions(
        participant_kinds=[api.ParticipantInfo.Kind.AGENT],
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
        from datetime import datetime
        import json

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        transcript_dir = "/Users/sid/Documents/GitHub/livekit-starter/data/livekit_conversations"
        os.makedirs(transcript_dir, exist_ok=True)
        transcript_file = f"{transcript_dir}/transcript_support_{ctx.room.name}_{ts}.json"

        try:
            # Get messages from session history
            messages = []
            if hasattr(session, 'chat_ctx') and session.chat_ctx and hasattr(session.chat_ctx, 'messages'):
                messages = [m.to_dict() for m in session.chat_ctx.messages]

            # Save transcript with metadata
            transcript_data = {
                "room": ctx.room.name,
                "agent": "support-agent",
                "timestamp": datetime.now().isoformat(),
                "messages": messages,
                "conversation_turns": support_agent.conversation_turns if 'support_agent' in locals() else 0
            }

            with open(transcript_file, "w") as f:
                json.dump(transcript_data, f, indent=2)

            logger.info(f"[SUPPORT] Saved transcript to {transcript_file} ({len(messages)} messages)")
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
    # Explicit BOOT logging to verify configuration
    logging.basicConfig(level=logging.INFO)

    # Get port from environment variable, default to 8081
    http_port = int(os.getenv("SUPPORT_AGENT_PORT", "8081"))

    logger.info(
        "[BOOT] Starting worker script=%s agent_name=%s LIVEKIT_URL=%s PORT=%d",
        __file__,
        "support-agent",
        os.getenv("LIVEKIT_URL"),
        http_port,
    )

    # Configure the worker with explicit agent_name
    # Note: Port is configured via CLI args, not WorkerOptions
    worker_opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="support-agent",  # CRITICAL: Explicit agent name for dispatch
    )

    # Run the CLI
    cli.run_app(worker_opts)