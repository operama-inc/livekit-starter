#!/bin/bash

echo "================================================
LiveKit Agent-to-Agent Complete Test with Audio
================================================"

# Change to the project directory
cd /Users/sid/Documents/GitHub/livekit-starter

# Load environment variables
source .env.local

echo "Loading environment from .env.local..."
echo "Environment check:"
echo "  LIVEKIT_URL: ${LIVEKIT_URL:0:20}..."
echo "  LIVEKIT_API_KEY: ${LIVEKIT_API_KEY:0:10}..."
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:0:10}..."
echo ""

# Clean up any existing processes
echo "Cleaning up existing processes..."
pkill -f "support_agent.py" 2>/dev/null
pkill -f "customer_agent.py" 2>/dev/null
pkill -f "livekit_conversation_runner.py" 2>/dev/null
sleep 3

# Start support agent in production mode
echo "Starting support agent in production mode..."
AGENT_HTTP_PORT=8081 uv run python src/support_agent.py start &
SUPPORT_PID=$!
echo "Support agent PID: $SUPPORT_PID"
echo "Waiting for support agent to initialize..."
sleep 8

# Start customer agent in production mode (will auto-select different port)
echo ""
echo "Starting customer agent in production mode..."
AGENT_HTTP_PORT=8082 uv run python src/customer_agent.py start &
CUSTOMER_PID=$!
echo "Customer agent PID: $CUSTOMER_PID"
echo "Waiting for customer agent to initialize..."
sleep 8

# Check if agents are running
ps -p $SUPPORT_PID > /dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Support agent failed to start!"
    ps aux | grep support_agent | grep -v grep
fi

ps -p $CUSTOMER_PID > /dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Customer agent failed to start!"
    ps aux | grep customer_agent | grep -v grep
fi

# Run the conversation orchestrator with longer monitoring
echo ""
echo "================================================"
echo "Running conversation orchestrator..."
echo "================================================"
uv run python src/livekit_conversation_runner.py agent-conversation-test 90

# Wait a bit for transcripts to save
echo ""
echo "Waiting for transcripts to save..."
sleep 5

# Check for conversation transcripts
echo ""
echo "================================================"
echo "Checking for conversation results..."
echo "================================================"

# Find the latest transcript files
echo "Looking for transcript files..."
ls -la /tmp/transcript_*test* 2>/dev/null | tail -5

# Check if audio file was created (if egress was enabled)
echo ""
echo "Looking for audio files..."
ls -la /tmp/livekit_conv_*.mp4 2>/dev/null | tail -5

# Display some conversation content if available
LATEST_SUPPORT=$(ls -t /tmp/transcript_support_* 2>/dev/null | head -1)
LATEST_CUSTOMER=$(ls -t /tmp/transcript_customer_* 2>/dev/null | head -1)

if [ -f "$LATEST_SUPPORT" ]; then
    echo ""
    echo "Support Agent Transcript Preview:"
    jq '.messages[0:3]' "$LATEST_SUPPORT" 2>/dev/null || cat "$LATEST_SUPPORT" | head -20
fi

if [ -f "$LATEST_CUSTOMER" ]; then
    echo ""
    echo "Customer Agent Transcript Preview:"
    jq '.messages[0:3]' "$LATEST_CUSTOMER" 2>/dev/null || cat "$LATEST_CUSTOMER" | head -20
fi

# Clean up
echo ""
echo "Cleaning up processes..."
kill $SUPPORT_PID 2>/dev/null
kill $CUSTOMER_PID 2>/dev/null
pkill -f "support_agent.py" 2>/dev/null
pkill -f "customer_agent.py" 2>/dev/null

echo ""
echo "================================================"
echo "Test complete!"
echo "Check /tmp/ for transcript and audio files"
echo "================================================"