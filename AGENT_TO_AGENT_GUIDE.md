# LiveKit Agent-to-Agent Communication: Comprehensive Implementation Guide

**Date**: 2025-11-19
**LiveKit Agents SDK Version**: v1.2.18
**Author**: Implementation Team

## 🎯 Objective

**Goal**: Implement agent-to-agent voice communication in LiveKit where both a customer AI agent and a support AI agent can have a conversation with each other in a LiveKit room, with the ability to capture both audio and transcripts of their interaction.

**Key Requirements**:
- Two AI agents (customer and support) conversing via voice
- Real-time audio communication between agents
- High-quality conversation capture
- Various customer personas and scenarios
- Full audio and transcript capture

## 📋 Implementation Status

### ✅ Successfully Completed

1. **Separate Agent Architecture**: Implemented two separate agent workers with unique `agent_name` identifiers
2. **Agent Dispatch API**: Successfully integrated LiveKit Agent Dispatch API for multi-agent orchestration
3. **Room Management**: Created orchestrator for room creation, agent dispatch, and monitoring
4. **API Compatibility Fixes**: Fixed all LiveKit SDK v1.2.18 compatibility issues:
   - RoomService initialization with aiohttp ClientSession
   - AgentDispatchService initialization
   - CreateAgentDispatchRequest API calls
   - ListParticipantsResponse handling
   - Participant detail logging

### ⚠️ Current Issues & Pending Work

1. **Agent Communication**: Agents join the room but are designed for human interaction (participant type: STANDARD), not agent-to-agent (type: AGENT)
2. **Audio Flow**: Need to implement proper audio routing between agents using RoomInputOptions
3. **Conversation Initiation**: Agents wait for human input instead of initiating conversation with each other
4. **Transcript Capture**: Need to verify transcripts contain actual conversation content

## 🏗️ Architecture Overview

### The Correct Pattern: Separate Workers

```
┌─────────────────────┐
│  Orchestrator       │
│ (conversation_runner)│
└──────┬──────────────┘
       │ Creates room & dispatches
       ├─────────────┬────────────┐
       ▼             ▼            ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│   Room   │  │ Support  │  │ Customer │
│          │◄─┤  Agent   │  │  Agent   │
│          │  └──────────┘  └──────────┘
└──────────┘   worker-1      worker-2
```

### Key Principle
**Each agent = One job = One WebRTC connection = One AgentSession**

This is the fundamental architecture that LiveKit enforces. Attempting to share connections or create multiple sessions within one job violates this pattern.

## 📁 Current Implementation Files

### Core Files
```
src/
├── support_agent.py       # Support agent worker (agent_name: "support-agent")
├── customer_agent.py      # Customer agent worker (agent_name: "customer-agent")
├── livekit_conversation_runner.py  # Orchestrator for room creation and dispatch
└── run_agents.sh         # Shell script for running the complete system
```

### Removed Obsolete Files
The following files have been removed as they represented failed approaches:
- agent_to_agent_v1.py (v1 pattern attempt)
- working_agent_to_agent.py (file-based coordination)
- unified_agent.py (failed unified approach)
- unified_agent_v2.py (another unified attempt)
- unified_agent_with_recording.py
- simple_test_agent.py (testing file)
- test_unified_dispatch.py (test script)

## 🔧 Implementation Details & Fixes Applied

### 1. Support Agent (`src/support_agent.py`)
```python
# Key configuration
WorkerOptions(
    entrypoint_fnc=entrypoint,
    agent_name="support-agent",  # CRITICAL: Unique agent name
)

# Agent session setup
session = agents.AgentSession(
    stt=agents.stt.StreamAdapter(
        stt=openai.STT(model="whisper-1"),
        vad=silero.VAD.load(),
    ),
    llm=openai.LLM(model="gpt-4o-mini"),
    tts=openai.TTS(voice="nova"),
)
```

### 2. Customer Agent (`src/customer_agent.py`)
```python
# Key configuration
WorkerOptions(
    entrypoint_fnc=entrypoint,
    agent_name="customer-agent",  # CRITICAL: Different agent name
)

# Uses "alloy" voice to distinguish from support agent
tts=openai.TTS(voice="alloy")
```

### 3. Orchestrator (`src/livekit_conversation_runner.py`)

#### Fixed Issues:

**Issue 1: RoomService Initialization**
```python
# Before (Error):
room_api = room_service.RoomService(self.url, self.api_key, self.api_secret)

# After (Fixed):
import aiohttp
async with aiohttp.ClientSession() as session:
    room_api = room_service.RoomService(session, self.url, self.api_key, self.api_secret)
```

**Issue 2: Agent Dispatch API**
```python
# Before (Error):
dispatch_request = api.CreateDispatchRequest(...)

# After (Fixed):
dispatch_request = api.CreateAgentDispatchRequest(
    room=room_name,
    agent_name=agent_name,
)
```

**Issue 3: Participants Response Handling**
```python
# Before (Error):
for p in response:  # ListParticipantsResponse not iterable

# After (Fixed):
participants = response.participants if hasattr(response, 'participants') else []
for p in participants:
    # Process participants
```

**Issue 4: Participant Detail Logging**
```python
# Before (Error):
logger.info(f"kind: {p.kind.name}")  # AttributeError: 'int' has no name

# After (Fixed):
kind_str = p.kind.name if hasattr(p.kind, 'name') else str(p.kind)
state_str = p.state.name if hasattr(p.state, 'name') else str(p.state)
```

### 4. Environment Variable Handling (`run_agents.sh`)

**Issue: Environment variables not inherited by subprocesses**
```bash
# Fixed with proper export:
set -a
source .env.local
set +a
```

