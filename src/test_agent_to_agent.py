#!/usr/bin/env python
"""
Test runner for agent-to-agent communication
Creates a room and dispatches two agents
"""
import asyncio
import logging
import os
from datetime import datetime

from livekit import api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_agent_to_agent():
    """Test agent-to-agent voice communication"""

    # Initialize LiveKit API
    livekit_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )

    # Create unique room name
    room_name = f"test-agent-to-agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    try:
        # 1. Create room
        logger.info(f"📦 Creating room: {room_name}")
        await livekit_api.room.create_room(api.CreateRoomRequest(name=room_name))
        logger.info(f"✅ Room created successfully")

        # 2. Dispatch first agent (will become customer)
        logger.info(f"🚀 Dispatching first agent (customer)...")
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=room_name,
                agent_name="",  # Empty means any agent
            )
        )
        logger.info(f"✅ First agent dispatched")

        # Wait a moment
        await asyncio.sleep(2)

        # 3. Dispatch second agent (will become support)
        logger.info(f"🚀 Dispatching second agent (support)...")
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=room_name,
                agent_name="",
            )
        )
        logger.info(f"✅ Second agent dispatched")

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Test setup complete!")
        logger.info(f"📊 Room: {room_name}")
        logger.info(f"🎭 Two agents should now be talking to each other")
        logger.info(f"{'='*60}\n")

        # 4. Monitor room for a while
        logger.info(f"👀 Monitoring conversation for 60 seconds...")
        for i in range(12):
            await asyncio.sleep(5)

            # Check room participants
            response = await livekit_api.room.list_participants(
                api.ListParticipantsRequest(room=room_name)
            )

            agent_count = sum(1 for p in response.participants if p.kind == api.ParticipantInfo.Kind.AGENT)
            logger.info(f"   [{(i+1)*5}s] Agents in room: {agent_count}")

        logger.info(f"\n🏁 Test complete! Check agent logs for conversation details.")

        # 5. Cleanup
        logger.info(f"🧹 Cleaning up room...")
        await livekit_api.room.delete_room(api.DeleteRoomRequest(room=room_name))
        logger.info(f"✅ Room deleted")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        # Try to cleanup
        try:
            await livekit_api.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except:
            pass
        raise

    await livekit_api.aclose()


if __name__ == "__main__":
    asyncio.run(test_agent_to_agent())
