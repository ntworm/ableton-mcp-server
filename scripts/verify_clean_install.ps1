[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temp = [IO.Path]::GetFullPath(
    (Join-Path $tempRoot ("ableton-mcp-clean-" + [guid]::NewGuid()))
)
if (-not $temp.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create/delete a clean-install directory outside the OS temp root"
}
try {
    & py -3 -m venv $temp
    $python = Join-Path $temp "Scripts\python.exe"
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed" }
    & $python -m pip install $root
    if ($LASTEXITCODE -ne 0) { throw "clean package install failed" }
    & $python -c "import ableton_mcp_server.server as s; assert len(s.PUBLIC_TOOL_NAMES) == 65"
    if ($LASTEXITCODE -ne 0) { throw "installed package import failed" }
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -Recurse -Force -LiteralPath $temp }
}