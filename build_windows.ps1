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
    & $Python -c "import os; from pathlib import Path; from PIL import Image, ImageDraw; root=Path(os.environ['BADGE_RELIEF_SMOKE_DIR']); image=Image.new('RGBA',(96,96),(0,0,0,0)); draw=ImageDraw.Draw(image); draw.ellipse((8,8,88,88),fill=(210,210,210,255),outline=(20,20,20,255),width=5); draw.rectangle((42,20,54,76),fill=(45,45,45,255)); image.save(root/'input.png')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create packaged semantic-pipeline smoke fixture"
    }
    & $Executable `
        --input (Join-Path $SmokeRoot "input.png") `
        --output (Join-Path $SmokeRoot "model.obj") `
        --preview-dir (Join-Path $SmokeRoot "previews") `
        --max-grid-cells 10000 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged semantic/adaptive pipeline smoke test failed with exit code $LASTEXITCODE"
    }
    foreach ($RequiredOutput in @(
        (Join-Path $SmokeRoot "model.obj"),
        (Join-Path $SmokeRoot "previews\semantic_region_preview.png"),
        (Join-Path $SmokeRoot "previews\confidence_heatmap_preview.png")
    )) {
        if (-not (Test-Path -LiteralPath $RequiredOutput)) {
            throw "Packaged semantic/adaptive pipeline did not create $RequiredOutput"
        }
    }
}
finally {
    Remove-Item Env:\BADGE_RELIEF_SMOKE_DIR -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $SmokeRoot) {
        Remove-Item -LiteralPath $SmokeRoot -Recurse -Force
    }
}
Write-Host "Built and smoke-tested dist\BadgeReliefMaker.exe, including semantic/adaptive previews"
