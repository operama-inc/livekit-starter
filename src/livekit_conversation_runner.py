#!/usr/bin/env python
"""
LiveKit Conversation Runner for agent-to-agent communication.
This script creates a room and dispatches both support and customer agents to it.
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
import aiohttp

# Load environment variables
load_dotenv(".env.local")

# Import LiveKit SDK
from livekit import api, rtc
from livekit.api import room_service, agent_dispatch_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LiveKitConversationRunner:
    """Orchestrates agent-to-agent conversations in LiveKit."""

    def __init__(self):
        """Initialize the runner with LiveKit credentials."""
        self.url = os.getenv("LIVEKIT_URL")
        self.api_key = os.getenv("LIVEKIT_API_KEY")
        self.api_secret = os.getenv("LIVEKIT_API_SECRET")

        if not all([self.url, self.api_key, self.api_secret]):
            logger.error("Missing LiveKit credentials in environment")
            sys.exit(1)

        logger.info(f"Initialized with LiveKit URL: {self.url}")

    async def create_room(self, room_name: str) -> str:
        """Create a LiveKit room."""
        async with aiohttp.ClientSession() as session:
            room_api = room_service.RoomService(session, self.url, self.api_key, self.api_secret)

            try:
                # Create the room
                room = await room_api.create_room(
                    api.CreateRoomRequest(
                        name=room_name,
                        empty_timeout=300,  # 5 minutes
                        max_participants=10,
                    )
                )
                logger.info(f"Created room: {room_name}")
                return room_name
            except Exception as e:
                logger.error(f"Error creating room: {e}")
                raise

    async def dispatch_agent(self, room_name: str, agent_name: str):
        """Dispatch a specific agent to a room."""
        async with aiohttp.ClientSession() as session:
            dispatch_api = agent_dispatch_service.AgentDispatchService(
                session, self.url, self.api_key, self.api_secret
            )

            try:
                # Create dispatch request with specific agent_name
                dispatch_request = api.CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name=agent_name,  # CRITICAL: Specify which agent to dispatch
                )

                # Dispatch the agent
                dispatch = await dispatch_api.create_dispatch(dispatch_request)
                logger.info(f"Successfully dispatched {agent_name} to room {room_name}")
                return True  # Just return success status
            except Exception as e:
                logger.error(f"Error dispatching {agent_name}: {e}")
                raise

    async def monitor_room(self, room_name: str, duration: int = 60):
        """Monitor room participants for a specified duration."""
        async with aiohttp.ClientSession() as session:
            room_api = room_service.RoomService(session, self.url, self.api_key, self.api_secret)

            logger.info(f"Monitoring room {room_name} for {duration} seconds...")

            for i in range(0, duration, 5):
                try:
                    # List participants in the room
                    response = await room_api.list_participants(
                        api.ListParticipantsRequest(room=room_name)
                    )

                    # Access participants from the response object
                    participants = response.participants if hasattr(response, 'participants') else []

                    agent_count = sum(1 for p in participants if p.kind == api.ParticipantInfo.Kind.AGENT)
                    standard_count = sum(1 for p in participants if p.kind == api.ParticipantInfo.Kind.STANDARD)

                    logger.info(f"[{i:3d}s] Room {room_name}: {len(participants)} participants "
                              f"({agent_count} agents, {standard_count} standard)")

                    # Log participant details
                    for p in participants:
                        # Handle both enum and integer representations
                        kind_str = p.kind.name if hasattr(p.kind, 'name') else str(p.kind)
                        state_str = p.state.name if hasattr(p.state, 'name') else str(p.state)
                        logger.info(f"  - {p.identity} (kind: {kind_str}, state: {state_str})")

                except Exception as e:
                    logger.error(f"Error monitoring room: {e}")

                await asyncio.sleep(5)

    async def delete_room(self, room_name: str):
        """Delete a LiveKit room."""
        async with aiohttp.ClientSession() as session:
            room_api = room_service.RoomService(session, self.url, self.api_key, self.api_secret)

            try:
                await room_api.delete_room(api.DeleteRoomRequest(room=room_name))
                logger.info(f"Deleted room: {room_name}")
            except Exception as e:
                logger.error(f"Error deleting room: {e}")

    async def run_conversation(self, room_name: str = None, monitor_duration: int = 60):
        """Run a complete agent-to-agent conversation."""
        if not room_name:
            room_name = f"agent-conversation-{int(time.time())}"

        logger.info("=" * 60)
        logger.info(f"Starting agent-to-agent conversation in room: {room_name}")
        logger.info("=" * 60)

        try:
            # Step 1: Create the room
            await self.create_room(room_name)
            await asyncio.sleep(1)

            # Step 2: Dispatch both agents explicitly
            logger.info("Dispatching agents...")

            # Dispatch support agent
            await self.dispatch_agent(room_name, "support-agent")

            # Small delay between dispatches
            await asyncio.sleep(2)

            # Dispatch customer agent
            await self.dispatch_agent(room_name, "customer-agent")

            logger.info(f"Both agents dispatched successfully to room: {room_name}")

            # Step 3: Monitor the conversation
            await asyncio.sleep(3)  # Give agents time to connect
            await self.monitor_room(room_name, monitor_duration)

            logger.info("=" * 60)
            logger.info("Conversation monitoring complete")
            logger.info(f"Check /tmp/transcript_*_{room_name}_*.json for transcripts")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during conversation: {e}")
            raise
        finally:
            # Optional: Clean up the room
            # await self.delete_room(room_name)
            pass


async def main():
    """Main entry point."""
    runner = LiveKitConversationRunner()

    # Parse command line arguments
    room_name = None
    monitor_duration = 60

    if len(sys.argv) > 1:
        room_name = sys.argv[1]
    if len(sys.argv) > 2:
        monitor_duration = int(sys.argv[2])

    # First, verify that both agents are running
    logger.info("=" * 60)
    logger.info("IMPORTANT: Make sure both agents are running:")
    logger.info("  Terminal 1: uv run python src/support_agent.py dev")
    logger.info("  Terminal 2: uv run python src/customer_agent.py dev")
    logger.info("=" * 60)
    logger.info("Starting in 3 seconds...")
    await asyncio.sleep(3)

    # Run the conversation
    await runner.run_conversation(room_name, monitor_duration)


if __name__ == "__main__":
    asyncio.run(main())