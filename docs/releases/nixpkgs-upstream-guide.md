# Nixpkgs Upstream Guide

Last reviewed: 2026-03-09

This guide covers how to upstream `drugclaw` to `NixOS/nixpkgs` so users get cache-backed prebuilt binaries from official Nix infrastructure.

## Goal

- Package `drugclaw` in `nixpkgs`
- Keep updates low-friction on each release
- Ensure Linux + Darwin builds stay healthy

## One-time Upstreaming

1. Fork `NixOS/nixpkgs` and clone locally.
2. Create package file:
   - `pkgs/by-name/mi/drugclaw/package.nix`
3. Add entry in:
   - `pkgs/top-level/all-packages.nix`
4. Use this baseline expression:

```nix
{
  lib,
  rustPlatform,
  fetchFromGitHub,
  stdenv,
  pkg-config,
  openssl,
  sqlite,
  libsodium,
  udev,
}:

rustPlatform.buildRustPackage rec {
  pname = "drugclaw";
  version = "0.0.163";

  src = fetchFromGitHub {
    owner = "drugclaw";
    repo = "drugclaw";
    rev = "v${version}";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };

  cargoHash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";

  nativeBuildInputs = [ pkg-config ];

  buildInputs =
    [
      openssl
      sqlite
      libsodium
    ]
    ++ lib.optionals stdenv.hostPlatform.isLinux [ udev ];

  buildFeatures = lib.optionals stdenv.hostPlatform.isLinux [ "journald" "sqlite-vec" ];

  doCheck = false;

  meta = with lib; {
    description = "Multi-channel agent runtime for Telegram, Discord, Slack, and Web";
    homepage = "https://github.com/DrugClaw/DrugClaw";
    changelog = "https://github.com/DrugClaw/DrugClaw/releases/tag/v${version}";
    license = licenses.asl20;
    mainProgram = "drugclaw";
    platforms = platforms.linux ++ platforms.darwin;
    maintainers = with maintainers; [ ];
  };
}
```

Note: replace the placeholder `hash` and `cargoHash` with real values from build output.

## Hash Update Workflow

When new release `vX.Y.Z` is out:

1. Bump `version` and `src.rev`.
2. Temporarily set:
   - `hash = lib.fakeHash;`
   - `cargoHash = lib.fakeHash;`
3. Run build:

```sh
nix build .#drugclaw
```

4. Copy the "got: sha256-..." values from the error output into `hash` and `cargoHash`.
5. Rebuild until it succeeds.

Automated path from the DrugClaw repo:

```sh
scripts/update-nixpkgs.sh
```
## Validation Before Opening Nixpkgs PR

- Build on Linux and Darwin (`x86_64-linux`, `aarch64-darwin` at minimum).
- Verify executable:

```sh
result/bin/drugclaw --help
```

- Confirm no Linux-only deps are used unguarded on Darwin (`udev`, `journald`).

## Ongoing Maintenance Policy

- Keep `flake.nix` package version aligned with `Cargo.toml`.
- On each DrugClaw release, open/update a nixpkgs bump PR within 24h.
- If upstream crate graph changes break nixpkgs, keep `flake` build green first, then patch nixpkgs expression.

## Recommended PR Metadata

- Title: `drugclaw: init at <version>` (first) / `drugclaw: <old> -> <new>` (bump)
- Include:
  - release notes link
  - local build logs for Linux/Darwin
  - short risk note if feature flags changed
