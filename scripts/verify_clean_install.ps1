[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$originalLocation = Get-Location
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
    & $python -m pip install --quiet --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed" }
    & $python -m pip install --quiet build
    if ($LASTEXITCODE -ne 0) { throw "build module install failed" }

    $distDir = Join-Path $temp "dist"
    & $python -m build --wheel --outdir $distDir $root
    if ($LASTEXITCODE -ne 0) { throw "wheel build failed" }

    $wheels = Get-ChildItem -Path $distDir -Filter "ableton*.whl"
    if ($wheels.Count -eq 0) { throw "no built wheel found in $distDir" }
    $wheelFile = $wheels[0].FullName

    $testVenv = Join-Path $temp "test-venv"
    & py -3 -m venv $testVenv
    $testPython = Join-Path $testVenv "Scripts\python.exe"
    & $testPython -m pip install --quiet $wheelFile
    if ($LASTEXITCODE -ne 0) { throw "installing wheel $wheelFile failed" }

    Set-Location $temp

    $tempEscaped = $temp.Replace("\", "\\")
    $code = @"
import json, sys
from pathlib import Path
import ableton_mcp_server.server as s

assert len(s.PUBLIC_TOOL_NAMES) == 65, f"Expected 65 tools, got {len(s.PUBLIC_TOOL_NAMES)}"

scaffold_dir = Path(r"$tempEscaped").resolve() / "scaffold_out"
res_str = s.scaffold_extension("WheelSmoke", output_directory=str(scaffold_dir))
res = json.loads(res_str)

assert res.get("status") == "scaffolded", f"scaffold_extension status expected 'scaffolded', got {res}"
proj_path = Path(res["project_path"])
vendor_dir = proj_path / "vendor"
assert vendor_dir.is_dir(), f"vendor dir missing: {vendor_dir}"

sdk = list(vendor_dir.glob("ableton-extensions-sdk-*.tgz"))
cli = list(vendor_dir.glob("ableton-extensions-cli-*.tgz"))
assert len(sdk) == 1, f"SDK tarball missing in vendor: {list(vendor_dir.iterdir())}"
assert len(cli) == 1, f"CLI tarball missing in vendor: {list(vendor_dir.iterdir())}"

pkg_path = proj_path / "package.json"
assert pkg_path.is_file(), "package.json missing"
pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
assert "@ableton-extensions/sdk" in deps, "missing @ableton-extensions/sdk dependency"
assert "@ableton-extensions/cli" in deps, "missing @ableton-extensions/cli devDependency"
assert deps["@ableton-extensions/sdk"].startswith("file:./vendor/"), f"SDK dep path wrong: {deps['@ableton-extensions/sdk']}"
assert deps["@ableton-extensions/cli"].startswith("file:./vendor/"), f"CLI dep path wrong: {deps['@ableton-extensions/cli']}"
"@

    $smokeScript = Join-Path $temp "wheel_smoke.py"

    [System.IO.File]::WriteAllText(
        $smokeScript,
        $code,
        [System.Text.UTF8Encoding]::new($false)
    )
    & $testPython $smokeScript
    if ($LASTEXITCODE -ne 0) { throw "wheel smoke verification failed" }
    Write-Host "Clean install and wheel scaffold smoke test SUCCESS"
} finally {
    Set-Location $originalLocation
    if (Test-Path -LiteralPath $temp) { Remove-Item -Recurse -Force -LiteralPath $temp }
}