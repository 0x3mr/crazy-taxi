#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v cmake >/dev/null 2>&1; then
  echo "CMake 3.20 or newer is required. Install CMake and try again." >&2
  exit 127
fi
cmake -S "$root" -B "$root/build" -DCMAKE_BUILD_TYPE=Release "$@"
cmake --build "$root/build" --config Release
