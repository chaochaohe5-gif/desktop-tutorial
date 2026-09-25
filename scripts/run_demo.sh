#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v python3 >/dev/null 2>&1; then
  runtime=python3
else
  runtime=python
fi
demo_output="output/demo-$(date +%Y%m%d-%H%M%S)-$$"
"$runtime" -m manju build examples/episode.json --out "$demo_output"
