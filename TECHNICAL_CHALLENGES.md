# Technical Challenges: LiveKit Agent-to-Agent Communication

## Executive Summary

This document details the technical challenges encountered while attempting to implement agent-to-agent voice conversations using the LiveKit Agents SDK for generating synthetic customer support conversations. The primary goal was to generate 100-200 synthetic conversations between AI agents, but fundamental architectural limitations in the LiveKit Agents framework prevented successful implementation.

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Dispatch Routing Challenge](#dispatch-routing-challenge)
3. [Agent Communication Architecture Issue](#agent-communication-architecture-issue)
4. [Egress API Recording Issues](#egress-api-recording-issues)
5. [Alternative Approaches](#alternative-approaches)
6. [Recommendations](#recommendations)

---

## Problem Statement

### Original Goal
Generate 100-200 synthetic customer support conversations using LiveKit infrastructure with:
- Two AI agents (customer and support) conversing via voice
- High-quality audio recordings (MP3)
- Conversation transcripts with timestamps
- Various customer personas and scenarios

### Core Issue
The LiveKit Agents SDK is designed for human-to-agent interactions, not agent-to-agent communication. While we successfully solved the dispatch routing problem, agents cannot actually converse with each other due to architectural limitations.

---

## Dispatch Routing Challenge

### Initial Problem
LiveKit's agent dispatch system only routes to one named worker at a time. When attempting to run separate customer and support agents:

```python
# Original approach - FAILED
# customer_agent.py
cli.run_app(WorkerOptions(
    entrypoint_fnc=customer_entrypoint,
    agent_name="customer-agent"
))

# support_agent.py
cli.run_app(WorkerOptions(
    entrypoint_fnc=support_entrypoint,
    agent_name="support-agent"
))
```

**Result:** Only the first agent would receive dispatch requests.

### Investigation Findings

From testing and logs:
```
INFO: Dispatching customer agent to room: test-room
INFO: Customer agent joined successfully
INFO: Attempting to dispatch support agent...
ERROR: No response from support agent worker
```

The issue: LiveKit dispatches to workers based on availability, and with named agents, only one worker pool is considered.

### Solution: Unified Agent Architecture

Created a unified agent (`unified_agent_v2.py`) that handles all dispatches and assigns roles dynamically:

```python
async def unified_entrypoint(ctx: JobContext):
    """Unified entry point that handles both customer and support roles"""

    room_name = ctx.room.name

    # Get role using coordination file
    role = get_role_for_room(room_name, ctx.job.id)
    logger.info(f"ASSIGNED ROLE: {role}")

    # Load appropriate persona based on role
    if role == "customer":
        persona = persona_service.get_customer_persona(customer_id)
    else:
        persona = persona_service.get_support_persona(support_id)

    # Create agent with assigned role
    agent = UnifiedAgent(role, persona)
```

#### File-based Coordination

To prevent race conditions when assigning roles:

```python
def get_role_for_room(room_name: str, job_id: str) -> str:
    """Determine role for this agent using coordination file"""

    if not acquire_lock():
        logger.error("Failed to acquire lock")
        return "customer"  # Fallback

    try:
        # Load or create coordination data
        if COORDINATION_FILE.exists():
            with open(COORDINATION_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = {}

        # Check if room already has assignments
        if room_name not in data:
            data[room_name] = {"customer": None, "support": None}

        room_data = data[room_name]

        # Assign first available role
        if room_data["customer"] is None:
            room_data["customer"] = job_id
            role = "customer"
        elif room_data["support"] is None:
            room_data["support"] = job_id
            role = "support"
        else:
            # Check if this job already has a role
            if room_data["customer"] == job_id:
                role = "customer"
            elif room_data["support"] == job_id:
                role = "support"
            else:
                logger.error(f"Room {room_name} already has both roles assigned")
                role = "customer"  # Fallback

        # Save updated data
        with open(COORDINATION_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        return role

    finally:
        release_lock()
```

**Result:** Both agents successfully join the same room with correct role assignments.

### Successful Test Output

```
INFO: Creating room: test-unified-agent
INFO: Dispatching first agent...
INFO: [Agent 1] ASSIGNED ROLE: customer
INFO: [Agent 1] Using customer persona: राज शर्मा
INFO: [Agent 1] Connected as customer agent

INFO: Dispatching second agent...
INFO: [Agent 2] ASSIGNED ROLE: support
INFO: [Agent 2] Using support persona: फ़ैज़ान
INFO: [Agent 2] Connected as support agent
```

---

## Agent Communication Architecture Issue

### The Fundamental Problem

While agents successfully join rooms with proper roles, they cannot actually communicate because:

1. **Audio Pipeline Direction:** LiveKit Agents expect audio from human participants
2. **No Agent Audio Publishing:** Agents don't publish audio tracks other agents can subscribe to
3. **STT Input Source:** Speech-to-text expects microphone input, not other agent audio

### Current Architecture

```python
# How LiveKit Agents currently work
session = AgentSession(
    stt=inference.STT(),     # Expects human voice input
    llm=openai.LLM(),        # Processes text
    tts=cartesia.TTS(),      # Generates audio response
    vad=silero.VAD.load()    # Detects human voice activity
)

# Pipeline flow:
# Human Microphone → STT → LLM → TTS → Human Speakers
# NOT: Agent Audio → STT → LLM → TTS → Agent Audio
```

### What Actually Happens

From test logs:
```
INFO: Customer initiating conversation...
# Attempts to speak but no audio is published
await session.say("Hello, I need help with my account.")
# ↑ This doesn't publish audio to the room

INFO: Connected as support agent
# Support agent waiting for input...
# Never receives any audio to process
```

### Missing Components

To enable agent-to-agent communication, we would need:

1. **Audio Track Publishing:**
```python
# Need to publish agent audio as a track
audio_track = await room.local_participant.publish_audio_track(
    agent_audio_source
)
```

2. **Audio Track Subscription:**
```python
# Need to subscribe to other agent's audio
@room.on("track_published")
async def on_track_published(publication, participant):
    if participant.identity != self.identity:
        track = await publication.track.subscribe()
        # Feed track audio to STT pipeline
```

3. **Audio Routing:**
```python
# Need custom audio routing
class AgentToAgentAudioBridge:
    async def route_audio(self, source_agent, target_agent):
        # Capture TTS output from source
        audio_frames = await source_agent.tts.get_audio()

        # Convert to format STT expects
        audio_stream = convert_to_stream(audio_frames)

        # Feed to target agent's STT
        await target_agent.stt.process_audio(audio_stream)
```

### Proof from LiveKit Documentation

From the LiveKit Agents documentation:
> "The Agent class is designed to handle conversations between a human participant and an AI agent. The audio pipeline processes incoming human speech through STT, generates responses via LLM, and outputs synthesized speech through TTS."

The framework lacks built-in support for agent-to-agent audio routing.

---

## Egress API Recording Issues

### Attempted Solution

Tried using LiveKit's Egress API to record agent conversations:

```python
class AudioEgressRecorder:
    async def start_audio_recording(self, room_name: str):
        request = api.RoomCompositeEgressRequest(
            room_name=room_name,
            audio_only=True,
            file_outputs=[api.EncodedFileOutput(
                filepath=filepath,
                file_type=api.EncodedFileType.MP3
            )]
        )

        egress_info = await self.livekit_api.egress.start_room_composite_egress(request)
```

### Configuration Errors

Multiple attempts to fix the API configuration:

1. **Initial Error:**
```
ERROR: request has missing or invalid field: output
```

2. **Attempted Fixes:**
```python
# Attempt 1: Direct file output
file=api.EncodedFileOutput(...)  # FAILED

# Attempt 2: List of outputs
file_outputs=[api.EncodedFileOutput(...)]  # FAILED

# Attempt 3: With explicit file type
file_outputs=[api.EncodedFileOutput(
    filepath="/tmp/recording.mp3",
    file_type=api.EncodedFileType.MP3
)]  # STILL FAILED
```

### Root Cause

The Egress API issue appears to be related to:
- Incorrect protobuf field mapping in the Python SDK
- Possible version mismatch between SDK and server API
- Missing required fields not documented in SDK

### Alternative: Room Events

Attempted to capture transcripts via room events instead:

```python
class ConversationRecorder:
    @room.on("data_received")
    def on_data_received(packet: DataPacket):
        """Capture transcript data packets"""
        data = packet.data.decode('utf-8')
        try:
            msg = json.loads(data)
            if 'text' in msg:
                recorder.add_transcript(
                    participant=packet.participant.identity,
                    text=msg['text']
                )
        except json.JSONDecodeError:
            pass
```

**Result:** Only captured system events (join/leave), no conversation data.

---

## Alternative Approaches

### 1. Hybrid Local Generation (Recommended)

Generate conversations locally without LiveKit room infrastructure:

```python
class LocalConversationGenerator:
    async def generate_conversation(self, customer_persona, support_persona):
        conversation = []

        for turn in range(max_turns):
            # Customer speaks
            customer_text = await self.generate_customer_response(context)
            customer_audio = await self.tts.synthesize(customer_text, customer_voice)

            # Support responds
            support_text = await self.generate_support_response(customer_text)
            support_audio = await self.tts.synthesize(support_text, support_voice)

            # Save both
            conversation.append({
                'speaker': 'customer',
                'text': customer_text,
                'audio': customer_audio
            })
            conversation.append({
                'speaker': 'support',
                'text': support_text,
                'audio': support_audio
            })

        return self.merge_audio_files(conversation)
```

### 2. Custom WebRTC Implementation

Build custom WebRTC peer connections for agent-to-agent:

```python
class AgentPeerConnection:
    async def establish_connection(self, other_agent):
        # Create peer connection
        pc = RTCPeerConnection()

        # Add audio track
        audio_track = AudioStreamTrack()
        pc.addTrack(audio_track)

        # Handle incoming audio
        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                asyncio.create_task(
                    self.process_incoming_audio(track)
                )

        # Exchange SDP
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        # Send offer to other agent...
```

### 3. Message-Based Conversation

Use LiveKit data channels for text-only conversation:

```python
class MessageBasedAgent:
    async def converse_via_messages(self):
        @room.on("data_received")
        async def on_message(data):
            message = json.loads(data.data)

            if message['role'] != self.role:
                # Generate response
                response = await self.llm.generate(message['text'])

                # Send response
                await room.local_participant.publish_data(
                    json.dumps({
                        'role': self.role,
                        'text': response
                    })
                )

                # Generate audio separately
                audio = await self.tts.synthesize(response)
                self.save_audio(audio)
```

### 4. Sequential Recording

Record each agent separately then combine:

```python
async def record_sequentially():
    # Record customer parts
    customer_recordings = []
    for turn in customer_turns:
        audio = await record_customer_turn(turn)
        customer_recordings.append(audio)

    # Record support parts
    support_recordings = []
    for turn in support_turns:
        audio = await record_support_turn(turn)
        support_recordings.append(audio)

    # Interleave and merge
    final_audio = merge_alternating(
        customer_recordings,
        support_recordings
    )
```

---

## Recommendations

### Immediate Solution

**Use the original OpenAI-based approach** that was already working:
- Direct API calls for conversation generation
- Local TTS synthesis
- Simple, reliable, and scalable

### Long-term Solutions

1. **Work with LiveKit Team**
   - Request agent-to-agent communication features
   - Contribute to SDK development
   - Document use case for product roadmap

2. **Build Custom Solution**
   - Implement WebRTC-based agent communication
   - Create audio routing layer
   - Maintain separately from LiveKit SDK

3. **Hybrid Approach**
   - Use LiveKit for human-agent interactions
   - Use custom solution for agent-agent training data

### Technical Debt Items

- Document the dispatch routing solution for future reference
- Clean up failed egress implementation attempts
- Consider contributing coordination logic back to LiveKit

---

## Conclusion

While we successfully solved the dispatch routing challenge with an innovative unified agent architecture, the fundamental limitation of LiveKit Agents being designed for human-agent (not agent-agent) interaction prevents achieving the original goal through this approach.

The recommended path forward is to return to the working OpenAI-based solution for generating synthetic conversations while potentially working with the LiveKit team to add agent-to-agent communication capabilities to their roadmap.

### Key Learnings

1. **Architecture Matters:** Understanding framework design assumptions before implementation
2. **Dispatch Routing:** LiveKit's dispatch system requires careful coordination for multi-agent scenarios
3. **API Documentation:** Egress API documentation gaps caused significant implementation delays
4. **Fallback Planning:** Always maintain working alternatives when exploring new approaches

---

## Appendix: Error Logs and Debug Output

### Dispatch Routing Debug Logs
```
2025-11-18 22:01:11 - Received job request for room: test-unified-agent
2025-11-18 22:01:11 - First agent in room, assigning customer role
2025-11-18 22:01:14 - Second dispatch received for same room
2025-11-18 22:01:14 - Customer already exists, assigning support role
```

### Egress API Error Response
```json
{
  "error": {
    "code": 3,
    "message": "request has missing or invalid field: output",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.BadRequest",
        "field_violations": [
          {
            "field": "output",
            "description": "missing required field"
          }
        ]
      }
    ]
  }
}
```

### Room Event Capture (Empty Conversation)
```
[1.0s] SYSTEM: agent-AJ_62A7y53Qij2B joined the room
[6.0s] SYSTEM: agent-AJ_F5AyxytBeLSt joined the room
# No actual conversation data captured
```