#!/usr/bin/env python3
"""
Script to delete a specific LiveKit room
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from livekit.api import LiveKitAPI, DeleteRoomRequest

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env.local")

async def delete_room(room_id: str):
    """Delete a LiveKit room by its ID"""
    # Initialize LiveKit API with environment variables
    api = LiveKitAPI()

    try:
        # Delete the room
        await api.room.delete_room(DeleteRoomRequest(room=room_id))
        print(f"Successfully deleted room: {room_id}")
    except Exception as e:
        print(f"Error deleting room {room_id}: {e}")
        raise

async def main():
    room_id = "RM_7CCAzbpJiUb5"
    print(f"Attempting to delete room: {room_id}")
    await delete_room(room_id)

if __name__ == "__main__":
    asyncio.run(main())