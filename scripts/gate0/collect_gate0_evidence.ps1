[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Artifact,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$SdkSha256,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$CliSha256,
    [Parameter(Mandatory = $true)][ValidateSet('before', 'after')][string]$Phase,
    [string]$OutputRoot = 'C:\Users\Usuario\repos\_release-artifacts\groove-brain-gate0'
)

$ErrorActionPreference = 'Stop'
$artifactPath = (Resolve-Path -LiteralPath $Artifact).Path
if (-not [IO.Path]::IsPathFullyQualified($OutputRoot)) {
    throw 'OUTPUT_ROOT_MUST_BE_ABSOLUTE'
}
$outputPath = [IO.Path]::GetFullPath($OutputRoot)
$runIdPath = Join-Path $outputPath 'current-run-id.txt'
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

if ($Phase -eq 'before') {
    $runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff'), ([Guid]::NewGuid().ToString('N').Substring(0, 8))
    Set-Content -LiteralPath $runIdPath -Value $runId -NoNewline -Encoding utf8
} else {
    if (-not (Test-Path -LiteralPath $runIdPath -PathType Leaf)) {
        throw 'RUN_ID_NOT_FOUND'
    }
    $runId = (Get-Content -LiteralPath $runIdPath -Raw).Trim()
    if ($runId -notmatch '^\d{8}-\d{6}-\d{3}-[0-9a-f]{8}$') {
        throw 'RUN_ID_INVALID'
    }
}

$runDir = Join-Path $outputPath $runId
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$destination = Join-Path $runDir "$Phase.json"
if (Test-Path -LiteralPath $destination) {
    throw 'EVIDENCE_PHASE_ALREADY_CAPTURED'
}

$helpers = @(
    Get-Process -Name 'groove-brain-gate0-helper' -ErrorAction SilentlyContinue |
        ForEach-Object {
            $started = $null
            try {
                $started = $_.StartTime.ToUniversalTime().ToString('o')
            } catch {
                $started = 'unavailable'
            }
            [ordered]@{ id = $_.Id; start_time = $started }
        }
)

$networkProfile = @(
    Get-NetConnectionProfile -ErrorAction SilentlyContinue |
        Select-Object Name, IPv4Connectivity, IPv6Connectivity
)

$payload = [ordered]@{
    schema_version = 1
    phase = $Phase
    captured_at_utc = [DateTime]::UtcNow.ToString('o')
    windows = [Environment]::OSVersion.VersionString
    architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    source_commit = $SourceCommit.ToLowerInvariant()
    sdk_sha256 = $SdkSha256.ToLowerInvariant()
    cli_sha256 = $CliSha256.ToLowerInvariant()
    artifact = $artifactPath
    artifact_sha256 = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    helper_processes = $helpers
    network_profile = $networkProfile
}

$payload |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $destination -Encoding utf8
Write-Output $runDir
