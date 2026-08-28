param(
    [Parameter(Mandatory = $true)][string]$Commit,
    [Parameter(Mandatory = $true)][string]$Workspace
)

$ErrorActionPreference = "Stop"
if ($Commit -notmatch "^[0-9a-f]{40}$") {
    throw "INVALID_COMMIT"
}

& wsl.exe --install --distribution Ubuntu-24.04 --no-launch --web-download
if ($LASTEXITCODE -ne 0) {
    throw "WSL_INSTALL_FAILED"
}
& wsl.exe --set-default-version 2
if ($LASTEXITCODE -ne 0) {
    throw "WSL2_DEFAULT_FAILED"
}
$archive = Join-Path $env:RUNNER_TEMP "uv-x86_64-unknown-linux-gnu.tar.gz"
$archiveUrl = "https://github.com/astral-sh/uv/releases/download/0.12.7/uv-x86_64-unknown-linux-gnu.tar.gz"
Invoke-WebRequest -Uri $archiveUrl -OutFile $archive
$actualHash = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne "788f18abea7c5f55d6216e4f5613fd89d4d59b631efeec117b2b07fe72f1da21") {
    throw "UV_ARCHIVE_HASH_MISMATCH"
}
$workspaceArchive = Join-Path $Workspace ".pano-wsl-uv.tar.gz"
Copy-Item -Path $archive -Destination $workspaceArchive

$normalizedWorkspace = $Workspace.Replace('\', '/')
if ($normalizedWorkspace -notmatch '^([A-Za-z]):/(.+)$') {
    throw "WSL_WORKSPACE_INVALID"
}
$wslWorkspace = "/mnt/$($Matches[1].ToLowerInvariant())/$($Matches[2])"
$kernelRelease = (& wsl.exe --distribution Ubuntu-24.04 -- uname -r).Trim()
if ($LASTEXITCODE -ne 0 -or $kernelRelease -notmatch "(?i)wsl2") {
    throw "WSL2_NOT_ACTIVE"
}

$probe = @'
set -euo pipefail
workspace="$1"
commit="$2"
cd "$workspace"
export UV_PROJECT_ENVIRONMENT=/tmp/pano-venv
export UV_CACHE_DIR=/tmp/pano-uv-cache
rm -rf .pano-wsl-uv
mkdir .pano-wsl-uv
tar -xzf .pano-wsl-uv.tar.gz -C .pano-wsl-uv --strip-components=1
./.pano-wsl-uv/uv sync --extra dev
./.pano-wsl-uv/uv run python scripts/platform_probe.py \
  --label wsl2-x64 \
  --commit "$commit" \
  --output evidence/wsl2-x64.json
rm -rf .pano-wsl-uv .pano-wsl-uv.tar.gz
'@
$probe = $probe.Replace("`r", "")
$probe | & wsl.exe --distribution Ubuntu-24.04 -- bash -s -- $wslWorkspace $Commit
if ($LASTEXITCODE -ne 0) {
    throw "WSL2_PROBE_FAILED"
}
