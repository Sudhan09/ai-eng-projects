#!/usr/bin/env bash
# Rebuild the project map (build/flowmap.html). Same as: python3 tools/flowmap.py build [--check]
exec python3 "$(dirname "$0")/tools/flowmap.py" build "$@"
