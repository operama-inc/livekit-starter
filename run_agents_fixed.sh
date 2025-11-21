#!/bin/bash

echo "==============================================
LiveKit Agent-to-Agent Communication Test (Fixed Port Conflict)
=============================================="

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
sleep 2

# Start support agent on port 8081
echo "Starting support agent on port 8081..."
uv run python src/support_agent.py start --http-port 8081 &
SUPPORT_PID=$!
echo "Support agent PID: $SUPPORT_PID"
echo "Waiting for support agent to initialize..."
sleep 5

# Start customer agent on port 8082
echo ""
echo "Starting customer agent on port 8082..."
uv run python src/customer_agent.py start --http-port 8082 &
CUSTOMER_PID=$!
echo "Customer agent PID: $CUSTOMER_PID"
echo "Waiting for customer agent to initialize..."
sleep 5

# Run the conversation orchestrator
echo ""
echo "=============================================="
echo "Running conversation orchestrator..."
echo "=============================================="
uv run python src/livekit_conversation_runner.py

# Clean up
echo ""
echo "Cleaning up..."
kill $SUPPORT_PID 2>/dev/null
kill $CUSTOMER_PID 2>/dev/null
pkill -f "support_agent.py" 2>/dev/null
pkill -f "customer_agent.py" 2>/dev/null

echo "Test complete!"