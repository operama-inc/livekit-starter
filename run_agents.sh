#!/bin/bash

# Agent-to-Agent Communication Test Script
# This script starts both support and customer agents, then runs the conversation orchestrator

echo "=============================================="
echo "LiveKit Agent-to-Agent Communication Test"
echo "=============================================="

# Load environment variables from .env.local
if [ -f .env.local ]; then
    echo "Loading environment from .env.local..."
    # Export all variables from .env.local
    set -a
    source .env.local
    set +a
else
    echo "Warning: .env.local not found, using hardcoded values"
    export LIVEKIT_API_KEY="APIM6cxVrpw4c2i"
    export LIVEKIT_API_SECRET="Vm46rvuQT1CRkezI8DzhUNptQHqwEGcQvIexPb69Dxr"
    export LIVEKIT_URL="wss://test-4yycb0oi.livekit.cloud"
fi

# Verify environment variables are set
echo "Environment check:"
echo "  LIVEKIT_URL: ${LIVEKIT_URL:0:20}..."
echo "  LIVEKIT_API_KEY: ${LIVEKIT_API_KEY:0:10}..."
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:0:10}..."

# Kill any existing Python processes related to agents
echo ""
echo "Cleaning up existing processes..."
pkill -f "python.*agent" 2>/dev/null || true
pkill -f "python.*runner" 2>/dev/null || true
sleep 2

echo ""
echo "Starting support agent (terminal simulation)..."
LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
LIVEKIT_URL="$LIVEKIT_URL" \
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run python src/support_agent.py dev &
SUPPORT_PID=$!
echo "Support agent PID: $SUPPORT_PID"

echo "Waiting for support agent to initialize..."
sleep 5

echo ""
echo "Starting customer agent (terminal simulation)..."
LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
LIVEKIT_URL="$LIVEKIT_URL" \
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run python src/customer_agent.py dev &
CUSTOMER_PID=$!
echo "Customer agent PID: $CUSTOMER_PID"

echo "Waiting for customer agent to initialize..."
sleep 5

echo ""
echo "=============================================="
echo "Running conversation orchestrator..."
echo "=============================================="
LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
LIVEKIT_URL="$LIVEKIT_URL" \
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run python src/livekit_conversation_runner.py

# Cleanup on exit
echo ""
echo "Cleaning up..."
kill $SUPPORT_PID $CUSTOMER_PID 2>/dev/null || true
pkill -f "python.*agent" 2>/dev/null || true

echo "Test complete!"