$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$AppName = "AIDrawingCopilot"
$LegacyAppName = [string]::Concat([char[]](0x41, 0x49, 0x4F5C, 0x56FE, 0x526F, 0x9A7E, 0x9A76))
$DistDir = Join-Path $Root "dist"
$AppDir = Join-Path $DistDir $AppName
$LegacyAppDir = Join-Path $DistDir $LegacyAppName
$BuildDir = Join-Path $Root "build"
$OldOneFile = Join-Path $DistDir "$AppName.exe"
$LegacyOneFile = Join-Path $DistDir "$LegacyAppName.exe"
$PreservedData = $null

Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"

py -3 -c "import sys; print(sys.version)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Python launcher cannot run Python 3. Build stopped before touching dist."
}

py -3 -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not available. Build stopped before touching dist."
}

py -3 scripts\create_icon.py
if ($LASTEXITCODE -ne 0) {
    throw "Icon generation failed. Build stopped before touching dist."
}

if (Test-Path $AppDir) {
    $resolvedApp = Resolve-Path $AppDir
    if (-not ($resolvedApp.Path.StartsWith($Root.Path))) {
        throw "Refuse to clean outside project root: $resolvedApp"
    }
    $dataDir = Join-Path $AppDir "data"
    if (Test-Path $dataDir) {
        New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
        $PreservedData = Join-Path $BuildDir ("preserved-data-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
        Move-Item -LiteralPath $dataDir -Destination $PreservedData
    }
    Remove-Item -LiteralPath $AppDir -Recurse -Force
}

if (-not $PreservedData -and (Test-Path (Join-Path $LegacyAppDir "data"))) {
    New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
    $PreservedData = Join-Path $BuildDir ("preserved-data-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    Move-Item -LiteralPath (Join-Path $LegacyAppDir "data") -Destination $PreservedData
}

if (Test-Path $OldOneFile) {
    Remove-Item -LiteralPath $OldOneFile -Force
}

$pyinstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onedir",
    "--name", $AppName,
    "--icon", "assets\app.ico",
    "--add-data", "assets\app.ico;assets",
    "main.py"
)
py -3 -m PyInstaller @pyinstallerArgs

New-Item -ItemType File -Force -Path (Join-Path $AppDir "portable.mode") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "data") | Out-Null

if ($PreservedData -and (Test-Path $PreservedData)) {
    $targetData = Join-Path $AppDir "data"
    if (Test-Path $targetData) {
        Remove-Item -LiteralPath $targetData -Recurse -Force
    }
    Move-Item -LiteralPath $PreservedData -Destination $targetData
}

$Exe = Join-Path $AppDir "$AppName.exe"
if (-not (Test-Path $Exe)) {
    throw "Build finished but EXE was not found: $Exe"
}

if (Test-Path $LegacyAppDir) {
    $resolvedLegacy = Resolve-Path $LegacyAppDir
    if (-not ($resolvedLegacy.Path.StartsWith($Root.Path))) {
        throw "Refuse to clean legacy directory outside project root: $resolvedLegacy"
    }
    Remove-Item -LiteralPath $LegacyAppDir -Recurse -Force
}
if (Test-Path $LegacyOneFile) {
    Remove-Item -LiteralPath $LegacyOneFile -Force
}

Get-Item $Exe | Select-Object FullName, Length, LastWriteTime
