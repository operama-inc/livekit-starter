#!/usr/bin/env python3
"""
LiveKit Audio Egress Recorder
Records agent-to-agent conversations as MP3 files using the Egress API
"""
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env.local")

from livekit import api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioEgressRecorder:
    """Records LiveKit conversations as MP3 using the Egress API"""

    def __init__(self):
        self.livekit_api = api.LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET")
        )
        self.egresses: Dict[str, str] = {}  # room_name -> egress_id

    async def start_audio_recording(self, room_name: str, output_dir: str = "data/conversations/audio") -> Optional[str]:
        """Start audio-only recording of a room using Egress API"""

        # Create output directory
        output_path = Path(output_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path.mkdir(parents=True, exist_ok=True)

        # Configure MP3 output
        filepath = str(output_path / f"{room_name}.mp3")

        try:
            # Create audio-only room composite egress
            request = api.RoomCompositeEgressRequest(
                room_name=room_name,
                audio_only=True,  # Audio-only recording
                file_outputs=[api.EncodedFileOutput(
                    filepath=filepath,
                    file_type=api.EncodedFileType.MP3
                )]
            )

            egress_info = await self.livekit_api.egress.start_room_composite_egress(request)

            self.egresses[room_name] = egress_info.egress_id
            logger.info(f"Started audio recording for room {room_name}")
            logger.info(f"Egress ID: {egress_info.egress_id}")
            logger.info(f"Recording will be saved to: {filepath}")

            return egress_info.egress_id

        except Exception as e:
            logger.error(f"Failed to start egress recording: {e}")
            return None

    async def stop_recording(self, room_name: str) -> bool:
        """Stop recording a room"""

        egress_id = self.egresses.get(room_name)
        if not egress_id:
            logger.warning(f"No active recording for room {room_name}")
            return False

        try:
            await self.livekit_api.egress.stop_egress(
                api.StopEgressRequest(egress_id=egress_id)
            )

            logger.info(f"Stopped recording for room {room_name}")
            del self.egresses[room_name]
            return True

        except Exception as e:
            logger.error(f"Failed to stop egress: {e}")
            return False

    async def get_egress_info(self, egress_id: str) -> Optional[api.EgressInfo]:
        """Get information about an egress"""
        try:
            egresses = await self.livekit_api.egress.list_egress(
                api.ListEgressRequest(egress_id=egress_id)
            )
            if egresses:
                return egresses[0]
            return None
        except Exception as e:
            logger.error(f"Failed to get egress info: {e}")
            return None

    async def wait_for_recording_complete(self, egress_id: str, timeout: int = 300):
        """Wait for recording to complete"""
        start_time = datetime.now()

        while (datetime.now() - start_time).seconds < timeout:
            info = await self.get_egress_info(egress_id)
            if info:
                if info.status == api.EgressStatus.EGRESS_COMPLETE:
                    logger.info(f"Recording complete: {info.file_results}")
                    return True
                elif info.status == api.EgressStatus.EGRESS_FAILED:
                    logger.error(f"Recording failed: {info.error}")
                    return False

            await asyncio.sleep(5)

        logger.warning("Recording did not complete within timeout")
        return False


async def test_audio_recording():
    """Test audio recording with agent conversation"""

    recorder = AudioEgressRecorder()
    livekit_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )

    # Create a new room
    room_name = f"test-audio-{datetime.now().strftime('%H%M%S')}"

    logger.info(f"Creating room: {room_name}")
    room = await livekit_api.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            metadata="cooperative_parent:default:3"  # 3 turns for testing
        )
    )

    # Start recording BEFORE agents join
    egress_id = await recorder.start_audio_recording(room_name)

    if egress_id:
        # Wait a moment for egress to initialize
        await asyncio.sleep(5)

        # Dispatch agents (they should already exist from our unified_agent_v2.py)
        logger.info("Dispatching customer agent...")
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(room=room_name)
        )

        await asyncio.sleep(3)

        logger.info("Dispatching support agent...")
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(room=room_name)
        )

        # Let conversation run
        logger.info("Recording conversation for 60 seconds...")
        await asyncio.sleep(60)

        # Stop recording
        await recorder.stop_recording(room_name)

        # Wait for egress to complete processing
        logger.info("Waiting for recording to finalize...")
        await recorder.wait_for_recording_complete(egress_id)

    # Delete room
    logger.info(f"Deleting room: {room_name}")
    await livekit_api.room.delete_room(api.DeleteRoomRequest(room=room_name))

    return egress_id


if __name__ == "__main__":
    asyncio.run(test_audio_recording())