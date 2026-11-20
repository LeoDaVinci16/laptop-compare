#!/usr/bin/env bash
# Linux / WSL / macOS: generate the report (run "conda activate laptop-compare" first).
cd "$(dirname "$0")" && laptop-compare "$@"
