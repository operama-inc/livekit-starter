#!/usr/bin/env python3
"""
LiveKit Conversation Recorder
Records agent-to-agent conversations and exports audio/transcripts
"""
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env.local")

from livekit import api, rtc
from livekit.api import EgressInfo, RoomCompositeEgressRequest, EncodedFileOutput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversationRecorder:
    """Records LiveKit agent conversations and exports them"""

    def __init__(self):
        self.livekit_api = api.LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET")
        )
        self.egresses: Dict[str, str] = {}  # room_name -> egress_id
        self.transcripts: Dict[str, List[Dict]] = {}  # room_name -> transcript entries

    async def start_recording(self, room_name: str, output_dir: str = "data/conversations") -> str:
        """Start recording a room using LiveKit Egress API"""

        # Create output directory
        output_path = Path(output_dir) / "recordings" / datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path.mkdir(parents=True, exist_ok=True)

        # Configure egress to record room audio as MP3
        filepath = f"{output_path}/{room_name}.mp3"

        try:
            # Create room composite egress (records entire room)
            request = RoomCompositeEgressRequest(
                room_name=room_name,
                file=EncodedFileOutput(
                    filepath=filepath,
                    file_type="MP3"  # Export as MP3
                )
            )

            egress_info = await self.livekit_api.egress.start_room_composite_egress(request)

            self.egresses[room_name] = egress_info.egress_id
            logger.info(f"Started recording room {room_name} with egress {egress_info.egress_id}")
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

    async def monitor_room_transcripts(self, room_name: str, duration: int = 300):
        """Monitor a room and collect transcripts"""

        # This would require connecting as a participant to receive transcripts
        # For now, we'll use a placeholder approach
        # In production, you'd connect to the room and listen for transcript events

        logger.info(f"Monitoring room {room_name} for transcripts (duration: {duration}s)")

        # Initialize transcript list for this room
        self.transcripts[room_name] = []

        # In a real implementation, you would:
        # 1. Connect to the room as a hidden participant
        # 2. Subscribe to transcript events
        # 3. Store them in self.transcripts[room_name]

        await asyncio.sleep(duration)

    async def export_transcript(self, room_name: str, output_dir: str = "data/conversations"):
        """Export collected transcripts to JSON"""

        transcript = self.transcripts.get(room_name, [])
        if not transcript:
            logger.warning(f"No transcript data for room {room_name}")
            return None

        # Create output path
        output_path = Path(output_dir) / "transcripts" / datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path.mkdir(parents=True, exist_ok=True)

        filepath = output_path / f"{room_name}_transcript.json"

        # Save transcript
        with open(filepath, 'w') as f:
            json.dump({
                "room_name": room_name,
                "timestamp": datetime.now().isoformat(),
                "messages": transcript
            }, f, indent=2)

        logger.info(f"Exported transcript to: {filepath}")
        return str(filepath)

    async def record_conversation(self, room_name: str, duration: int = 60):
        """Record a complete conversation with audio and transcript"""

        logger.info(f"Starting conversation recording for room: {room_name}")

        # Start egress recording
        egress_id = await self.start_recording(room_name)

        # Monitor for transcripts (in parallel)
        transcript_task = asyncio.create_task(
            self.monitor_room_transcripts(room_name, duration)
        )

        # Wait for conversation to complete
        logger.info(f"Recording for {duration} seconds...")
        await asyncio.sleep(duration)

        # Stop recording
        await self.stop_recording(room_name)

        # Wait for transcript monitoring to complete
        await transcript_task

        # Export transcript
        transcript_path = await self.export_transcript(room_name)

        logger.info(f"Conversation recording complete!")
        logger.info(f"Audio will be available once egress completes processing")
        logger.info(f"Transcript saved to: {transcript_path}")

        return {
            "room_name": room_name,
            "egress_id": egress_id,
            "transcript_path": transcript_path
        }


async def record_test_conversation():
    """Record a test conversation between agents"""

    recorder = ConversationRecorder()

    # Create a new room for testing
    livekit_api = api.LiveKitAPI()
    room_name = f"test-recording-{datetime.now().strftime('%H%M%S')}"

    logger.info(f"Creating room: {room_name}")
    room = await livekit_api.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            metadata="cooperative_parent:default:3"  # 3 turns max for testing
        )
    )

    # Start recording BEFORE dispatching agents
    egress_id = await recorder.start_recording(room_name)

    if egress_id:
        # Dispatch agents
        logger.info("Dispatching customer agent...")
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(room=room_name)
        )

        await asyncio.sleep(3)

        logger.info("Dispatching support agent...")
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(room=room_name)
        )

        # Let conversation run for 60 seconds
        logger.info("Recording conversation for 60 seconds...")
        await asyncio.sleep(60)

        # Stop recording
        await recorder.stop_recording(room_name)

        # Check egress status
        egress_list = await livekit_api.egress.list_egress(
            api.ListEgressRequest(room_name=room_name)
        )

        for egress in egress_list:
            logger.info(f"Egress {egress.egress_id} status: {egress.status}")
            if egress.file:
                logger.info(f"Recording location: {egress.file.location}")

    # Delete room
    logger.info(f"Deleting room: {room_name}")
    await livekit_api.room.delete_room(api.DeleteRoomRequest(name=room_name))

    return egress_id


if __name__ == "__main__":
    asyncio.run(record_test_conversation())