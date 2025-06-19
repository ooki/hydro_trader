#!/bin/bash

# Activate virtual environment if exists
if [ -d "venv" ]; then
  source venv/bin/activate
fi

# Run the server
uvicorn hydro_trader.server:app --host 0.0.0.0 --port 8000