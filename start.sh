#!/usr/bin/env bash
set -euo pipefail

# Run DrugClaw, the AI Research Assistant for Accelerated Drug Discovery, from source.

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_WEB=1
USE_RELEASE=0
CONFIG_PATH="${DRUGCLAW_CONFIG:-${MICROCLAW_CONFIG:-}}"

usage() {
  cat <<'USAGE'
Usage:
  ./start.sh [--config <path>] [--release] [--skip-web-build]

Options:
  --config <path>    Use a specific config file for this run
  --release          Run `cargo run --release -- start`
  --skip-web-build   Skip `npm --prefix web run build`
  -h, --help         Show help

Notes:
  - `DRUGCLAW_CONFIG` is accepted as a script-level alias and is mapped to
    the runtime's current compatibility env var `MICROCLAW_CONFIG`.
  - The runtime itself still resolves config overrides through `MICROCLAW_CONFIG`.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    --release)
      USE_RELEASE=1
      shift
      ;;
    --skip-web-build)
      BUILD_WEB=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

cd "$ROOT_DIR"

if [[ "$BUILD_WEB" == "1" && -f "web/package.json" ]]; then
  echo "[start] building Web UI"
  npm --prefix web run build
fi

if [[ -n "$CONFIG_PATH" ]]; then
  export MICROCLAW_CONFIG="$CONFIG_PATH"
  export DRUGCLAW_CONFIG="$CONFIG_PATH"
  echo "[start] using config: $CONFIG_PATH"
fi

CMD=(cargo run)
if [[ "$USE_RELEASE" == "1" ]]; then
  CMD+=(--release)
fi
CMD+=(-- start)

echo "[start] running: ${CMD[*]}"
"${CMD[@]}"
