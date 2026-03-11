#!/usr/bin/env bash
set -euo pipefail

# Build and publish the DrugClaw research assistant release plus Homebrew tap update.

usage() {
  cat <<'EOF'
Usage:
  scripts/release_homebrew.sh

Environment overrides:
  ROOT_DIR
  TAP_DIR
  TAP_REPO
  FORMULA_PATH
  GITHUB_REPO
  MACOS_TARGETS

  Notes:
    - This script bumps the patch version in Cargo.toml.
    - It must run on macOS and builds both Apple Silicon and Intel release binaries
      for the Homebrew formula before delegating publishing to scripts/release_finalize.sh.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
REPO_DIR="$ROOT_DIR"
TAP_DIR="${TAP_DIR:-$ROOT_DIR/tmp/homebrew-tap}"
TAP_REPO="${TAP_REPO:-drugclaw/homebrew-tap}"
FORMULA_PATH="${FORMULA_PATH:-Formula/drugclaw.rb}"
GITHUB_REPO="${GITHUB_REPO:-DrugClaw/DrugClaw}"
read -r -a MACOS_TARGETS <<< "${MACOS_TARGETS:-aarch64-apple-darwin x86_64-apple-darwin}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

current_branch() {
  local branch
  branch="$(git symbolic-ref --quiet --short HEAD || true)"
  if [ -z "$branch" ]; then
    echo "Detached HEAD is not supported for release push" >&2
    exit 1
  fi
  echo "$branch"
}

sync_rebase_and_push() {
  local remote="${1:-origin}"
  local branch
  branch="$(current_branch)"

  echo "Syncing $remote/$branch before push..."
  git fetch "$remote" "$branch"
  if git show-ref --verify --quiet "refs/remotes/$remote/$branch"; then
    git rebase "$remote/$branch"
  fi

  if git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
    git push "$remote" "$branch"
  else
    git push -u "$remote" "$branch"
  fi
}

require_macos_host() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "scripts/release_homebrew.sh must run on macOS so it can publish both macOS Homebrew assets." >&2
    exit 1
  fi
}

target_arch() {
  case "$1" in
    aarch64-apple-darwin) echo "aarch64" ;;
    x86_64-apple-darwin) echo "x86_64" ;;
    *)
      echo "Unsupported Homebrew release target: $1" >&2
      exit 1
      ;;
  esac
}

latest_release_tag() {
  git tag --list 'v*' --sort=-version:refname | head -n1
}

contains_digit_four() {
  [[ "$1" == *4* ]]
}

replace_root_version() {
  local file="$1"
  local old_version="$2"
  local new_version="$3"
  local tmp

  tmp="$(mktemp "${TMPDIR:-/tmp}/drugclaw-version.XXXXXX")"
  sed "s/^version = \"$old_version\"/version = \"$new_version\"/" "$file" > "$tmp"
  mv "$tmp" "$file"
}

require_cmd cargo
require_cmd git
require_cmd gh
require_cmd shasum
require_cmd tar
require_cmd npm
require_cmd rustup
require_macos_host

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI not authenticated. Run: gh auth login" >&2
  exit 1
fi

cd "$REPO_DIR"

# --- Build web assets (embedded via include_dir! in src/web.rs) ---
if [ -f "web/package.json" ]; then
  echo "Building web assets..."
  if [ -f "web/package-lock.json" ]; then
    npm --prefix web ci
  else
    npm --prefix web install
  fi
  npm --prefix web run build
  test -f "web/dist/index.html" || {
    echo "web/dist/index.html is missing after web build" >&2
    exit 1
  }
  test -f "web/dist/icon.png" || {
    echo "web/dist/icon.png is missing after web build" >&2
    exit 1
  }
  if ! ls web/dist/assets/*.js >/dev/null 2>&1; then
    echo "web/dist/assets/*.js is missing after web build" >&2
    exit 1
  fi
fi

# --- Bump patch version in Cargo.toml ---
PREV_TAG="$(latest_release_tag)"
CURRENT_VERSION=$(grep '^version' Cargo.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

NEW_MAJOR="$MAJOR"
NEW_MINOR="$MINOR"

while contains_digit_four "$NEW_MAJOR"; do
  NEW_MAJOR=$((NEW_MAJOR + 1))
  NEW_MINOR=0
  PATCH=0
done

while contains_digit_four "$NEW_MINOR"; do
  NEW_MINOR=$((NEW_MINOR + 1))
  PATCH=0
done

NEW_PATCH=$((PATCH + 1))
NEW_VERSION="$NEW_MAJOR.$NEW_MINOR.$NEW_PATCH"
while contains_digit_four "$NEW_VERSION"; do
  NEW_PATCH=$((NEW_PATCH + 1))
  NEW_VERSION="$NEW_MAJOR.$NEW_MINOR.$NEW_PATCH"
done
TAG="v$NEW_VERSION"

if [ "$PREV_TAG" = "$TAG" ]; then
  PREV_TAG="$(git tag --list 'v*' --sort=-version:refname | sed -n '2p')"
fi

replace_root_version Cargo.toml "$CURRENT_VERSION" "$NEW_VERSION"
echo "Version bumped: $CURRENT_VERSION -> $NEW_VERSION"
if [ -n "$PREV_TAG" ]; then
  echo "Previous tag: $PREV_TAG"
else
  echo "Previous tag: (none)"
fi

# --- Build release binaries ---
echo "Cleaning previous Rust build artifacts..."
cargo clean

echo "Ensuring Rust targets are installed..."
rustup target add "${MACOS_TARGETS[@]}"

ASSET_SPECS=()
for target in "${MACOS_TARGETS[@]}"; do
  arch="$(target_arch "$target")"
  tarball_name="drugclaw-$NEW_VERSION-${arch}-apple-darwin.tar.gz"
  tarball_path="target/release/$tarball_name"
  binary="target/$target/release/drugclaw"

  echo "Building release binary for $target..."
  cargo build --release --target "$target"

  if [ ! -f "$binary" ]; then
    echo "Binary not found: $binary" >&2
    exit 1
  fi

  tar -czf "$tarball_path" -C "target/$target/release" drugclaw
  sha256="$(shasum -a 256 "$tarball_path" | awk '{print $1}')"
  echo "Created tarball: $tarball_path"
  echo "SHA256 ($target): $sha256"
  ASSET_SPECS+=("$tarball_path::$tarball_name::$sha256::$target")
done

# --- Git commit + push ---
git add Cargo.toml
git commit -m "bump version to $NEW_VERSION"
sync_rebase_and_push origin

echo "Release commit pushed: $(git rev-parse HEAD)"

# --- Finalize release (blocking) ---
finalize_args=(
  --repo-dir "$REPO_DIR"
  --tap-dir "$TAP_DIR"
  --tap-repo "$TAP_REPO"
  --formula-path "$FORMULA_PATH"
  --github-repo "$GITHUB_REPO"
  --new-version "$NEW_VERSION"
  --tag "$TAG"
)
for asset_spec in "${ASSET_SPECS[@]}"; do
  finalize_args+=(--asset "$asset_spec")
done

"$ROOT_DIR/scripts/release_finalize.sh" "${finalize_args[@]}"
