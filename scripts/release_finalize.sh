#!/usr/bin/env bash
set -euo pipefail

# Finalize a DrugClaw release: wait for CI, tag, publish GitHub release, and update Homebrew tap.

usage() {
  cat <<'EOF'
Usage:
  scripts/release_finalize.sh --repo-dir <path> --tap-dir <path> --tap-repo <owner/repo> \
    --formula-path <path> --github-repo <owner/repo> --new-version <version> --tag <tag> \
    --asset <path>::<name>::<sha256>::<target>
EOF
}

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

wait_for_ci_success() {
  local github_repo="$1"
  local commit_sha="$2"
  local timeout_seconds="${CI_WAIT_TIMEOUT_SECONDS:-6000}"
  local interval_seconds="${CI_WAIT_INTERVAL_SECONDS:-20}"
  local elapsed=0
  local required_jobs_json="${REQUIRED_CI_JOBS_JSON:-}"
  if [ -z "$required_jobs_json" ]; then
    required_jobs_json='["Web Build","Rust (ubuntu-latest)","Rust (macos-latest)","Stability Smoke"]'
  fi
  local required_job_count

  required_job_count="$(jq -r 'length' <<<"$required_jobs_json")"

  echo "Waiting for required CI jobs on commit: $commit_sha"
  while [ "$elapsed" -lt "$timeout_seconds" ]; do
    local run_id
    run_id="$(
      gh run list \
        --repo "$github_repo" \
        --workflow "CI" \
        --commit "$commit_sha" \
        --json databaseId,status,createdAt \
        --jq 'sort_by(.createdAt) | reverse | .[0].databaseId'
    )"

    if [ -z "$run_id" ] || [ "$run_id" = "null" ]; then
      echo "CI run not found yet for commit $commit_sha."
      sleep "$interval_seconds"
      elapsed=$((elapsed + interval_seconds))
      continue
    fi

    local jobs_json
    jobs_json="$(
      gh run view "$run_id" \
        --repo "$github_repo" \
        --json jobs
    )"

    local failed_job
    failed_job="$(
      jq -r --argjson required "$required_jobs_json" '
        .jobs
        | map(select(.name as $name | $required | index($name)))
        | map(select(.conclusion == "failure"
                  or .conclusion == "cancelled"
                  or .conclusion == "timed_out"
                  or .conclusion == "action_required"
                  or .conclusion == "startup_failure"
                  or .conclusion == "stale"))
        | first
        | if . == null then empty else "\(.name) \(.url)" end
      ' <<<"$jobs_json"
    )"

    if [ -n "$failed_job" ]; then
      echo "Required CI job failed for commit $commit_sha: $failed_job" >&2
      return 1
    fi

    local completed_required_count
    completed_required_count="$(
      jq -r --argjson required "$required_jobs_json" '
        .jobs
        | map(select(.name as $name | $required | index($name)))
        | map(select(.conclusion == "success"))
        | length
      ' <<<"$jobs_json"
    )"

    if [ "$completed_required_count" -eq "$required_job_count" ]; then
      echo "Required CI jobs succeeded. Run id: $run_id"
      return 0
    fi

    echo "CI not successful yet. Slept ${elapsed}s/${timeout_seconds}s."
    sleep "$interval_seconds"
    elapsed=$((elapsed + interval_seconds))
  done

  echo "Timed out waiting for required CI jobs after ${timeout_seconds}s." >&2
  return 1
}

previous_release_tag() {
  local current_tag="$1"
  git tag --list 'v*' --sort=-version:refname | awk -v current="$current_tag" '$0 != current { print; exit }'
}

write_generated_release_notes() {
  local repo="$1"
  local tag="$2"
  local previous_tag="$3"
  local notes_file="$4"
  local args=(
    gh api -X POST "repos/$repo/releases/generate-notes"
    -f "tag_name=$tag"
  )

  if [ -n "$previous_tag" ]; then
    args+=(-f "previous_tag_name=$previous_tag")
  fi

  "${args[@]}" --jq '.body' > "$notes_file"
}

