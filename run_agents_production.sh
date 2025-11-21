#!/bin/bash

echo "==============================================
LiveKit Agent-to-Agent Communication Test (Production Mode)
=============================================="

# Load environment variables
source .env.local

# Set port configuration
export SUPPORT_AGENT_PORT=8081
export CUSTOMER_AGENT_PORT=8082

echo "Loading environment from .env.local..."
echo "Environment check:"
echo "  LIVEKIT_URL: ${LIVEKIT_URL:0:20}..."
echo "  LIVEKIT_API_KEY: ${LIVEKIT_API_KEY:0:10}..."
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:0:10}..."
echo "Port configuration:"
echo "  SUPPORT_AGENT_PORT: $SUPPORT_AGENT_PORT"
echo "  CUSTOMER_AGENT_PORT: $CUSTOMER_AGENT_PORT"
echo ""

# Clean up any existing processes
echo "Cleaning up existing processes..."
pkill -f "support_agent.py" 2>/dev/null
pkill -f "customer_agent.py" 2>/dev/null
pkill -f "livekit_conversation_runner.py" 2>/dev/null
sleep 2

# Start support agent with 'start' mode
# The SDK will automatically select an available port
echo "Starting support agent (production mode)..."
uv run python src/support_agent.py start 2>&1 | tee /tmp/support_agent_prod.log &
SUPPORT_PID=$!
echo "Support agent PID: $SUPPORT_PID"
echo "Waiting for support agent to initialize..."
sleep 5

# Start customer agent with 'start' mode
# The SDK will automatically select an available port (different from support)
echo ""
echo "Starting customer agent (production mode)..."
uv run python src/customer_agent.py start 2>&1 | tee /tmp/customer_agent_prod.log &
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