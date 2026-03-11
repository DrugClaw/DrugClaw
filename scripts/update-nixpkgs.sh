#!/usr/bin/env bash
set -euo pipefail

# Update the DrugClaw research assistant package in a nixpkgs checkout and optionally open a PR.

usage() {
  cat <<'EOF'
Usage:
  scripts/update-nixpkgs.sh [options]

Default behavior (no options):
  - auto-detect version from Cargo.toml
  - clone <current-gh-user>/nixpkgs into /tmp with timestamp
  - update drugclaw package hashes
  - build/verify
  - commit, push, and open PR to NixOS/nixpkgs:nixos-unstable

Options:
  --version <x.y.z>         Target drugclaw version (default: from Cargo.toml)
  --drugclaw-dir <path>    DrugClaw repo root (default: current repo root)
  --nixpkgs-dir <path>      Use an existing nixpkgs checkout instead of temp clone
  --fork-owner <owner>      GitHub owner of nixpkgs fork (default: current gh user)
  --branch <name>           Nixpkgs branch name (default: drugclaw-<version>-<timestamp>)
  --base <branch>           Upstream base branch (default: nixos-unstable)
  --draft                   Open PR as draft
  --no-push                 Do not push
  --no-pr                   Do not open PR
  -h, --help                Show help

Example:
  scripts/update-nixpkgs.sh
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

extract_hash_from_log() {
  local log_file="$1"
  grep -Eo 'got:[[:space:]]+sha256-[A-Za-z0-9+/=]+' "$log_file" | tail -n1 | awk '{print $2}'
}

set_package_fields() {
  local package_file="$1"
  local version="$2"
  local src_hash="$3"
  local cargo_hash="$4"
  perl -0777 -i -pe '
    s/version = "[^"]+";/version = "'"$version"'";/;
    s/hash = (?:lib\.fakeHash|"[^"]+");/hash = '"$src_hash"';/;
    s/cargoHash = (?:lib\.fakeHash|"[^"]+");/cargoHash = '"$cargo_hash"';/;
  ' "$package_file"
}

run_nix_build() {
  local log_file="$1"
  set +e
  nix-build -A drugclaw >"$log_file" 2>&1
  local status=$?
  set -e
  return "$status"
}

TIMESTAMP="$(date +%Y%m%d%H%M%S)"
DRUGCLAW_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=""
BASE_BRANCH="nixos-unstable"
FORK_OWNER=""
NIXPKGS_DIR=""
BRANCH=""
DO_PUSH=true
DO_PR=true
DO_DRAFT=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --drugclaw-dir) DRUGCLAW_DIR="$2"; shift 2 ;;
    --nixpkgs-dir) NIXPKGS_DIR="$2"; shift 2 ;;
    --fork-owner) FORK_OWNER="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --base) BASE_BRANCH="$2"; shift 2 ;;
    --draft) DO_DRAFT=true; shift ;;
    --no-push) DO_PUSH=false; shift ;;
    --no-pr) DO_PR=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_cmd git
require_cmd perl
require_cmd nix-build
require_cmd gh

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run: gh auth login" >&2
  exit 1
fi

if [ -z "$VERSION" ]; then
  VERSION="$(grep '^version = "' "$DRUGCLAW_DIR/Cargo.toml" | head -n1 | sed -E 's/version = "([^"]+)"/\1/')"
fi
if [ -z "$VERSION" ]; then
  echo "Failed to detect version from Cargo.toml. Pass --version explicitly." >&2
  exit 1
fi

if [ -z "$FORK_OWNER" ]; then
  FORK_OWNER="$(gh api user --jq .login)"
fi

if [ -z "$NIXPKGS_DIR" ]; then
  NIXPKGS_DIR="/tmp/nixpkgs-${TIMESTAMP}"
  echo "Using temp nixpkgs dir: $NIXPKGS_DIR"
  if ! gh repo view "${FORK_OWNER}/nixpkgs" >/dev/null 2>&1; then
    echo "Fork ${FORK_OWNER}/nixpkgs not found, creating fork..."
    gh repo fork NixOS/nixpkgs --remote=false
  fi
  gh repo clone "${FORK_OWNER}/nixpkgs" "$NIXPKGS_DIR"
fi

if [ -z "$BRANCH" ]; then
  BRANCH="drugclaw-${VERSION}-${TIMESTAMP}"
fi

cd "$NIXPKGS_DIR"
if ! git remote get-url upstream >/dev/null 2>&1; then
  git remote add upstream https://github.com/NixOS/nixpkgs.git
fi

