param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppBuild = Join-Path $Root "dist\AIDrawingCopilot\AIDrawingCopilot.exe"
$InstallerScript = Join-Path $Root "installer\AIDrawingCopilot.iss"
$Output = Join-Path $Root "dist\AIDrawingCopilot-Setup-0.2.0.exe"
$CompilerCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$Compiler = $CompilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $SkipAppBuild) {
    & (Join-Path $PSScriptRoot "build_exe.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Application build failed."
    }
}

if (-not (Test-Path -LiteralPath $AppBuild)) {
    throw "Application EXE was not found: $AppBuild"
}
if (-not $Compiler) {
    throw "Inno Setup 6 was not found. Install JRSoftware.InnoSetup first."
}
if (Test-Path -LiteralPath $Output) {
    Remove-Item -LiteralPath $Output -Force
}

Push-Location (Split-Path -Parent $InstallerScript)
try {
    & $Compiler $InstallerScript
    if ($LASTEXITCODE -ne 0) {
        throw "Installer compilation failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $Output)) {
    throw "Installer compiler finished but the Setup EXE was not found: $Output"
}

Get-Item -LiteralPath $Output | Select-Object FullName, Length, LastWriteTime
