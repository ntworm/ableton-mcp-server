[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvRoot = Join-Path $RepoRoot ".venv-win"
$Python = Join-Path $VenvRoot "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    & py -3 -m venv $VenvRoot
}

& $Python -m pip install -e "$RepoRoot"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install ableton-mcp-server into $VenvRoot"
}

$AbletonMcp = Join-Path $VenvRoot "Scripts\ableton-mcp.exe"
& $AbletonMcp install-script
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install AbletonMCPServer_RemoteScript"
}

$InstallStatus = & $AbletonMcp install-status --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
    throw "Unable to verify AbletonMCPServer_RemoteScript"
}
$InstalledScript = Join-Path $InstallStatus.target "__init__.py"
$InstalledHash = Get-FileHash -LiteralPath $InstalledScript -Algorithm SHA256
Write-Output "Remote Script verification:"
Write-Output "  algorithm: $($InstalledHash.Algorithm)"
Write-Output "  hash: $($InstalledHash.Hash)"
Write-Output "  path: $($InstalledHash.Path)"

Write-Output "Windows runtime: $Python"
Write-Output "MCP executable: $(Join-Path $VenvRoot 'Scripts\ableton-mcp-server.exe')"
Write-Output "From WSL use: /mnt/c/.../.venv-win/Scripts/ableton-mcp-server.exe"
