param(
  [string]$Repo,
  [string]$InstallDir,
  [switch]$SkipRun
)

$ErrorActionPreference = 'Stop'

function Get-EnvAlias {
  param(
    [string]$Primary,
    [string]$Legacy,
    [string]$Fallback = ''
  )

  $primaryValue = (Get-Item -Path "Env:$Primary" -ErrorAction SilentlyContinue).Value
  if ($primaryValue) {
    return $primaryValue
  }
  $legacyValue = (Get-Item -Path "Env:$Legacy" -ErrorAction SilentlyContinue).Value
  if ($legacyValue) {
    return $legacyValue
  }
  return $Fallback
}

if (-not $PSBoundParameters.ContainsKey('Repo') -or [string]::IsNullOrWhiteSpace($Repo)) {
  $Repo = Get-EnvAlias -Primary 'DRUGCLAW_REPO' -Legacy 'MICROCLAW_REPO' -Fallback 'DrugClaw/DrugClaw'
}

if (-not $PSBoundParameters.ContainsKey('InstallDir') -or [string]::IsNullOrWhiteSpace($InstallDir)) {
  $installFallback = if ($env:USERPROFILE) {
    Join-Path $env:USERPROFILE '.local\bin'
  } else {
    Join-Path (Get-Location) '.local\bin'
  }
  $InstallDir = Get-EnvAlias -Primary 'DRUGCLAW_INSTALL_DIR' -Legacy 'MICROCLAW_INSTALL_DIR' -Fallback $installFallback
}

$BinName = 'drugclaw.exe'
$ApiUrl = "https://api.github.com/repos/$Repo/releases/latest"
$skipRunFromEnv = $false
$skipRunEnv = Get-EnvAlias -Primary 'DRUGCLAW_INSTALL_SKIP_RUN' -Legacy 'MICROCLAW_INSTALL_SKIP_RUN'
if ($skipRunEnv) {
  $skipRunFromEnv = @('1', 'true', 'yes') -contains $skipRunEnv.Trim().ToLowerInvariant()
}
$skipRunEffective = $SkipRun.IsPresent -or $skipRunFromEnv
$hadExistingCommand = $null -ne (Get-Command drugclaw -ErrorAction SilentlyContinue)

function Write-Info([string]$msg) {
  Write-Host $msg
}

function Resolve-Arch {
  switch ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture) {
    'X64' { return 'x86_64' }
    'Arm64' { return 'aarch64' }
    default { throw "Unsupported architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)" }
  }
}

function Select-AssetUrl([object]$release, [string]$arch) {
  $patterns = @(
    "drugclaw-[0-9]+\.[0-9]+\.[0-9]+-$arch-windows-msvc\.zip$",
    "drugclaw-[0-9]+\.[0-9]+\.[0-9]+-.*$arch.*windows.*\.zip$"
  )

  foreach ($p in $patterns) {
    $match = $release.assets | Where-Object { $_.browser_download_url -match $p } | Select-Object -First 1
    if ($null -ne $match) {
      return $match.browser_download_url
    }
  }

  return $null
}

