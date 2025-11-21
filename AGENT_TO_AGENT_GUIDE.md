# Agent-to-Agent Communication Guide

## Project Overview

This project enables **agent-to-agent voice communication** using LiveKit to generate synthetic conversations quickly. Two AI agents (customer and support) can have real-time voice conversations, with proper turn-taking, interruption handling, and conversation recording.

## Current Status: ⚠️ PARTIALLY WORKING

After extensive debugging and testing (as of 2025-11-20 14:49), the system has several critical issues that prevent full agent-to-agent conversation:

### ✅ Working Components:
1. **VAD/Turn Detection Fixed** - Configuration corrected
2. **Environment Variables Loading** - Using dotenv
3. **Agent Registration** - Both agents register with LiveKit
4. **Room Creation** - Rooms created successfully
5. **Support Agent Dispatch** - Support agent receives jobs

### ❌ Current Issues:
1. **Invalid OpenAI Model** - ~~LLM_MODEL was set to invalid `gpt-4.1`~~ **FIXED to `gpt-4o-mini`**
2. **Named Dispatch in Dev Mode** - Customer agent never receives job dispatch
3. **Port Conflict in Production** - Both agents try to use port 8081
4. **Egress API Error** - Audio recording fails even with `file_outputs` parameter
5. **No Actual Conversation** - Agents don't communicate with each other

## Architecture

```
┌─────────────────┐       WebRTC Audio        ┌─────────────────┐
│  Support Agent  │◄──────────────────────────►│  Customer Agent │
│  (port: 8081)   │       LiveKit Room         │  (port: 8082)  │
│  Voice: nova    │                            │  Voice: alloy   │
└─────────────────┘                            └─────────────────┘
        │                                               │
        └─────────────┐                  ┌──────────────┘
                      ▼                  ▼
                 ┌────────────────────────────┐
                 │    LiveKit Cloud Server    │
                 │  - Room Management         │
                 │  - Agent Dispatch          │
                 │  - Audio Recording         │
                 └────────────────────────────┘
```

## Critical Issues & Error Details

### 1. Invalid OpenAI Model Error (FIXED)

**Error Message:**
```
httpx.HTTPStatusError: Client error '404 Not Found' for url 'https://api.openai.com/v1/'
```

**Root Cause:** `.env.local` had invalid model `LLM_MODEL=gpt-4.1`

**Fix Applied:** Changed to valid model `LLM_MODEL=gpt-4o-mini`

### 2. Egress API Error (Audio Recording)

**Error Message:**
```
2025-11-20 14:49:24,892 - ERROR - Error starting egress:
TwirpError(code=invalid_argument, message=request has missing or invalid field: output, status=400)
```

**Code Location:** `src/livekit_conversation_runner.py:150-154`
```python
# Tried multiple approaches that failed:
# Approach 1: file parameter
req = RoomCompositeEgressRequest(
    room_name=room_name,
    audio_only=True,
    file=file_output,  # Failed with "output" field error
)

# Approach 2: file_outputs list
req = RoomCompositeEgressRequest(
    room_name=room_name,
    audio_only=True,
    file_outputs=[file_output],  # Still failed with same error
)
```

**Analysis:** The LiveKit API expects a different parameter structure for output configuration that isn't documented in the SDK.

### 3. Named Dispatch Doesn't Work in Dev Mode

**Test Results from Dev Mode (2025-11-20 14:49):**
```
Support Agent:
- Registered: ✅ "registered worker {"id": "AW_4KtqKU48sERk"}"
- Job Received: ✅ Support agent joins room

Customer Agent:
- Registered: ✅ "registered worker {"id": "AW_efFUe4qPBFcp"}"
- Job Received: ❌ Never joins room

Room Status: Only 1 participant (support agent) throughout 60-second monitoring
```

**Code:** Both dispatches are created (`src/livekit_conversation_runner.py:209-216`):
```python
# Dispatch support agent
await self.dispatch_agent(room_name, "support-agent")
await asyncio.sleep(2)
# Dispatch customer agent
await self.dispatch_agent(room_name, "customer-agent")
```

**Issue:** In dev mode, the LiveKit SDK doesn't properly route named dispatches to specific workers. Only the first available worker (support) receives jobs.

### 4. Port Conflict in Production Mode

**Error Message:**
```
OSError: [Errno 48] error while attempting to bind on address ('::', 8081, 0, 0):
address already in use
```

**Issue:** Both agents default to port 8081. The SDK doesn't support `http_port` parameter in `WorkerOptions` or `--http-port` CLI flag.

**Attempted Fix (Failed):**
```python
# This doesn't work - SDK doesn't accept http_port parameter:
worker_opts = WorkerOptions(
    entrypoint_fnc=entrypoint,
    agent_name="support-agent",
    http_port=http_port,  # ❌ TypeError: unexpected keyword argument
)
```

### 5. No Conversation Happening

**Root Cause:** Customer agent never joins the room because it doesn't receive the dispatch.

**Support Agent Behavior:**
- Successfully joins room
- Starts generating initial message
- Waits for customer who never arrives

**Transcript Files:** Empty (no messages exchanged)
```json
{
    "room": "agent-conversation-1763678406",
    "agent": "support-agent",
    "timestamp": "2025-11-20T14:40:10",
    "messages": [],
    "conversation_turns": 0
}
```

## Test Logs & Evidence

### Latest Test Run (2025-11-20 14:49)

