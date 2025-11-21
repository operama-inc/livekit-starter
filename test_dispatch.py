#!/usr/bin/env python
"""Test script to verify agent dispatch configuration."""

import asyncio
import logging
import os
import sys
import time
from dotenv import load_dotenv
import aiohttp
from livekit import api
from livekit.api import room_service, agent_dispatch_service

# Load environment
load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_dispatch():
    """Test agent dispatch to verify both agents can be dispatched."""
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    room_name = f"test-dispatch-{int(time.time())}"

    logger.info(f"Testing dispatch to room: {room_name}")

    async with aiohttp.ClientSession() as session:
        # Create room
        room_api = room_service.RoomService(session, url, api_key, api_secret)
        await room_api.create_room(api.CreateRoomRequest(name=room_name))
        logger.info(f"Created room: {room_name}")

        # Create dispatch service
        dispatch_api = agent_dispatch_service.AgentDispatchService(
            session, url, api_key, api_secret
        )

        # Test 1: Dispatch without agent_name (should go to default worker)
        try:
            req1 = api.CreateAgentDispatchRequest(room=room_name)
            dispatch1 = await dispatch_api.create_dispatch(req1)
            logger.info(f"✓ Dispatch without agent_name succeeded: {dispatch1}")
        except Exception as e:
            logger.error(f"✗ Dispatch without agent_name failed: {e}")

        await asyncio.sleep(2)

        # Test 2: Dispatch with agent_name="support-agent"
        try:
            req2 = api.CreateAgentDispatchRequest(
                room=room_name,
                agent_name="support-agent"
            )
            dispatch2 = await dispatch_api.create_dispatch(req2)
            logger.info(f"✓ Dispatch to 'support-agent' succeeded: {dispatch2}")
        except Exception as e:
            logger.error(f"✗ Dispatch to 'support-agent' failed: {e}")

        await asyncio.sleep(2)

        # Test 3: Dispatch with agent_name="customer-agent"
        try:
            req3 = api.CreateAgentDispatchRequest(
                room=room_name,
                agent_name="customer-agent"
            )
            dispatch3 = await dispatch_api.create_dispatch(req3)
            logger.info(f"✓ Dispatch to 'customer-agent' succeeded: {dispatch3}")
        except Exception as e:
            logger.error(f"✗ Dispatch to 'customer-agent' failed: {e}")

        await asyncio.sleep(2)

        # Check participants
        resp = await room_api.list_participants(api.ListParticipantsRequest(room=room_name))
        participants = resp.participants if hasattr(resp, 'participants') else []
        logger.info(f"Room has {len(participants)} participants:")
        for p in participants:
            logger.info(f"  - {p.identity} (kind: {p.kind})")

        # Clean up
        await room_api.delete_room(api.DeleteRoomRequest(room=room_name))
        logger.info(f"Deleted room: {room_name}")

if __name__ == "__main__":
    asyncio.run(test_dispatch())