function Path-Contains([string]$pathValue, [string]$dir) {
  if ([string]::IsNullOrWhiteSpace($pathValue)) { return $false }
  $needle = $dir.Trim().TrimEnd('\').ToLowerInvariant()
  foreach ($part in $pathValue.Split(';')) {
    if ([string]::IsNullOrWhiteSpace($part)) { continue }
    if ($part.Trim().TrimEnd('\').ToLowerInvariant() -eq $needle) {
      return $true
    }
  }
  return $false
}

function Ensure-UserPathContains([string]$dir) {
  $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (Path-Contains $userPath $dir) {
    return $false
  }

  $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) {
    $dir
  } else {
    "$userPath;$dir"
  }

  [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')

  if (-not (Path-Contains $env:Path $dir)) {
    $env:Path = "$env:Path;$dir"
  }

  return $true
}

function Install-FromCargo([string]$Repo, [string]$Tag, [string]$InstallDir, [string]$BinName) {
  if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "Cargo is required for source fallback but was not found in PATH."
  }

  $repoUrl = "https://github.com/$Repo.git"
  $cargoRoot = New-Item -ItemType Directory -Force -Path (Join-Path ([System.IO.Path]::GetTempPath()) ("drugclaw-cargo-install-" + [guid]::NewGuid().ToString()))
  try {
    Write-Info "No prebuilt binary found. Falling back to cargo install from $repoUrl at $Tag"
    & cargo install --git $repoUrl --tag $Tag --locked --root $cargoRoot.FullName --bin drugclaw
    if ($LASTEXITCODE -ne 0) {
      throw "cargo install failed with exit code $LASTEXITCODE"
    }

    $compiledPath = Join-Path $cargoRoot.FullName "bin\$BinName"
    if (-not (Test-Path $compiledPath)) {
      throw "cargo install completed but $BinName was not found under $($cargoRoot.FullName)\bin"
    }

    Copy-Item -Path $compiledPath -Destination (Join-Path $InstallDir $BinName) -Force
  } finally {
    Remove-Item -Recurse -Force $cargoRoot.FullName -ErrorAction SilentlyContinue
  }
}

$arch = Resolve-Arch
Write-Info "Installing drugclaw for windows/$arch..."

$release = Invoke-RestMethod -Uri $ApiUrl -Headers @{ 'User-Agent' = 'drugclaw-install-script' }
$assetUrl = Select-AssetUrl -release $release -arch $arch
$targetPath = Join-Path $InstallDir $BinName

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

if ($assetUrl) {
  $tmpDir = New-Item -ItemType Directory -Force -Path (Join-Path ([System.IO.Path]::GetTempPath()) ("drugclaw-install-" + [guid]::NewGuid().ToString()))
  try {
    $archivePath = Join-Path $tmpDir.FullName 'drugclaw.zip'
    Write-Info "Downloading: $assetUrl"
    Invoke-WebRequest -Uri $assetUrl -OutFile $archivePath

    Expand-Archive -Path $archivePath -DestinationPath $tmpDir.FullName -Force
    $bin = Get-ChildItem -Path $tmpDir.FullName -Filter $BinName -Recurse | Select-Object -First 1
    if (-not $bin) {
      throw "Could not find $BinName in archive"
    }

    Copy-Item -Path $bin.FullName -Destination $targetPath -Force
  } finally {
    Remove-Item -Recurse -Force $tmpDir.FullName -ErrorAction SilentlyContinue
  }
} else {
  if (-not $release.tag_name) {
    throw "No prebuilt binary found for windows/$arch, and the latest release tag is missing so source fallback cannot start."
  }
  Install-FromCargo -Repo $Repo -Tag $release.tag_name -InstallDir $InstallDir -BinName $BinName
}

$pathUpdated = Ensure-UserPathContains $InstallDir

Write-Info "Installed drugclaw to: $targetPath"
if ($pathUpdated) {
  Write-Info "Added '$InstallDir' to your user PATH."
  Write-Info "Open a new terminal if command lookup does not refresh immediately."
} else {
  Write-Info "PATH already contains '$InstallDir'."
}

Write-Info "drugclaw"
if ($skipRunEffective) {
  Write-Info "Skipping auto-run (-SkipRun)."
} elseif ($hadExistingCommand) {
  Write-Info "Skipping auto-run (upgrade detected)."
} elseif (Get-Command drugclaw -ErrorAction SilentlyContinue) {
  Write-Info "Running: drugclaw"
  try {
    & drugclaw
  } catch {
    Write-Info "Auto-run failed. Try running: drugclaw"
  }
} else {
  Write-Info "Could not find 'drugclaw' in PATH."
  Write-Info "Add this directory to PATH: $InstallDir"
  Write-Info "Then run: $targetPath"
}

if (-not (Get-Command agent-browser.cmd -ErrorAction SilentlyContinue) -and -not (Get-Command agent-browser -ErrorAction SilentlyContinue)) {
  Write-Info "Optional: install browser automation support with:"
  Write-Info "  npm install -g agent-browser"
  Write-Info "  agent-browser install"
}
