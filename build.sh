#!/usr/bin/env bash
# exit on error
set -o errexit

# Install Python dependencies
pip install -r requirements.txt

# Create static directory if it doesn't exist
mkdir -p static

# You can add other build steps here if needed
echo "Build completed successfully!"