#!/usr/bin/env bash
set -euo pipefail

# Install DrugClaw, the AI Research Assistant for Accelerated Drug Discovery.

env_alias() {
  local primary="$1"
  local legacy="$2"
  local fallback="${3:-}"
  local value="${!primary:-}"
  if [ -n "$value" ]; then
    printf '%s' "$value"
    return 0
  fi
  value="${!legacy:-}"
  if [ -n "$value" ]; then
    printf '%s' "$value"
    return 0
  fi
  printf '%s' "$fallback"
}

REPO="$(env_alias DRUGCLAW_REPO MICROCLAW_REPO 'DrugClaw/DrugClaw')"
BIN_NAME="drugclaw"
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
SKIP_RUN="$(env_alias DRUGCLAW_INSTALL_SKIP_RUN MICROCLAW_INSTALL_SKIP_RUN '0')"
SKIP_SANDBOX_BUILD="$(env_alias DRUGCLAW_INSTALL_SKIP_SANDBOX_BUILD MICROCLAW_INSTALL_SKIP_SANDBOX_BUILD '0')"
DEFAULT_SANDBOX_IMAGE="drugclaw-drug-sandbox:latest"
DOCKING_COMPAT_IMAGE="drugclaw-drug-sandbox-docking:latest"

log() {
  printf '%s\n' "$*"
}

err() {
  printf 'Error: %s\n' "$*" >&2
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

print_help() {
  cat <<'EOF_HELP'
Usage: install.sh [--skip-run]

Options:
  --skip-run   Do not auto-run DrugClaw after install.
  --skip-sandbox-build
               Do not auto-build the default science sandbox image.
  -h, --help   Show help.

Environment:
  DRUGCLAW_REPO / MICROCLAW_REPO
  DRUGCLAW_INSTALL_DIR / MICROCLAW_INSTALL_DIR
  DRUGCLAW_INSTALL_SKIP_RUN / MICROCLAW_INSTALL_SKIP_RUN
  DRUGCLAW_INSTALL_SKIP_SANDBOX_BUILD / MICROCLAW_INSTALL_SKIP_SANDBOX_BUILD

Notes:
  - `DRUGCLAW_*` is the preferred script interface.
  - Legacy `MICROCLAW_*` env vars remain accepted for compatibility.
  - This installer prefers prebuilt release assets and falls back to `cargo install`
    when the latest release does not include your platform and Cargo is available.
  - When Docker is installed and the daemon is reachable, this installer also
    attempts to build the default unified science+docking sandbox image:
    `drugclaw-drug-sandbox:latest`.
EOF_HELP
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --skip-run)
        SKIP_RUN=1
        ;;
      --skip-sandbox-build)
        SKIP_SANDBOX_BUILD=1
        ;;
      -h|--help)
        print_help
        exit 0
        ;;
      *)
        err "Unknown argument: $1"
        print_help >&2
        exit 1
        ;;
    esac
    shift
  done
}

should_skip_run() {
  local normalized
  normalized="$(printf '%s' "$SKIP_RUN" | tr '[:upper:]' '[:lower:]')"
  case "$normalized" in
    1|true|yes)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

should_skip_sandbox_build() {
  local normalized
  normalized="$(printf '%s' "$SKIP_SANDBOX_BUILD" | tr '[:upper:]' '[:lower:]')"
  case "$normalized" in
    1|true|yes)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

detect_os() {
  case "$(uname -s)" in
    Darwin) echo "darwin" ;;
    Linux) echo "linux" ;;
    *)
      err "Unsupported OS: $(uname -s)"
      exit 1
      ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "x86_64" ;;
    arm64|aarch64) echo "aarch64" ;;
    *)
      err "Unsupported architecture: $(uname -m)"
      exit 1
      ;;
  esac
}

install_dir_override() {
  env_alias DRUGCLAW_INSTALL_DIR MICROCLAW_INSTALL_DIR ""
}

detect_install_dir() {
  local override
  override="$(install_dir_override)"
  if [ -n "$override" ]; then
    echo "$override"
    return
  fi
  if [ -w "/usr/local/bin" ]; then
    echo "/usr/local/bin"
    return
  fi
  if [ -d "$HOME/.local/bin" ] || mkdir -p "$HOME/.local/bin" 2>/dev/null; then
    echo "$HOME/.local/bin"
    return
  fi
  echo "/usr/local/bin"
}

download_release_json() {
  if need_cmd curl; then
    curl -fsSL "$API_URL"
  elif need_cmd wget; then
    wget -qO- "$API_URL"
  else
    err "Neither curl nor wget is available"
    exit 1
  fi
}

