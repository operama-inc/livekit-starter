#!/usr/bin/env python3
"""
LiveKit Conversation Runner - Orchestrates agent-to-agent conversations with egress recording
"""
import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from livekit import api
from livekit.api import (
    LiveKitAPI,
    CreateRoomRequest,
    CreateAgentDispatchRequest,
    ListRoomsRequest,
    ListParticipantsRequest,
    RoomCompositeEgressRequest,
    TrackEgressRequest,
    EncodedFileOutput,
    EncodedFileType,
    StopEgressRequest,
    ListEgressRequest,
    EgressInfo,
    DeleteRoomRequest,
    TrackType,
)
from dotenv import load_dotenv

# Load environment variables from .env.local
load_dotenv(Path(__file__).parent.parent / ".env.local")

from voice_conversation_generator.models import CustomerPersona, SupportPersona
from voice_conversation_generator.services import PersonaService
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LiveKitConversationRunner:
    """Orchestrates LiveKit agent-to-agent conversations with recording"""

    def __init__(
        self,
        livekit_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        output_dir: str = "data/livekit_conversations"
    ):
        """Initialize the conversation runner

        Args:
            livekit_url: LiveKit server URL
            api_key: LiveKit API key
            api_secret: LiveKit API secret
            output_dir: Directory for output files
        """
        self.livekit_url = livekit_url or os.getenv("LIVEKIT_URL")
        self.api_key = api_key or os.getenv("LIVEKIT_API_KEY")
        self.api_secret = api_secret or os.getenv("LIVEKIT_API_SECRET")

        # LiveKitAPI will automatically use LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET env vars
        # If they're not set, we can pass them explicitly
        if livekit_url or api_key or api_secret:
            # Use explicit credentials if provided
            self.api = LiveKitAPI(
                url=self.livekit_url,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
        else:
            # Use env vars (will raise if not set)
            self.api = LiveKitAPI()

        # Setup output directory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def run_conversation(
        self,
        customer_persona_id: str,
        support_persona_id: str = "default",
        max_turns: int = 5,
        record_audio: bool = False,  # Disabled for now due to API issues
        record_per_track: bool = False  # Disabled for now
    ) -> Dict[str, Any]:
        """Run a single agent-to-agent conversation

        Args:
            customer_persona_id: ID of the customer persona
            support_persona_id: ID of the support persona
            max_turns: Maximum conversation turns
            record_audio: Whether to record composite audio
            record_per_track: Whether to record per-track audio

        Returns:
            Dictionary with conversation metadata and recording paths
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        room_name = f"conv_{timestamp}_{customer_persona_id}"
        metadata = f"{customer_persona_id}:{support_persona_id}:{max_turns}"

        logger.info(f"Starting conversation: {room_name}")
        logger.info(f"Metadata: {metadata}")

        try:
            # 1. Create room
            await self.create_room(room_name, metadata)

            # 2. Start egress recording if requested
            composite_egress_id = None
            track_egress_ids = []

            if record_audio:
                composite_egress_id = await self.start_composite_egress(
                    room_name,
                    f"{timestamp}_{customer_persona_id}_composite"
                )

            if record_per_track:
                # We'll start track egress after agents join
                pass

            # 3. Dispatch agents
            await self.dispatch_agents(room_name)

            # 4. Wait briefly for agents to connect
            await asyncio.sleep(3)

            # Start per-track recording after agents join
            if record_per_track:
                track_egress_ids = await self.start_track_egress(room_name, timestamp)

            # 5. Monitor conversation
            await self.monitor_conversation(room_name, max_turns)

            # 6. Stop egress and retrieve recordings
            recordings = {}
            if composite_egress_id:
                composite_info = await self.stop_egress(composite_egress_id)
                recordings['composite'] = composite_info

            for egress_id in track_egress_ids:
                track_info = await self.stop_egress(egress_id)
                recordings[f'track_{egress_id}'] = track_info

            # 7. Clean up room
            await self.delete_room(room_name)

            logger.info(f"Conversation completed: {room_name}")
            return {
                'room_name': room_name,
                'customer_persona': customer_persona_id,
                'support_persona': support_persona_id,
                'max_turns': max_turns,
                'recordings': recordings,
                'timestamp': timestamp
            }

        except Exception as e:
            logger.error(f"Error in conversation {room_name}: {e}")
            # Clean up on error
            try:
                await self.delete_room(room_name)
            except:
                pass
            raise

    async def create_room(self, room_name: str, metadata: str) -> None:
        """Create a LiveKit room"""
        request = CreateRoomRequest(
            name=room_name,
            metadata=metadata,
            empty_timeout=300,  # 5 minutes
            max_participants=10
        )
        room = await self.api.room.create_room(request)
        logger.info(f"Created room: {room.name}")

    async def delete_room(self, room_name: str) -> None:
        """Delete a LiveKit room"""
        try:
            await self.api.room.delete_room(DeleteRoomRequest(room=room_name))
            logger.info(f"Deleted room: {room_name}")
        except Exception as e:
            logger.warning(f"Could not delete room {room_name}: {e}")

    async def start_composite_egress(
        self,
        room_name: str,
        file_prefix: str
    ) -> str:
        """Start composite egress recording

        Args:
            room_name: Room to record
            file_prefix: Prefix for output file

        Returns:
            Egress ID
        """
        output_file = self.output_dir / f"{file_prefix}.ogg"

        # Use the deprecated 'file' field for now as it still works
        request = RoomCompositeEgressRequest(
            room_name=room_name,
            audio_only=True,
            layout="speaker",
            file=EncodedFileOutput(
                file_type=EncodedFileType.OGG,  # OGG/Opus for audio-only
                filepath=str(output_file)
            )
        )

        egress_info = await self.api.egress.start_room_composite_egress(request)
        logger.info(f"Started composite egress: {egress_info.egress_id}")
        return egress_info.egress_id

    async def start_track_egress(
        self,
        room_name: str,
        timestamp: str
    ) -> List[str]:
        """Start per-track egress recording

        Args:
            room_name: Room to record
            timestamp: Timestamp for file naming

        Returns:
            List of egress IDs
        """
        egress_ids = []

        # Get participants in room
        participants = await self.api.room.list_participants(
            ListParticipantsRequest(room=room_name)
        )

        for participant in participants.participants:
            # Skip if not an agent
            if participant.identity not in ["customer-agent", "support-agent"]:
                continue

            # Find audio track
            for track in participant.tracks:
                if track.type == TrackType.AUDIO and track.track_id:
                    output_file = self.output_dir / f"{timestamp}_{participant.identity}.ogg"

                    request = TrackEgressRequest(
                        room_name=room_name,
                        track_id=track.track_id,
                        file=EncodedFileOutput(
                            file_type=EncodedFileType.OGG,
                            filepath=str(output_file)
                        )
                    )

                    egress_info = await self.api.egress.start_track_egress(request)
                    egress_ids.append(egress_info.egress_id)
                    logger.info(f"Started track egress for {participant.identity}: {egress_info.egress_id}")

        return egress_ids

    async def stop_egress(self, egress_id: str) -> Dict[str, Any]:
        """Stop an egress recording

        Args:
            egress_id: Egress to stop

        Returns:
            Egress information
        """
        request = StopEgressRequest(egress_id=egress_id)
        egress_info = await self.api.egress.stop_egress(request)

        logger.info(f"Stopped egress: {egress_id}")

        # Wait briefly for file to be written
        await asyncio.sleep(2)

        return {
            'egress_id': egress_id,
            'status': egress_info.status.name,
            'file_results': egress_info.file_results if hasattr(egress_info, 'file_results') else None
        }

    async def dispatch_agents(self, room_name: str) -> None:
        """Explicitly dispatch both agents to the room

        Args:
            room_name: Room for agents to join
        """
        # Use explicit dispatch for both agents
        logger.info(f"Dispatching agents to room: {room_name}")

        try:
            # Dispatch support agent
            await self.api.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name="support-agent",
                    metadata='{"role":"support"}'
                )
            )
            logger.info("Dispatched support-agent")

            # Dispatch customer agent
            await self.api.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name="customer-agent",
                    metadata='{"role":"customer"}'
                )
            )
            logger.info("Dispatched customer-agent")

        except Exception as e:
            logger.error(f"Error dispatching agents: {e}")
            raise

    async def monitor_conversation(
        self,
        room_name: str,
        max_turns: int,
        timeout: int = 300
    ) -> None:
        """Monitor conversation progress

        Args:
            room_name: Room to monitor
            max_turns: Expected max turns
            timeout: Maximum time to wait (seconds)
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Check room participants
                participants = await self.api.room.list_participants(
                    ListParticipantsRequest(room=room_name)
                )

                agent_count = sum(1 for p in participants.participants
                                  if "agent" in p.identity.lower())

                if agent_count < 2:
                    logger.info(f"Waiting for agents... ({agent_count}/2 connected)")
                else:
                    logger.info(f"Both agents connected, conversation in progress...")

                    # Estimate conversation duration (15 seconds per turn)
                    estimated_duration = max_turns * 15
                    await asyncio.sleep(min(estimated_duration, 60))

                    # Check if agents are still connected
                    participants = await self.api.room.list_participants(
                        ListParticipantsRequest(room=room_name)
                    )

                    if len(participants.participants) == 0:
                        logger.info("Conversation ended (all participants left)")
                        break

            except Exception as e:
                logger.warning(f"Error monitoring room: {e}")

            await asyncio.sleep(5)

        logger.info(f"Monitoring completed for {room_name}")


async def run_single_conversation():
    """Run a single test conversation"""
    runner = LiveKitConversationRunner()

    # Load personas
    persona_service = PersonaService()
    persona_service.load_default_personas()

    # Run conversation
    result = await runner.run_conversation(
        customer_persona_id="cooperative_parent",
        support_persona_id="default",
        max_turns=3,
        record_audio=False,  # Disabled for testing
        record_per_track=False
    )

    print("\n" + "=" * 50)
    print("CONVERSATION COMPLETED")
    print("=" * 50)
    print(f"Room: {result['room_name']}")
    print(f"Customer: {result['customer_persona']}")
    print(f"Support: {result['support_persona']}")
    print(f"Recordings: {len(result.get('recordings', {}))}")
    for name, info in result.get('recordings', {}).items():
        print(f"  - {name}: {info}")
    print("=" * 50)

    return result


if __name__ == "__main__":
    # Test with single conversation
    asyncio.run(run_single_conversation())