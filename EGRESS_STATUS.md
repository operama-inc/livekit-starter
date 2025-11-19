# Egress API Status

## Current Issue
The LiveKit Egress API is returning "request has missing or invalid field: output" error when trying to start room composite egress.

## Attempted Fixes
1. Changed from `file` to `file_outputs` (list)
2. Fixed `DeleteRoomRequest` to use `room` instead of `name`
3. Added `file_type=api.EncodedFileType.MP3` for audio-only recordings

## Code Status
File: `src/audio_egress_recorder.py`
- AudioEgressRecorder class implemented
- Start/stop recording methods working
- Configuration issue with RoomCompositeEgressRequest

## Working Solution
The unified agent (`src/unified_agent_v2.py`) successfully:
- Handles both customer and support agents in a single worker
- Uses file-based coordination to assign roles
- Both agents can join the same room and communicate
- Transcripts are available via room events

## Alternative Approaches
1. **Room Events**: Subscribe to room events and capture transcripts in real-time
2. **Agent Hooks**: Use LiveKit agent observability hooks to capture conversation data
3. **Custom Recording**: Build custom recording using room participant tracks
4. **Cloud Recording**: Use LiveKit Cloud's built-in recording features

## Next Steps
1. Focus on scaling the conversation generation
2. Capture transcripts via room events instead of egress
3. Generate audio files post-conversation if needed