extract_release_tag() {
  local release_json="$1"
  printf '%s' "$release_json" \
    | tr '\n' ' ' \
    | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

extract_asset_url() {
  local release_json="$1"
  local os="$2"
  local arch="$3"
  local os_regex arch_regex

  case "$os" in
    darwin) os_regex="apple-darwin|darwin" ;;
    linux) os_regex="linux-gnu|linux-musl|linux" ;;
    *)
      err "Unsupported OS for release matching: $os"
      return 1
      ;;
  esac

  case "$arch" in
    x86_64) arch_regex="x86_64|amd64" ;;
    aarch64) arch_regex="aarch64|arm64" ;;
    *)
      err "Unsupported architecture for release matching: $arch"
      return 1
      ;;
  esac

  printf '%s\n' "$release_json" \
    | grep -Eo 'https://[^"]+' \
    | grep '/releases/download/' \
    | grep -E "/${BIN_NAME}-[0-9]+\.[0-9]+\.[0-9]+-.*(apple-darwin|linux-gnu|linux-musl|windows-msvc)\.(tar\.gz|zip)$" \
    | grep -Ei "(${arch_regex}).*(${os_regex})|(${os_regex}).*(${arch_regex})" \
    | head -n1
}

download_file() {
  local url="$1"
  local output="$2"
  if need_cmd curl; then
    curl -fL "$url" -o "$output"
  else
    wget -O "$output" "$url"
  fi
}

docker_ready() {
  need_cmd docker && docker info >/dev/null 2>&1
}

source_archive_url() {
  local tag="$1"
  printf 'https://github.com/%s/archive/refs/tags/%s.tar.gz' "$REPO" "$tag"
}

extract_source_context() {
  local archive="$1"
  local tmpdir="$2"
  local srcdir="$tmpdir/source-context"

  mkdir -p "$srcdir"
  tar -xzf "$archive" -C "$srcdir"
  find "$srcdir" -mindepth 1 -maxdepth 1 -type d | head -n1
}

ensure_docking_compat_alias() {
  if ! docker image inspect "$DEFAULT_SANDBOX_IMAGE" >/dev/null 2>&1; then
    return 0
  fi

  if docker image inspect "$DOCKING_COMPAT_IMAGE" >/dev/null 2>&1; then
    return 0
  fi

  if docker tag "$DEFAULT_SANDBOX_IMAGE" "$DOCKING_COMPAT_IMAGE" >/dev/null 2>&1; then
    log "Tagged compatibility alias: $DOCKING_COMPAT_IMAGE"
  fi
}

ensure_default_sandbox_image() {
  local release_tag="$1"
  local tmpdir="$2"
  local archive source_url source_dir

  if should_skip_sandbox_build; then
    log "Skipping sandbox image build (--skip-sandbox-build)."
    return 0
  fi

  if ! need_cmd docker; then
    log "Docker CLI not found. Skipping default sandbox image build."
    return 0
  fi

  if ! docker_ready; then
    log "Docker is installed but the daemon is unavailable. Skipping default sandbox image build."
    return 0
  fi

  if docker image inspect "$DEFAULT_SANDBOX_IMAGE" >/dev/null 2>&1; then
    log "Default sandbox image already available: $DEFAULT_SANDBOX_IMAGE"
    ensure_docking_compat_alias
    return 0
  fi

  if [ -z "$release_tag" ]; then
    err "Could not determine latest release tag; skipping default sandbox image build."
    return 0
  fi

  source_url="$(source_archive_url "$release_tag")"
  archive="$tmpdir/${BIN_NAME}-${release_tag}-source.tar.gz"

  log "Docker detected. Building default unified sandbox image: $DEFAULT_SANDBOX_IMAGE"
  log "Downloading source context: $source_url"
  if ! download_file "$source_url" "$archive"; then
    err "Failed to download source archive for sandbox image build."
    return 0
  fi

  source_dir="$(extract_source_context "$archive" "$tmpdir")"
  if [ -z "$source_dir" ] || [ ! -f "$source_dir/docker/drug-sandbox.Dockerfile" ]; then
    err "Source archive did not contain docker/drug-sandbox.Dockerfile; skipping sandbox image build."
    return 0
  fi

  if ! docker build -f "$source_dir/docker/drug-sandbox.Dockerfile" -t "$DEFAULT_SANDBOX_IMAGE" "$source_dir"; then
    err "Failed to build $DEFAULT_SANDBOX_IMAGE. Retry manually with:"
    err "  docker build -f docker/drug-sandbox.Dockerfile -t $DEFAULT_SANDBOX_IMAGE ."
    return 0
  fi

  log "Built default sandbox image: $DEFAULT_SANDBOX_IMAGE"
  ensure_docking_compat_alias
}

copy_binary_to_install_dir() {
  local bin_path="$1"
  local install_dir="$2"

  chmod +x "$bin_path"
  if [ -w "$install_dir" ]; then
    cp "$bin_path" "$install_dir/$BIN_NAME"
  else
    if need_cmd sudo; then
      sudo cp "$bin_path" "$install_dir/$BIN_NAME"
    else
      err "No write permission for $install_dir and sudo not available"
      return 1
    fi
  fi
}

