#!/usr/bin/env python3
"""
Test script to dispatch both customer and support agents to the same room
using the unified agent approach
"""
import os
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from livekit import api

# Load environment variables from .env.local
load_dotenv(Path(__file__).parent.parent / ".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Test unified agent dispatch"""

    # Initialize LiveKit API client
    livekit_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )

    # Create room with metadata specifying personas
    room_name = "test-unified-agent"
    room_metadata = "cooperative_parent:default:3"  # customer:support:max_turns

    logger.info(f"Creating room: {room_name}")
    room = await livekit_api.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            metadata=room_metadata
        )
    )
    logger.info(f"Room created: {room.name}")

    # Dispatch first agent (should become customer)
    logger.info("Dispatching first agent (will become customer)...")
    dispatch1 = await livekit_api.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            room=room_name,
            metadata='{"role":"customer"}'  # Hint, though agent will detect based on participant count
        )
    )
    logger.info(f"First dispatch created: {dispatch1.agent_name if hasattr(dispatch1, 'agent_name') else 'dispatched'}")

    # Wait a bit for first agent to join
    await asyncio.sleep(3)

    # Dispatch second agent (should become support)
    logger.info("Dispatching second agent (will become support)...")
    dispatch2 = await livekit_api.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            room=room_name,
            metadata='{"role":"support"}'  # Hint, though agent will detect based on participant count
        )
    )
    logger.info(f"Second dispatch created: {dispatch2.agent_name if hasattr(dispatch2, 'agent_name') else 'dispatched'}")

    # Wait for conversation to complete
    logger.info("Agents dispatched. Waiting for conversation...")
    await asyncio.sleep(30)

    # List participants to see if both joined
    participants = await livekit_api.room.list_participants(
        api.ListParticipantsRequest(room=room_name)
    )
    logger.info(f"Participants in room: {len(participants)}")
    for p in participants:
        logger.info(f"  - {p.identity} (state: {p.state})")

    # Delete room when done
    logger.info(f"Deleting room: {room_name}")
    await livekit_api.room.delete_room(api.DeleteRoomRequest(name=room_name))


if __name__ == "__main__":
    asyncio.run(main())