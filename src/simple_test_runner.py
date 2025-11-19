#!/usr/bin/env python3
"""
Simple test runner to test agent-to-agent conversation
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from livekit import api
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_conversation():
    """Test a simple agent-to-agent conversation"""

    # Create API client
    lkapi = api.LiveKitAPI()

    # Create room
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    room_name = f"test_{timestamp}"

    logger.info(f"Creating room: {room_name}")
    room = await lkapi.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            empty_timeout=60,  # 1 minute
            max_participants=10
        )
    )
    logger.info(f"Room created: {room.name}")

    # Auto-dispatch will handle agents joining - they both listen for new rooms
    # The first agent to join becomes the customer, second becomes support

    # Wait for conversation
    logger.info("Waiting for agents to join and converse...")
    await asyncio.sleep(30)  # Give them 30 seconds to talk

    # Check participants
    participants = await lkapi.room.list_participants(
        api.ListParticipantsRequest(room=room_name)
    )

    logger.info(f"Participants in room: {len(participants.participants)}")
    for p in participants.participants:
        logger.info(f"  - {p.identity} (state: {p.state})")

    # Clean up
    logger.info("Deleting room...")
    await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))

    await lkapi.aclose()
    logger.info("Test complete!")


if __name__ == "__main__":
    asyncio.run(test_conversation())