install_from_archive() {
  local archive="$1"
  local install_dir="$2"
  local tmpdir="$3"
  local extracted=0

  case "$archive" in
    *.tar.gz|*.tgz)
      tar -xzf "$archive" -C "$tmpdir"
      extracted=1
      ;;
    *.zip)
      if ! need_cmd unzip; then
        err "unzip is required to extract zip archives"
        return 1
      fi
      unzip -q "$archive" -d "$tmpdir"
      extracted=1
      ;;
  esac

  if [ "$extracted" -eq 0 ]; then
    if tar -tzf "$archive" >/dev/null 2>&1; then
      tar -xzf "$archive" -C "$tmpdir"
      extracted=1
    elif need_cmd unzip && unzip -tq "$archive" >/dev/null 2>&1; then
      unzip -q "$archive" -d "$tmpdir"
      extracted=1
    fi
  fi

  if [ "$extracted" -eq 0 ]; then
    err "Unknown archive format: $archive"
    return 1
  fi

  local bin_path
  bin_path="$(find "$tmpdir" -type f -name "$BIN_NAME" | head -n1)"
  if [ -z "$bin_path" ]; then
    err "Could not find '$BIN_NAME' in archive"
    return 1
  fi

  copy_binary_to_install_dir "$bin_path" "$install_dir"
}

install_from_source_tag() {
  local tag="$1"
  local install_dir="$2"
  local tmpdir="$3"
  local cargo_root="$tmpdir/cargo-root"
  local repo_url="https://github.com/${REPO}.git"
  local bin_path

  if ! need_cmd cargo; then
    err "Cargo is required for source fallback but is not available"
    return 1
  fi

  log "Falling back to cargo install from ${repo_url} at ${tag}"
  cargo install \
    --git "$repo_url" \
    --tag "$tag" \
    --locked \
    --root "$cargo_root" \
    --bin "$BIN_NAME"

  bin_path="$cargo_root/bin/$BIN_NAME"
  if [ ! -f "$bin_path" ]; then
    err "cargo install completed but '$BIN_NAME' was not found under $cargo_root/bin"
    return 1
  fi

  copy_binary_to_install_dir "$bin_path" "$install_dir"
}

main() {
  local os arch install_dir release_json asset_url release_tag tmpdir archive asset_filename had_existing_bin

  parse_args "$@"

  os="$(detect_os)"
  arch="$(detect_arch)"
  install_dir="$(detect_install_dir)"
  had_existing_bin=0
  if need_cmd "$BIN_NAME"; then
    had_existing_bin=1
  fi

  log "Installing ${BIN_NAME} for ${os}/${arch} from ${REPO}..."
  release_json="$(download_release_json)"
  release_tag="$(extract_release_tag "$release_json" || true)"
  asset_url="$(extract_asset_url "$release_json" "$os" "$arch" || true)"

  tmpdir="$(mktemp -d)"
  trap 'if [ -n "${tmpdir:-}" ]; then rm -rf "$tmpdir"; fi' EXIT
  if [ -n "$asset_url" ]; then
    asset_filename="${asset_url##*/}"
    asset_filename="${asset_filename%%\?*}"
    if [ -z "$asset_filename" ] || [ "$asset_filename" = "$asset_url" ]; then
      asset_filename="${BIN_NAME}.archive"
    fi
    archive="$tmpdir/$asset_filename"
    log "Downloading: $asset_url"
    download_file "$asset_url" "$archive"
    install_from_archive "$archive" "$install_dir" "$tmpdir"
  elif [ -n "$release_tag" ] && need_cmd cargo; then
    install_from_source_tag "$release_tag" "$install_dir" "$tmpdir"
  else
    err "No prebuilt binary found for ${os}/${arch} in the latest GitHub release."
    if [ -z "$release_tag" ]; then
      err "The latest release tag could not be determined for source fallback."
    elif ! need_cmd cargo; then
      err "Cargo is not installed, so source fallback is unavailable."
    fi
    err "Use another install path instead:"
    err "  Homebrew (macOS): brew tap drugclaw/tap && brew install drugclaw"
    err "  Build from source: https://github.com/${REPO}"
    exit 1
  fi

  log ""
  log "Installed ${BIN_NAME} to ${install_dir}/${BIN_NAME}."
  ensure_default_sandbox_image "$release_tag" "$tmpdir"
  if [ "$install_dir" = "$HOME/.local/bin" ]; then
    log "Ensure '$HOME/.local/bin' is in PATH."
    log "Example: export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi

  if should_skip_run; then
    log "Skipping auto-run (--skip-run)."
  elif [ "$had_existing_bin" -eq 1 ]; then
    log "Skipping auto-run (existing install detected)."
  elif need_cmd "$BIN_NAME"; then
    log "Running: ${BIN_NAME}"
    if ! "$BIN_NAME"; then
      err "Auto-run failed. Try running: ${BIN_NAME}"
    fi
  else
    log "Could not find '${BIN_NAME}' in PATH after install."
    log "Add this directory to PATH: ${install_dir}"
    log "Then run: ${install_dir}/${BIN_NAME}"
  fi
}

main "$@"
