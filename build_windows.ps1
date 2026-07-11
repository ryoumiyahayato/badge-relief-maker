$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m pip install -e ".[package]"
if ($LASTEXITCODE -ne 0) {
    throw "Package dependency installation failed with exit code $LASTEXITCODE"
}
$Executable = Join-Path $Root "dist\BadgeReliefMaker.exe"
$RunningExecutable = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "BadgeReliefMaker.exe" -and $_.ExecutablePath -eq $Executable }
if ($RunningExecutable) {
    throw "Close the running dist\BadgeReliefMaker.exe before rebuilding"
}
& $Python -m PyInstaller --clean --noconfirm BadgeReliefMaker.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}
& $Executable --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Packaged --help smoke test failed with exit code $LASTEXITCODE"
}
$Version = (Get-Item -LiteralPath $Executable).VersionInfo
$ProjectVersionLine = Select-String -LiteralPath (Join-Path $Root "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $ProjectVersionLine) {
    throw "Could not read project version from pyproject.toml"
}
$ExpectedVersion = $ProjectVersionLine.Matches[0].Groups[1].Value
if ($Version.FileVersion -notlike "$ExpectedVersion*" -or $Version.ProductVersion -notlike "$ExpectedVersion*") {
    throw "Packaged version metadata is missing or incorrect"
}
& $Executable --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Packaged --version smoke test failed with exit code $LASTEXITCODE"
}
Write-Host "Built and smoke-tested dist\BadgeReliefMaker.exe"