**Setup:**
```bash
# Dev mode test to avoid port conflict
./run_agents_dev_test.sh
```

**Key Log Entries:**

1. **Room Creation Success:**
```
2025-11-20 14:49:23,499 - INFO - Created room: agent-conversation-1763678962
```

2. **Invalid OpenAI Model Error (from support agent log):**
```
httpx.HTTPStatusError: Client error '404 Not Found' for url 'https://api.openai.com/v1/'
Model: gpt-4.1 (INVALID - Fixed to gpt-4o-mini)
```

3. **Egress API Failure:**
```
2025-11-20 14:49:24,892 - ERROR - Error starting egress:
TwirpError(code=invalid_argument, message=request has missing or invalid field: output, status=400)
```

4. **Both Agents Dispatched:**
```
2025-11-20 14:49:25,988 - INFO - Created dispatch for support-agent: id: "AD_XGV8ubEVqs6D"
2025-11-20 14:49:28,081 - INFO - Created dispatch for customer-agent: id: "AD_bgLXnZDAksoT"
```

5. **Only Support Agent in Room:**
```
2025-11-20 14:49:31,179 - INFO - [  0s] Room: 1 participants (1 agents, 0 standard)
2025-11-20 14:50:06,404 - INFO - [ 35s] Room: 1 participants (1 agents, 0 standard)
```

## Code Files with Issues

### 1. `src/livekit_conversation_runner.py`
- **Lines 150-154**: Egress API parameter issue
- **Lines 195-202**: Egress recording implementation
- **Lines 209-216**: Agent dispatch logic

### 2. `src/support_agent.py`
- **Lines 201-217**: Port configuration attempt (removed as it doesn't work)
- **Lines 114-121**: VAD configuration (fixed)
- **Lines 56-70**: on_enter method for initiating conversation

### 3. `src/customer_agent.py`
- **Lines 191-210**: Port configuration attempt (removed as it doesn't work)
- **Lines 114-121**: VAD configuration (fixed)
- **Lines 56-60**: on_enter method (waits for support to speak first)

## Working VAD/Turn Detection Fix

The VAD configuration issue was successfully resolved:

**Before (Broken):**
```python
# WRONG - StreamAdapter prevents proper VAD setup
vad = StreamAdapter(
    vad=silero.VAD.load(),
    update_interval=0.1
)
```

**After (Fixed):**
```python
# CORRECT - Pass VAD directly to AgentSession
session = agents.AgentSession(
    stt=openai.STT(model="whisper-1"),
    llm=openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4o-mini")),
    tts=openai.TTS(voice="nova"),
    vad=silero.VAD.load(),  # Direct VAD instance
    turn_detection=MultilingualModel(),  # Proper turn detection
    allow_interruptions=True,
)
```

## Recommendations for Resolution

### 1. Fix Egress API
Research the correct LiveKit Egress API structure. The SDK documentation doesn't match the API requirements:
- Neither `file` nor `file_outputs` work
- The API expects an "output" field with different structure
- May need to use direct API calls instead of SDK

### 2. Use Production Mode with Workarounds
- Run agents on different machines
- Use Docker containers with port mapping
- Or accept single-agent limitation

### 3. Alternative Architecture
Consider running both agents in a single process with different personalities/roles rather than separate workers.

## Test Scripts

### Dev Mode Test Script (`run_agents_dev_test.sh`)
```bash
#!/bin/bash
# Starts both agents in dev mode (avoids port conflict)
uv run python src/support_agent.py dev 2>&1 | tee /tmp/support_dev_test.log &
sleep 3
uv run python src/customer_agent.py dev 2>&1 | tee /tmp/customer_dev_test.log &
sleep 3
uv run python src/livekit_conversation_runner.py
```

### Production Mode Script (`run_agents_production.sh`)
```bash
#!/bin/bash
# Attempts production mode (fails due to port conflict)
uv run python src/support_agent.py start &  # Port 8081
uv run python src/customer_agent.py start &  # Also wants 8081 - FAILS
```

## Environment Configuration

### `.env.local`
```
LIVEKIT_URL=wss://test-4yycb0oi.livekit.cloud
LIVEKIT_API_KEY=APIM6cxVrpXXXX
LIVEKIT_API_SECRET=XXXXX
OPENAI_API_KEY=sk-proj-XXXXX
LLM_MODEL=gpt-4o-mini
```

## Transcript Storage

Transcripts are saved to: `/Users/sid/Documents/GitHub/livekit-starter/data/livekit_conversations/`

Format: `transcript_{agent}_{room}_{timestamp}.json`

**Current Issue:** All transcripts are empty as no conversation occurs.

## Summary

The agent-to-agent communication system has fundamental architectural issues:

1. **Invalid OpenAI Model**: Fixed from `gpt-4.1` to `gpt-4o-mini`
2. **Dev Mode**: Named dispatch doesn't work - only one agent gets jobs
3. **Production Mode**: Port conflict prevents multiple agents
4. **Egress API**: Incorrect parameter structure prevents audio recording
5. **Result**: No actual agent-to-agent conversation occurs

The VAD/turn detection and OpenAI model issues have been successfully fixed, but the agents never get to communicate because customer agent doesn't join the room (dev mode dispatch limitation).

---

*Last Updated: 2025-11-20 14:51*
*Status: Requires SDK updates or architectural changes to work*
*Version: 0.5.1 - Partially functional, no conversation capability*