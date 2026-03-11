#!/usr/bin/env bash
set -euo pipefail

# Validate the DrugClaw research runtime, docs, and local web surfaces.

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_WEB=1
RUN_WEBSITE=1
RUN_DOCS=1
RUST_ONLY=0

usage() {
  cat <<'USAGE'
Usage:
  ./check.sh [--rust-only] [--skip-web] [--skip-website] [--skip-docs]

Options:
  --rust-only      Run only Rust tests
  --skip-web       Skip `npm --prefix web run build`
  --skip-website   Skip `npm --prefix website run build`
  --skip-docs      Skip docs artifact drift check
  -h, --help       Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rust-only)
      RUST_ONLY=1
      RUN_WEB=0
      RUN_WEBSITE=0
      RUN_DOCS=0
      shift
      ;;
    --skip-web)
      RUN_WEB=0
      shift
      ;;
    --skip-website)
      RUN_WEBSITE=0
      shift
      ;;
    --skip-docs)
      RUN_DOCS=0
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

echo "[check] rust tests"
cargo test -q

if [[ "$RUST_ONLY" == "1" ]]; then
  echo "[check] completed rust-only run"
  exit 0
fi

if [[ "$RUN_WEB" == "1" && -f "web/package.json" ]]; then
  echo "[check] web build"
  npm --prefix web run build
fi

if [[ "$RUN_WEBSITE" == "1" && -f "website/package.json" ]]; then
  echo "[check] website build"
  npm --prefix website run build
fi

if [[ "$RUN_DOCS" == "1" && -f "scripts/generate_docs_artifacts.mjs" ]]; then
  echo "[check] docs artifact drift"
  node scripts/generate_docs_artifacts.mjs --check
fi

echo "[check] completed"
