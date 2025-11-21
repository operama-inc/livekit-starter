#!/bin/bash

echo "=========================================="
echo "Agent-to-Agent Communication Test (Dev Mode)"
echo "Testing actual conversation with egress recording"
echo "=========================================="

# Kill any existing processes
echo "Cleaning up existing processes..."
pkill -f "python src/support_agent.py" 2>/dev/null
pkill -f "python src/customer_agent.py" 2>/dev/null
pkill -f "livekit_conversation_runner.py" 2>/dev/null
sleep 2

# Start support agent in dev mode
echo ""
echo "[1/3] Starting support agent in dev mode..."
uv run python src/support_agent.py dev 2>&1 | tee /tmp/support_dev_test.log &
SUPPORT_PID=$!
echo "  Support agent PID: $SUPPORT_PID"
sleep 3

# Start customer agent in dev mode
echo ""
echo "[2/3] Starting customer agent in dev mode..."
uv run python src/customer_agent.py dev 2>&1 | tee /tmp/customer_dev_test.log &
CUSTOMER_PID=$!
echo "  Customer agent PID: $CUSTOMER_PID"
sleep 3

# Run conversation
echo ""
echo "[3/3] Starting conversation runner..."
echo "=========================================="
uv run python src/livekit_conversation_runner.py 2>&1 | tee /tmp/conversation_runner_test.log

echo ""
echo "=========================================="
echo "Test complete!"
echo "Check logs at:"
echo "  /tmp/support_dev_test.log"
echo "  /tmp/customer_dev_test.log"
echo "  /tmp/conversation_runner_test.log"
echo "  /Users/sid/Documents/GitHub/livekit-starter/data/livekit_conversations/"
echo "=========================================="

# Wait a bit before cleanup
sleep 5

# Kill agents
echo "Cleaning up agents..."
kill $SUPPORT_PID 2>/dev/null
kill $CUSTOMER_PID 2>/dev/null