git fetch upstream "$BASE_BRANCH"
git checkout -B "$BRANCH" "upstream/$BASE_BRANCH"

PACKAGE_FILE="$NIXPKGS_DIR/pkgs/by-name/mi/drugclaw/package.nix"
if [ ! -f "$PACKAGE_FILE" ]; then
  echo "Package file not found: $PACKAGE_FILE" >&2
  exit 1
fi

OLD_VERSION="$(grep 'version = "' "$PACKAGE_FILE" | head -n1 | sed -E 's/.*"([^"]+)".*/\1/')"
SRC_HASH=""
CARGO_HASH=""
echo "Updating drugclaw package: ${OLD_VERSION} -> ${VERSION}"

set_package_fields "$PACKAGE_FILE" "$VERSION" "lib.fakeHash" "lib.fakeHash"

LOG1="$(mktemp)"
LOG2="$(mktemp)"
LOG3="$(mktemp)"
PR_BODY="$(mktemp)"
trap 'rm -f "$LOG1" "$LOG2" "$LOG3" "$PR_BODY"' EXIT

if run_nix_build "$LOG1"; then
  SRC_HASH="$(grep 'hash = ' "$PACKAGE_FILE" | head -n1 | sed -E 's/.*"(sha256-[^"]+)".*/\1/')"
else
  SRC_HASH="$(extract_hash_from_log "$LOG1")"
  if [ -z "$SRC_HASH" ]; then
    echo "Failed to extract src hash from build log." >&2
    tail -n 120 "$LOG1" >&2
    exit 1
  fi
  echo "Resolved src hash: $SRC_HASH"
  set_package_fields "$PACKAGE_FILE" "$VERSION" "\"$SRC_HASH\"" "lib.fakeHash"
fi

if run_nix_build "$LOG2"; then
  CARGO_HASH="$(grep 'cargoHash = ' "$PACKAGE_FILE" | head -n1 | sed -E 's/.*"(sha256-[^"]+)".*/\1/')"
else
  CARGO_HASH="$(extract_hash_from_log "$LOG2")"
  if [ -z "$CARGO_HASH" ]; then
    echo "Failed to extract cargoHash from build log." >&2
    tail -n 120 "$LOG2" >&2
    exit 1
  fi
  echo "Resolved cargoHash: $CARGO_HASH"
  set_package_fields "$PACKAGE_FILE" "$VERSION" "\"$SRC_HASH\"" "\"$CARGO_HASH\""
fi

if ! run_nix_build "$LOG3"; then
  echo "Final nix-build failed." >&2
  tail -n 200 "$LOG3" >&2
  exit 1
fi

BUILD_PATH="$(tail -n1 "$LOG3" | tr -d '\r')"
if [ -x "$BUILD_PATH/bin/drugclaw" ]; then
  "$BUILD_PATH/bin/drugclaw" --help >/dev/null
fi

git add "$PACKAGE_FILE"
if git diff --cached --quiet; then
  echo "No changes detected after update."
  echo "nixpkgs dir: $NIXPKGS_DIR"
  exit 0
fi

git commit -m "drugclaw: ${OLD_VERSION} -> ${VERSION}"
echo "Committed on branch: $BRANCH"

if $DO_PUSH; then
  git push -u origin "$BRANCH"
  echo "Pushed: origin/$BRANCH"
else
  echo "Skip push due to --no-push"
fi

if $DO_PR; then
  if ! $DO_PUSH; then
    echo "--no-push is set, cannot open PR automatically." >&2
    exit 1
  fi
  cat > "$PR_BODY" <<EOF
## Summary
- drugclaw: ${OLD_VERSION} -> ${VERSION}

## Build / test
- nix-build -A drugclaw
- result/bin/drugclaw --help

## Upstream release
- https://github.com/DrugClaw/DrugClaw/releases/tag/v${VERSION}
EOF
  if $DO_DRAFT; then
    gh pr create \
      --repo NixOS/nixpkgs \
      --base "$BASE_BRANCH" \
      --head "${FORK_OWNER}:${BRANCH}" \
      --title "drugclaw: ${OLD_VERSION} -> ${VERSION}" \
      --body-file "$PR_BODY" \
      --draft
  else
    gh pr create \
      --repo NixOS/nixpkgs \
      --base "$BASE_BRANCH" \
      --head "${FORK_OWNER}:${BRANCH}" \
      --title "drugclaw: ${OLD_VERSION} -> ${VERSION}" \
      --body-file "$PR_BODY"
  fi
else
  echo "Skip PR due to --no-pr"
fi

echo "Done. nixpkgs dir: $NIXPKGS_DIR"
