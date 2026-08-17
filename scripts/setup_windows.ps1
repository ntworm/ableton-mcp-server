[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvRoot = Join-Path $RepoRoot ".venv-win"
$Python = Join-Path $VenvRoot "Scripts\python.exe"

if ($DryRun) {
    Push-Location $RepoRoot
    try {
        if (Test-Path -LiteralPath $Python) {
            & $Python -B -m ableton_mcp_server.cli install-script --dry-run
        } else {
            & py -3 -B -m ableton_mcp_server.cli install-script --dry-run
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to preview installation of AbletonMCPServer_RemoteScript"
        }
    } finally {
        Pop-Location
    }
    exit 0
}

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

$InstallStatusRaw = & $AbletonMcp install-status --json
if ($LASTEXITCODE -ne 0) {
    throw "Unable to verify AbletonMCPServer_RemoteScript (install-status exited $LASTEXITCODE)"
}
try {
    $InstallStatus = $InstallStatusRaw | ConvertFrom-Json
} catch {
    throw "Unable to verify AbletonMCPServer_RemoteScript (install-status returned invalid JSON)"
}
if ($null -eq $InstallStatus -or [string]::IsNullOrWhiteSpace($InstallStatus.target)) {
    throw "Unable to verify AbletonMCPServer_RemoteScript (install-status reported no target)"
}
$InstalledScript = Join-Path $InstallStatus.target "__init__.py"
if (-not (Test-Path -LiteralPath $InstalledScript)) {
    throw "Unable to verify AbletonMCPServer_RemoteScript (expected file not found at $InstalledScript)"
}
$InstalledHash = Get-FileHash -LiteralPath $InstalledScript -Algorithm SHA256
Write-Output "Remote Script verification:"
Write-Output "  algorithm: $($InstalledHash.Algorithm)"
Write-Output "  hash: $($InstalledHash.Hash)"
Write-Output "  path: $($InstalledHash.Path)"

Write-Output "Windows runtime: $Python"
Write-Output "MCP executable: $(Join-Path $VenvRoot 'Scripts\ableton-mcp-server.exe')"
Write-Output "From WSL use: /mnt/c/.../.venv-win/Scripts/ableton-mcp-server.exe"
