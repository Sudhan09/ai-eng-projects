#!/usr/bin/env bash
# Rebuild the project map (build/flowmap.html). Same as: python3 src/flowmap_tests/flowmap.py build [--check]
exec python3 "$(dirname "$0")/src/flowmap_tests/flowmap.py" build "$@"
