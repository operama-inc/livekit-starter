# Agent-to-Agent Communication Investigation Log

## Problem Statement
When attempting to run agent-to-agent conversations with LiveKit, only one agent receives its dispatch request. The customer agent never receives its job request, preventing two agents from joining the same room.

## Investigation Timeline

### Attempt 1: Separate Agent Workers with Named Dispatch
**Date**: 2025-11-18
**Approach**: Run separate workers for customer_agent.py and support_agent.py with explicit agent_name parameters
**Result**: ❌ Failed
- Support agent receives dispatch and joins room
- Customer agent worker registers but never receives dispatch request
- Room shows only 1 participant

### Attempt 2: Simple Test Agent with Role Detection
**Date**: 2025-11-18
**Approach**: Single agent file that detects role based on room participant count
**Result**: ❌ Failed
- Only one instance joins the room
- Second dispatch doesn't reach any worker

## Root Cause Analysis

### Theory 1: Named Dispatch Routing Issue
Only one worker can handle named dispatches at a time. The dispatch system may route all requests to the first registered worker, regardless of agent_name.

### Theory 2: Worker Registration Problem
Multiple workers with different agent_names might not be properly differentiated by the LiveKit dispatch system.

## Solution Approach: Unified Agent Dispatcher

### Design
Create a single worker that:
1. Receives all dispatch requests
2. Reads role from job metadata
3. Instantiates appropriate agent class (CustomerAgent or SupportAgent)
4. Both agents run in the same worker process but as separate sessions

### Implementation Plan
1. Create unified_agent.py that handles both roles
2. Use job metadata to determine which agent to instantiate
3. Test with sequential agent joining
4. Monitor dispatch request handling

## Test Results

### Test 1: Unified Agent Basic Test
**Date**: 2025-11-18
**Command**: `uv run python src/unified_agent.py dev`
**Result**: ✅ Partial Success
- Both agents receive dispatch requests
- Single worker handles multiple dispatches
- **Issue**: Race condition - both agents become customers

### Test 2: Agent-to-Agent Conversation
**Date**: 2025-11-18
**Setup**: Runner dispatches both agents to same room
**Result**: ❌ Failed
- Both agents join as customers due to race condition
- No support agent created

## Lessons Learned
1. **Dispatch Routing Limitation**: LiveKit dispatches to one worker at a time when using named agents
2. **Unified Worker Solution**: Single worker handling all dispatches solves the routing issue
3. **Race Condition**: Multiple agents checking participant count simultaneously causes role conflicts
4. **Coordination Required**: Need external coordination (file lock, database) to prevent race conditions

## Solution Status
✅ **FULLY VERIFIED**: Created unified_agent_v2.py with:
- Single worker handles all dispatch requests
- File-based coordination to prevent race conditions
- Deterministic role assignment based on job order
- Both agents successfully join same room and communicate

### Successful Test Results (2025-11-18 22:01)
- First agent (AJ_WPr9oL7mNb8T) → Assigned customer role (राज शर्मा)
- Second agent (AJ_Fh355biycw3z) → Assigned support role (फ़ैज़ान)
- Both connected to room "test-unified-agent"
- Customer initiated conversation: "Hello, I need help with my account."

## Next Steps
1. ✅ Implement unified_agent.py
2. ✅ Test dispatch metadata routing
3. ✅ Create race condition fix (unified_agent_v2.py)
4. ✅ Test agent-to-agent conversation - WORKING!
5. 🔄 Scale to batch conversations (100-200)