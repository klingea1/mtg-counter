#!/usr/bin/env bash
# Run this on macOS/Linux to start the MTG Counter server.
cd "$(dirname "$0")"

if command -v python3 &>/dev/null; then
    python3 server.py "$@"
elif command -v python &>/dev/null; then
    python server.py "$@"
else
    echo "Could not find Python on this computer."
    echo "Install it (e.g. 'brew install python3') and run this script again."
    exit 1
fi