## 🚀 Required Next Steps for Agent-to-Agent Communication

### Enable Agent-to-Agent Audio

The current implementation needs to be modified to enable agents to hear each other:

```python
from livekit.agents.participant_kind import PARTICIPANT_KIND_AGENT, PARTICIPANT_KIND_STANDARD

# In each agent's entrypoint
room_input_options = RoomInputOptions(
    participant_kinds=[PARTICIPANT_KIND_AGENT, PARTICIPANT_KIND_STANDARD],
)

await session.start(
    agent=agent_instance,
    room=ctx.room,
    room_input_options=room_input_options,
    room_output_options=RoomOutputOptions(),
)
```

## 🧪 Running the System

### 1. Start Both Agent Workers
```bash
# Terminal 1
uv run python src/support_agent.py dev

# Terminal 2
uv run python src/customer_agent.py dev
```

### 2. Run the Conversation
```bash
# Terminal 3
uv run python src/livekit_conversation_runner.py [room_name] [duration]
```

### 3. Or Use the Complete Script
```bash
./run_agents.sh
```

The orchestrator will:
1. Create a room
2. Dispatch the support agent
3. Dispatch the customer agent
4. Monitor the conversation
5. Save transcripts when done

## ❌ Failed Approaches & Lessons Learned

### Mistake 1: Unified Agent Approach
**Attempted**: Single worker handling both roles with file-based coordination
**Why it failed**: LiveKit's dispatch system only routes to one named worker at a time

### Mistake 2: Two Sessions in One Entrypoint
**Attempted**: Both sessions in same worker sharing WebRTC connection
**Why it failed**: Violates LiveKit's architecture of one session per connection

### Mistake 3: Using participant_identity
**Attempted**: Setting bogus participant identities for routing
**Why it failed**: No such participants exist in the room

## 🐛 Troubleshooting Guide

### Issue: Agents Join But Don't Converse
- **Check**: Are both agents using RoomInputOptions with PARTICIPANT_KIND_AGENT?
- **Check**: Are the agents' on_enter() methods being called?
- **Check**: Are the agents' on_user_turn_completed() methods firing?

### Issue: Only One Agent Joins
- **Check**: Are both agent workers running?
- **Check**: Is the orchestrator dispatching both agents explicitly?
- **Check**: Do the agent_name values match between worker and dispatch?

### Issue: Empty Transcripts
- **Check**: Is conversation_item_added event handler registered?
- **Check**: Are the agents actually speaking (check TTS generation)?
- **Check**: Is the session.history being populated during conversation?

### Issue: Environment Variables Not Found
- **Check**: .env.local file exists with correct credentials
- **Check**: Using `set -a` and `set +a` around `source .env.local`
- **Check**: Explicit exports in shell scripts

## 📊 Test Results

### Current State
- Room creation: ✅ Working
- Support agent dispatch: ✅ Working
- Customer agent dispatch: ✅ Working
- Agents join room: ✅ Working (2 participants visible)
- Agent conversation: ❌ Not working (agents wait for human input)
- Audio capture: ❓ Not verified
- Transcript capture: ❓ Not verified

## 🔍 Debug Commands

```bash
# Check running processes
ps aux | grep python

# Monitor room participants
lk room participants list <room-name>

# Check agent logs
tail -f /tmp/agent_conversation_*.log

# View transcripts
ls -la /tmp/transcript_*.json
```

## 📝 Environment Configuration

Required environment variables in `.env.local`:
```
LIVEKIT_URL=wss://test-4yycb0oi.livekit.cloud
LIVEKIT_API_KEY=APIM6cxVrpw4c2i
LIVEKIT_API_SECRET=Vm46rvuQT1CRkezI8DzhUNptQHqwEGcQvIexPb69Dxr
OPENAI_API_KEY=<your-key>
```

## 🎯 Success Criteria

The implementation will be considered successful when:
1. ✅ Both agents connect to LiveKit
2. ✅ Both agents join the same room
3. ❌ Agents have a multi-turn conversation (pending)
4. ❌ Audio is generated for both agents (pending)
5. ❌ Full transcripts are captured (pending)
6. ✅ No errors in logs

## 📚 References

- **LiveKit Agents SDK v1.2.18**: Using v1 patterns (not v0)
- **Agent Dispatch API**: For explicit multi-agent dispatch
- **RoomInputOptions**: Key to enabling agent-to-agent audio
- **WorkerOptions.agent_name**: Critical for dispatch identification
- **aiohttp**: Required for LiveKit API service initialization

## 🔮 Future Improvements

1. **Implement Agent-to-Agent Audio**: Modify agents to use RoomInputOptions
2. **Add Conversation Logic**: Update agents to initiate conversation without human input
3. **Error Handling**: Implement retry logic for dispatch failures
4. **Optimize Timing**: Fine-tune delays between agent actions
5. **Add Metrics**: Track conversation quality metrics
6. **Audio Recording**: Implement egress API for audio capture

## 📌 Conclusion

The LiveKit agent-to-agent communication infrastructure is successfully set up with proper room creation, agent dispatch, and monitoring. The main remaining challenge is modifying the agents to communicate with each other rather than waiting for human input. This requires:

1. Implementing RoomInputOptions to enable agent-to-agent audio
2. Modifying agent logic to initiate conversation autonomously
3. Ensuring proper audio flow between agents

Once these modifications are made, the system will achieve full agent-to-agent voice communication with audio and transcript capture capabilities.

---

**Last Updated**: 2025-11-19 1:30 PM PST
**Status**: Infrastructure Complete, Agent Communication Pending