#!/usr/bin/env python
"""
Working Agent-to-Agent Voice Communication
Uses proper RoomInputOptions to enable agent-to-agent speech detection
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    RoomInputOptions,
    RoomOutputOptions,
    cli,
    WorkerOptions,
)
from livekit.agents import inference, llm as agents_llm
from livekit.plugins import cartesia, openai, silero

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add file handler for conversation logging
def setup_conversation_logging(room_name: str):
    """Setup file-based logging for conversation capture"""
    log_file = Path(f"/tmp/agent_conversation_{room_name}.log")
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info(f"Conversation logging to: {log_file}")
    return log_file

# Load prompts
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SUPPORT_PROMPT = (PROMPTS_DIR / "support_agent_system_prompt.txt").read_text()
INTERMEDIATE_PROMPT = (PROMPTS_DIR / "customer_support_agent_intermediate_prompt.txt").read_text()

# Coordination file for role assignment
COORDINATION_FILE = Path("/tmp/livekit_agent_coordination.json")
COORDINATION_LOCK = Path("/tmp/livekit_agent_coordination.lock")


def acquire_lock() -> bool:
    """Acquire lock for coordination file"""
    try:
        COORDINATION_LOCK.touch(exist_ok=False)
        return True
    except FileExistsError:
        # Wait and retry
        import time
        for _ in range(10):
            time.sleep(0.1)
            try:
                COORDINATION_LOCK.touch(exist_ok=False)
                return True
            except FileExistsError:
                continue
        return False


def release_lock():
    """Release lock"""
    try:
        COORDINATION_LOCK.unlink()
    except FileNotFoundError:
        pass


def get_role_for_room(room_name: str, job_id: str) -> str:
    """Determine role for this agent using coordination file"""

    if not acquire_lock():
        logger.error("Failed to acquire lock")
        return "customer"  # Fallback

    try:
        # Load or create coordination data
        if COORDINATION_FILE.exists():
            with open(COORDINATION_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = {}

        # Check if room already has assignments
        if room_name not in data:
            data[room_name] = {"customer": None, "support": None}

        room_data = data[room_name]

        # Assign first available role
        if room_data["customer"] is None:
            room_data["customer"] = job_id
            role = "customer"
        elif room_data["support"] is None:
            room_data["support"] = job_id
            role = "support"
        else:
            # Check if this job already has a role
            if room_data["customer"] == job_id:
                role = "customer"
            elif room_data["support"] == job_id:
                role = "support"
            else:
                logger.error(f"Room {room_name} already has both roles assigned")
                role = "customer"  # Fallback

        # Save updated data
        with open(COORDINATION_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        return role

    finally:
        release_lock()


class UnifiedAgent(Agent):
    """Unified agent that can play both customer and support roles"""

    def __init__(self, role: str, instructions: str):
        self.role = role
        super().__init__(instructions=instructions)
        logger.info(f"[OK] UnifiedAgent initialized with role={role}")

    async def on_enter(self):
        """Called when agent enters the room - support initiates conversation"""
        logger.info(f"[{self.role}] on_enter called")

        if self.role == "support":
            # Support agent initiates the conversation
            logger.info("[support] Initiating conversation with greeting")
            await self.session.say(
                "Hello... I am फ़ैज़ान speaking from Jodo, the official fee payment partner of Delhi Public School. Am I speaking to Yash?",
                allow_interruptions=True,
            )

    async def on_user_message(self, message, ctx: RunContext):
        """Log incoming messages for debugging"""
        logger.info(f"[HEARD] [{self.role}] FROM OTHER AGENT: '{message.text}'")
        return await super().on_user_message(message, ctx)

    async def on_agent_speech_committed(self, message, ctx: RunContext):
        """Log agent's own speech"""
        logger.info(f"[SAID] [{self.role}] TO OTHER AGENT: '{message.text}'")
        return await super().on_agent_speech_committed(message, ctx)


def build_customer_instructions() -> str:
    """Build instructions for customer agent"""
    return """You are Yash, a parent whose child's fee payment has failed.

## Your Situation
- Your child रोहित studies at Delhi Public School
- The fee payment of Five Thousand Seven Hundred Eleven Rupees And Forty Five Paise failed on October 5 due to insufficient balance
- You enrolled in Jodo's Flex payment which auto-debits fees

## Your Personality
- You are cooperative and willing to resolve the issue
- You respond naturally to questions
- You ask clarifying questions when needed
- You keep responses concise and natural

## How to Respond
- Confirm your identity when asked
- Acknowledge the payment issue
- Ask relevant questions about rescheduling
- Select a payment date when offered options between December 15-20
- Keep responses short and conversational

## Language
- Respond in English unless the agent switches to Hindi
- Use natural conversational language
- Be polite and cooperative
"""


def build_support_instructions() -> str:
    """Build instructions for support agent using provided prompts"""
    # Combine the two prompt files
    return f"""{SUPPORT_PROMPT}

{INTERMEDIATE_PROMPT}
"""


async def unified_entrypoint(ctx: JobContext):
    """Unified entry point that handles both customer and support roles"""

    room_name = ctx.room.name
    logger.info(f"[START] Job starting for room: {room_name}")

    # Setup conversation logging
    log_file = setup_conversation_logging(room_name)

    # Get role using coordination file
    role = get_role_for_room(room_name, ctx.job.id)
    logger.info(f"[ROLE] ASSIGNED ROLE: {role}")

    # Build instructions based on role
    if role == "support":
        instructions = build_support_instructions()
        voice_id = "onyx"  # Male voice (OpenAI TTS)
    else:  # customer
        instructions = build_customer_instructions()
        voice_id = "alloy"  # Default neutral voice (OpenAI TTS)

    # Create agent
    agent = UnifiedAgent(role=role, instructions=instructions)

    # Create session with proper configuration
    logger.info(f"[{role}] Creating AgentSession with agent-to-agent audio enabled")
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-streaming"),
        llm=openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4.1-mini")),
        tts=openai.TTS(voice=voice_id if role == "support" else "alloy"),
        vad=silero.VAD.load(),
    )

    # Start session with proper RoomInputOptions to enable agent-to-agent communication
    logger.info(f"[{role}] Starting session with RoomInputOptions(participant_kinds=[AGENT, STANDARD])")
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            # 🔑 KEY FIX: Listen to both AGENT and STANDARD participants
            participant_kinds=[
                rtc.ParticipantKind.PARTICIPANT_KIND_AGENT,
                rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD,
            ],
        ),
        room_output_options=RoomOutputOptions(
            audio_enabled=True,
            transcription_enabled=True,
        ),
    )

    logger.info(f"[{role}] [OK] Session started successfully - agent is now listening to room audio")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=unified_entrypoint,
        )
    )
