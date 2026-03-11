#!/usr/bin/env bash
set -euo pipefail

# Release the DrugClaw research runtime and its distribution metadata.

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_CLIPPY=1
RUN_WEBSITE=1
RUN_NIXPKGS="${AUTO_NIXPKGS_UPDATE:-0}"
MODE="release"

usage() {
  cat <<'USAGE'
Usage:
  ./deploy.sh [release] [--skip-clippy] [--skip-website] [--with-nixpkgs]

Options:
  release         Run the release pipeline (default)
  --skip-clippy   Skip pre-release `cargo clippy --all-targets -- -D warnings`
  --skip-website  Skip `website/deploy_pages.sh`
  --with-nixpkgs  Run `scripts/update-nixpkgs.sh` after release
  -h, --help      Show help

Notes:
  - This script delegates the actual release flow to `scripts/release_homebrew.sh`.
  - `AUTO_NIXPKGS_UPDATE=1` is still honored for compatibility.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    release)
      MODE="release"
      shift
      ;;
    --skip-clippy)
      RUN_CLIPPY=0
      shift
      ;;
    --skip-website)
      RUN_WEBSITE=0
      shift
      ;;
    --with-nixpkgs)
      RUN_NIXPKGS=1
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

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "deploy.sh must run inside a git checkout." >&2
  exit 1
fi

if [[ ! -x "$ROOT_DIR/scripts/release_homebrew.sh" ]]; then
  echo "Missing executable: scripts/release_homebrew.sh" >&2
  exit 1
fi

if [[ "$RUN_CLIPPY" == "1" ]]; then
  echo "[deploy] pre-release clippy"
  cargo clippy --all-targets -- -D warnings
fi

echo "[deploy] starting ${MODE} pipeline"
"$ROOT_DIR/scripts/release_homebrew.sh"

if [[ "$RUN_NIXPKGS" == "1" ]]; then
  if [[ ! -x "$ROOT_DIR/scripts/update-nixpkgs.sh" ]]; then
    echo "Missing executable: scripts/update-nixpkgs.sh" >&2
    exit 1
  fi
  echo "[deploy] updating nixpkgs"
  "$ROOT_DIR/scripts/update-nixpkgs.sh"
fi

if [[ "$RUN_WEBSITE" == "1" && -f "$ROOT_DIR/website/deploy_pages.sh" ]]; then
  echo "[deploy] publishing website pages"
  (
    cd "$ROOT_DIR/website"
    sh ./deploy_pages.sh
  )
fi

echo "[deploy] completed"
