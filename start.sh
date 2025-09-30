#!/bin/bash
set -e

# Install dependencies
pip install -r requirements.txt

# Start the application
exec python main.py
