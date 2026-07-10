$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m pip install -e ".[package]"
& $Python -m PyInstaller --clean --noconfirm BadgeReliefMaker.spec
& (Join-Path $Root "dist\BadgeReliefMaker.exe") --help | Out-Null
Write-Host "Built and smoke-tested dist\BadgeReliefMaker.exe"
