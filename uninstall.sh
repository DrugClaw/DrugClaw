#!/usr/bin/env bash
set -euo pipefail

# Remove a local DrugClaw runtime binary installation.

BIN_NAME="drugclaw"

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
Usage: uninstall.sh

Environment:
  DRUGCLAW_INSTALL_DIR / MICROCLAW_INSTALL_DIR

Notes:
  - `DRUGCLAW_*` is the preferred script interface.
  - Legacy `MICROCLAW_*` env vars remain accepted for compatibility.
EOF_HELP
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

resolve_targets() {
  local override
  override="$(env_alias DRUGCLAW_INSTALL_DIR MICROCLAW_INSTALL_DIR "")"

  if [ -n "$override" ]; then
    printf '%s\n' "${override%/}/$BIN_NAME"
  fi

  if need_cmd "$BIN_NAME"; then
    command -v "$BIN_NAME"
  fi

  printf '%s\n' "/usr/local/bin/$BIN_NAME"
  printf '%s\n' "$HOME/.local/bin/$BIN_NAME"
}

unique_targets() {
  local seen="|"
  local path
  while IFS= read -r path; do
    if [ -n "$path" ] && [[ "$seen" != *"|$path|"* ]]; then
      printf '%s\n' "$path"
      seen+="$path|"
    fi
  done
}

remove_file() {
  local target="$1"
  if [ ! -e "$target" ]; then
    return 1
  fi

  if [ -w "$target" ] || [ -w "$(dirname "$target")" ]; then
    rm -f "$target"
  else
    if need_cmd sudo; then
      sudo rm -f "$target"
    else
      err "No permission to remove $target and sudo is unavailable"
      return 2
    fi
  fi

  return 0
}

main() {
  local os removed=0 failed=0 target rc

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    print_help
    exit 0
  fi

  os="$(detect_os)"
  log "Uninstalling $BIN_NAME on $os..."

  while IFS= read -r target; do
    if [ -z "$target" ]; then
      continue
    fi
    if remove_file "$target"; then
      log "Removed: $target"
      removed=$((removed + 1))
    else
      rc=$?
      if [ "$rc" -eq 2 ]; then
        failed=1
      fi
    fi
  done < <(resolve_targets | unique_targets)

  if [ "$failed" -ne 0 ]; then
    exit 1
  fi

  if [ "$removed" -eq 0 ]; then
    log "$BIN_NAME binary not found. Nothing to uninstall."
    exit 0
  fi

  log ""
  log "$BIN_NAME has been removed."
  log "Optional cleanup (not removed automatically):"
  log "  rm -rf ~/.drugclaw/runtime"
  log "  rm -f ./drugclaw.config.yaml ./drugclaw.config.yml"
}

main "$@"
