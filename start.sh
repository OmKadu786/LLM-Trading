#!/usr/bin/env bash

# Start the MCP Services in the background
echo "🚀 Starting MCP background tools (Alpaca, Math, Search)..."
python3 agent_tools/start_mcp_services.py &

# Wait briefly to ensure ports are listening
echo "⏳ Waiting for servers to initialize..."
sleep 5

# Start the main trading loop
echo "📈 Booting up the Live AI-Trader Agent..."
python3 main.py --interval 60