REPO_DIR=""
TAP_DIR=""
TAP_REPO=""
FORMULA_PATH=""
GITHUB_REPO=""
NEW_VERSION=""
TAG=""
ASSET_SPECS=()
TARBALL_PATH=""
TARBALL_NAME=""
SHA256=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo-dir) REPO_DIR="$2"; shift 2 ;;
    --tap-dir) TAP_DIR="$2"; shift 2 ;;
    --tap-repo) TAP_REPO="$2"; shift 2 ;;
    --formula-path) FORMULA_PATH="$2"; shift 2 ;;
    --github-repo) GITHUB_REPO="$2"; shift 2 ;;
    --new-version) NEW_VERSION="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --asset) ASSET_SPECS+=("$2"); shift 2 ;;
    --tarball-path) TARBALL_PATH="$2"; shift 2 ;;
    --tarball-name) TARBALL_NAME="$2"; shift 2 ;;
    --sha256) SHA256="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

for required in REPO_DIR TAP_DIR TAP_REPO FORMULA_PATH GITHUB_REPO NEW_VERSION TAG; do
  if [ -z "${!required}" ]; then
    echo "Missing required argument: $required" >&2
    usage >&2
    exit 1
  fi
done

if [ "${#ASSET_SPECS[@]}" -eq 0 ]; then
  if [ -n "$TARBALL_PATH" ] && [ -n "$TARBALL_NAME" ] && [ -n "$SHA256" ]; then
    case "$TARBALL_NAME" in
      *aarch64-apple-darwin.tar.gz) ASSET_SPECS+=("$TARBALL_PATH::$TARBALL_NAME::$SHA256::aarch64-apple-darwin") ;;
      *x86_64-apple-darwin.tar.gz) ASSET_SPECS+=("$TARBALL_PATH::$TARBALL_NAME::$SHA256::x86_64-apple-darwin") ;;
      *)
        echo "Cannot infer target from tarball name: $TARBALL_NAME" >&2
        exit 1
        ;;
    esac
  else
    echo "Provide at least one --asset argument." >&2
    usage >&2
    exit 1
  fi
fi

asset_field() {
  local spec="$1"
  local index="$2"
  awk -F'::' -v idx="$index" '{ print $idx }' <<< "$spec"
}

asset_url_for_name() {
  local name="$1"
  echo "https://github.com/$GITHUB_REPO/releases/download/$TAG/$name"
}

declare -A ASSET_PATH_BY_TARGET=()
declare -A ASSET_NAME_BY_TARGET=()
declare -A ASSET_SHA_BY_TARGET=()
ASSET_UPLOAD_PATHS=()

for spec in "${ASSET_SPECS[@]}"; do
  path="$(asset_field "$spec" 1)"
  name="$(asset_field "$spec" 2)"
  sha="$(asset_field "$spec" 3)"
  target="$(asset_field "$spec" 4)"

  if [ -z "$path" ] || [ -z "$name" ] || [ -z "$sha" ] || [ -z "$target" ]; then
    echo "Invalid --asset spec: $spec" >&2
    exit 1
  fi
  if [ ! -f "$path" ]; then
    echo "Asset file not found: $path" >&2
    exit 1
  fi

  case "$target" in
    aarch64-apple-darwin|x86_64-apple-darwin) ;;
    *)
      echo "Unsupported asset target: $target" >&2
      exit 1
      ;;
  esac

  ASSET_PATH_BY_TARGET["$target"]="$path"
  ASSET_NAME_BY_TARGET["$target"]="$name"
  ASSET_SHA_BY_TARGET["$target"]="$sha"
  ASSET_UPLOAD_PATHS+=("$path")
done

