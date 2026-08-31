#!/bin/bash
# Test workflow tick endpoint

# Set environment variables to enable workflow engine
export ENABLE_WORKFLOW_ENGINE=true
export INTERNAL_TICK_TOKEN="test-token-12345-workflow-engine-test"
export GEMINI_API_KEY=${GEMINI_API_KEY}

# Start backend in background if not running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "Starting backend..."
    cd /Users/juanpablo/Sephiroth/clinical-ai-copilot
    PYTHONPATH=.:platform .venv/bin/uvicorn api.main:app --reload --port 8000 > /tmp/sephiroth.log 2>&1 &
    sleep 3
fi

echo "Testing workflow tick endpoint..."
echo ""

# Make request to tick endpoint
curl -X POST http://localhost:8000/internal/tick \
    -H "X-Internal-Token: $INTERNAL_TICK_TOKEN" \
    -H "Content-Type: application/json" \
    -s | jq .

echo ""
echo "✓ Tick request completed"
