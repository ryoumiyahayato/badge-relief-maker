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

$SmokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("BadgeReliefMaker-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $SmokeRoot | Out-Null
$env:BADGE_RELIEF_SMOKE_DIR = $SmokeRoot
try {
    & $Python -c "import os; from pathlib import Path; import numpy as np; from PIL import Image; root=Path(os.environ['BADGE_RELIEF_SMOKE_DIR']); rows,cols=48,64; mask=np.zeros((rows,cols),dtype=np.uint8); mask[6:-6,8:-8]=255; gradient=np.tile(np.linspace(0,65535,cols,dtype=np.uint16),(rows,1)); gradient[mask==0]=0; Image.fromarray(mask,mode='L').save(root/'solid_mask.png'); Image.fromarray(gradient).save(root/'height_master_16bit.png')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create approved-artifact package smoke fixtures"
    }
    & $Executable `
        --approved-heightmap (Join-Path $SmokeRoot "height_master_16bit.png") `
        --approved-solid-mask (Join-Path $SmokeRoot "solid_mask.png") `
        --output (Join-Path $SmokeRoot "model.obj") `
        --build-report (Join-Path $SmokeRoot "build_report.json") `
        --width-mm 64 `
        --height-mm 48 `
        --base-mm 2 `
        --relief-mm 3 `
        --quality draft | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged approved-artifact OBJ smoke test failed with exit code $LASTEXITCODE"
    }
    foreach ($RequiredOutput in @(
        (Join-Path $SmokeRoot "model.obj"),
        (Join-Path $SmokeRoot "build_report.json")
    )) {
        if (-not (Test-Path -LiteralPath $RequiredOutput)) {
            throw "Packaged approved-artifact path did not create $RequiredOutput"
        }
    }
}
finally {
    Remove-Item Env:\BADGE_RELIEF_SMOKE_DIR -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $SmokeRoot) {
        Remove-Item -LiteralPath $SmokeRoot -Recurse -Force
    }
}
Write-Host "Built and smoke-tested dist\BadgeReliefMaker.exe through the approved deterministic artifact path"