for mac_target in aarch64-apple-darwin x86_64-apple-darwin; do
  if [ -z "${ASSET_PATH_BY_TARGET[$mac_target]:-}" ]; then
    echo "Missing required macOS asset for target: $mac_target" >&2
    exit 1
  fi
done

require_cmd gh
require_cmd git
require_cmd jq
require_cmd shasum

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI not authenticated. Run: gh auth login" >&2
  exit 1
fi

cd "$REPO_DIR"

RELEASE_COMMIT_SHA="$(git rev-parse HEAD)"
if ! wait_for_ci_success "$GITHUB_REPO" "$RELEASE_COMMIT_SHA"; then
  exit 1
fi

if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "Tag already exists on origin: $TAG"
else
  if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "Tag already exists locally: $TAG"
  else
    git tag "$TAG" "$RELEASE_COMMIT_SHA"
    echo "Created local tag: $TAG -> $RELEASE_COMMIT_SHA"
  fi
  git push origin "refs/tags/$TAG"
  echo "Pushed tag: $TAG"
fi

PREV_TAG="$(previous_release_tag "$TAG")"
if [ -n "$PREV_TAG" ]; then
  echo "Generating release notes from range: $PREV_TAG..$TAG"
else
  echo "Generating release notes without a previous tag (first release or missing tags)"
fi
RELEASE_NOTES_FILE="$(mktemp)"
trap 'rm -f "$RELEASE_NOTES_FILE"' EXIT
write_generated_release_notes "$GITHUB_REPO" "$TAG" "$PREV_TAG" "$RELEASE_NOTES_FILE"

if gh release view "$TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
  echo "Release $TAG exists. Updating notes and uploading/overwriting assets."
  gh release edit "$TAG" \
    --repo "$GITHUB_REPO" \
    -t "$TAG" \
    --notes-file "$RELEASE_NOTES_FILE"
  gh release upload "$TAG" "${ASSET_UPLOAD_PATHS[@]}" --repo "$GITHUB_REPO" --clobber
else
  echo "Release $TAG does not exist. Creating release with generated notes and uploading assets."
  gh release create "$TAG" "${ASSET_UPLOAD_PATHS[@]}" \
    --repo "$GITHUB_REPO" \
    -t "$TAG" \
    --notes-file "$RELEASE_NOTES_FILE"
fi

echo "Resetting tap workspace: $TAP_DIR"
rm -rf "$TAP_DIR"
mkdir -p "$(dirname "$TAP_DIR")"
echo "Cloning tap repo..."
git clone "https://github.com/$TAP_REPO.git" "$TAP_DIR"

cd "$TAP_DIR"
mkdir -p Formula

cat > "$FORMULA_PATH" << RUBY
class Drugclaw < Formula
  desc "AI research assistant for accelerated drug discovery"
  homepage "https://github.com/$GITHUB_REPO"
  license "Apache-2.0"

  if OS.mac? && Hardware::CPU.arm?
    url "$(asset_url_for_name "${ASSET_NAME_BY_TARGET[aarch64-apple-darwin]}")"
    sha256 "${ASSET_SHA_BY_TARGET[aarch64-apple-darwin]}"
  elsif OS.mac? && Hardware::CPU.intel?
    url "$(asset_url_for_name "${ASSET_NAME_BY_TARGET[x86_64-apple-darwin]}")"
    sha256 "${ASSET_SHA_BY_TARGET[x86_64-apple-darwin]}"
  else
    raise "DrugClaw Homebrew bottles are published for macOS only. Use install.sh on Linux."
  end

  def install
    bin.install "drugclaw"
  end

  test do
    assert_match "DrugClaw", shell_output("#{bin}/drugclaw help")
  end
end
RUBY

git add "$FORMULA_PATH"
git commit -m "drugclaw homebrew release $NEW_VERSION"
sync_rebase_and_push origin

echo ""
echo "Done! Released $TAG and updated Homebrew tap."
echo ""
echo "Users can install with:"
echo "  brew tap drugclaw/tap"
echo "  brew install drugclaw"
