#!/usr/bin/env bash
set -e

echo "Starting IHP ML Predictor service..."

# Get log level from options (default: info)
LOG_LEVEL=$(jq -r '.log_level // "info"' /data/options.json 2>/dev/null || echo "info")

export FLASK_APP=app.py
export LOG_LEVEL=$LOG_LEVEL

echo "Log level: $LOG_LEVEL"
echo "Starting Flask server on port 5000..."

# Run Flask app
python3 app.py
