#!/usr/bin/env bash
# Linux / WSL / macOS: open the app (run "conda activate laptop-compare" first).
cd "$(dirname "$0")" && laptop-compare --serve "$@"
