#!/usr/bin/env python3
"""
Conversation Runner V2 - Captures conversations via room events
Uses the unified agent for agent-to-agent communication
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
from livekit.rtc import Room, RemoteTrack, Track, TrackPublication, DataPacket
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from voice_conversation_generator.services import PersonaService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversationRecorder:
    """Records conversations from room events"""

    def __init__(self, room_name: str, output_dir: str = "data/conversations"):
        self.room_name = room_name
        self.output_dir = Path(output_dir)
        self.transcripts: List[Dict] = []
        self.start_time = datetime.now()

    def add_transcript(self, participant: str, text: str, timestamp: float = None):
        """Add a transcript entry"""
        if timestamp is None:
            timestamp = (datetime.now() - self.start_time).total_seconds()

        self.transcripts.append({
            "participant": participant,
            "text": text,
            "timestamp": timestamp
        })
        logger.info(f"[{participant}]: {text}")

    def save(self):
        """Save transcripts to file"""
        timestamp_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / "transcripts" / timestamp_str
        output_path.mkdir(parents=True, exist_ok=True)

        # Save as JSON
        json_file = output_path / f"{self.room_name}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                "room": self.room_name,
                "start_time": self.start_time.isoformat(),
                "duration": (datetime.now() - self.start_time).total_seconds(),
                "transcripts": self.transcripts
            }, f, indent=2, ensure_ascii=False)

        # Save as readable text
        text_file = output_path / f"{self.room_name}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(f"Conversation: {self.room_name}\n")
            f.write(f"Date: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*50 + "\n\n")

            for entry in self.transcripts:
                f.write(f"[{entry['timestamp']:.1f}s] {entry['participant']}: {entry['text']}\n")

        logger.info(f"Saved transcripts to {output_path}")
        return json_file, text_file


async def monitor_room_events(room_name: str, max_duration: int = 120):
    """Monitor a room and capture all events and transcripts"""

    recorder = ConversationRecorder(room_name)
    room = Room()

    # Set up event handlers
    @room.on("data_received")
    def on_data_received(packet: DataPacket):
        """Handle data packets (including transcripts)"""
        try:
            # Parse the data packet
            data = packet.data.decode('utf-8') if isinstance(packet.data, bytes) else packet.data

            # Try to parse as JSON (transcription format)
            try:
                msg = json.loads(data)
                if 'text' in msg:
                    # This is a transcript
                    participant = packet.participant.identity if packet.participant else "Unknown"
                    recorder.add_transcript(participant, msg['text'])
            except json.JSONDecodeError:
                # Plain text message
                participant = packet.participant.identity if packet.participant else "Unknown"
                recorder.add_transcript(participant, data)

        except Exception as e:
            logger.error(f"Error handling data packet: {e}")

    @room.on("participant_connected")
    def on_participant_connected(participant):
        logger.info(f"Participant connected: {participant.identity}")
        recorder.add_transcript("SYSTEM", f"{participant.identity} joined the room")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        logger.info(f"Participant disconnected: {participant.identity}")
        recorder.add_transcript("SYSTEM", f"{participant.identity} left the room")

    @room.on("track_subscribed")
    def on_track_subscribed(track: Track, publication: TrackPublication, participant):
        """Handle track subscription (audio tracks)"""
        if track.kind == rtc.TrackKind.AUDIO:
            logger.info(f"Subscribed to audio from {participant.identity}")

    # Connect to room
    try:
        url = os.getenv("LIVEKIT_URL")
        token = await create_room_token(room_name, "recorder")

        await room.connect(url, token)
        logger.info(f"Connected to room {room_name} as recorder")

        # Monitor for specified duration
        await asyncio.sleep(max_duration)

    except Exception as e:
        logger.error(f"Error monitoring room: {e}")

    finally:
        # Save recordings
        json_file, text_file = recorder.save()

        # Disconnect
        await room.disconnect()
        logger.info(f"Disconnected from room {room_name}")

        return json_file, text_file


async def create_room_token(room_name: str, identity: str) -> str:
    """Create a token for joining a room"""
    from livekit import api

    token_api = api.AccessToken(
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )
    token_api.with_identity(identity)
    token_api.with_name(identity)
    token_api.with_grants(api.VideoGrants(
        room_join=True,
        room=room_name,
        can_subscribe=True,
        can_publish=False  # Recorder only listens
    ))

    return token_api.to_jwt()


async def run_conversation(customer_persona_id: str, support_persona_id: str = "default",
                          max_turns: int = 5, monitor: bool = True):
    """Run a single conversation between agents and optionally monitor it"""

    livekit_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )

    # Create room with metadata
    room_name = f"conv-{datetime.now().strftime('%H%M%S')}"
    metadata = f"{customer_persona_id}:{support_persona_id}:{max_turns}"

    logger.info(f"Creating room: {room_name}")
    room = await livekit_api.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            metadata=metadata
        )
    )

    # Start monitoring if requested
    monitor_task = None
    if monitor:
        monitor_task = asyncio.create_task(
            monitor_room_events(room_name, max_duration=max_turns * 20)
        )
        await asyncio.sleep(2)  # Let monitor connect first

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

    # Wait for conversation to complete
    if monitor_task:
        json_file, text_file = await monitor_task
        logger.info(f"Conversation saved to: {text_file}")
    else:
        # Just wait for conversation duration
        await asyncio.sleep(max_turns * 15)

    # Delete room
    logger.info(f"Deleting room: {room_name}")
    await livekit_api.room.delete_room(api.DeleteRoomRequest(room=room_name))

    return room_name


async def run_multiple_conversations(count: int = 5):
    """Run multiple conversations with different personas"""

    persona_service = PersonaService(tts_provider="cartesia")
    persona_service.load_default_personas()

    # Get available personas
    customer_personas = ["cooperative_parent", "angry_insufficient_funds",
                        "confused_elderly", "technical_bug_report", "friendly_billing"]
    support_personas = ["default", "technical_expert", "billing_specialist"]

    results = []

    for i in range(count):
        # Rotate through personas
        customer = customer_personas[i % len(customer_personas)]
        support = support_personas[i % len(support_personas)]
        turns = 3 + (i % 3)  # Vary turns between 3-5

        logger.info(f"\n{'='*50}")
        logger.info(f"Starting conversation {i+1}/{count}")
        logger.info(f"Customer: {customer}, Support: {support}, Turns: {turns}")
        logger.info(f"{'='*50}")

        try:
            room_name = await run_conversation(customer, support, turns, monitor=True)
            results.append({
                "room": room_name,
                "customer": customer,
                "support": support,
                "turns": turns,
                "status": "completed"
            })

            # Wait between conversations
            if i < count - 1:
                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Error in conversation {i+1}: {e}")
            results.append({
                "customer": customer,
                "support": support,
                "turns": turns,
                "status": "failed",
                "error": str(e)
            })

    # Save summary
    summary_file = Path("data/conversations/summary.json")
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": count,
            "completed": sum(1 for r in results if r["status"] == "completed"),
            "conversations": results
        }, f, indent=2)

    logger.info(f"\n{'='*50}")
    logger.info(f"Completed {count} conversations")
    logger.info(f"Summary saved to: {summary_file}")

    return results


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Run agent-to-agent conversations")
    parser.add_argument("--customer", default="cooperative_parent",
                       help="Customer persona ID")
    parser.add_argument("--support", default="default",
                       help="Support persona ID")
    parser.add_argument("--turns", type=int, default=5,
                       help="Max conversation turns")
    parser.add_argument("--count", type=int, default=1,
                       help="Number of conversations to run")
    parser.add_argument("--no-monitor", action="store_true",
                       help="Skip monitoring/recording")

    args = parser.parse_args()

    if args.count > 1:
        # Run multiple conversations
        await run_multiple_conversations(args.count)
    else:
        # Run single conversation
        await run_conversation(
            args.customer,
            args.support,
            args.turns,
            monitor=not args.no_monitor
        )


if __name__ == "__main__":
    asyncio.run(main())