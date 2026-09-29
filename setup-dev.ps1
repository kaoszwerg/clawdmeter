# setup-dev.ps1 - Clawdmeter firmware toolchain in one self-contained venv
#
# Creates .venv-dev\ at the repo root and installs everything needed to build
# and flash the firmware into it:
#   - PlatformIO Core (pio), esptool, pyserial
#   - PlatformIO's platform, toolchains and libraries for the chosen board env
#     (PLATFORMIO_CORE_DIR points into the venv, so nothing lands in
#     %USERPROFILE%\.platformio and deleting .venv-dev\ removes all of it)
#
# The daemon keeps its own .venv\ (install-windows.ps1); the two don't mix.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File setup-dev.ps1                    # default env: waveshare_lcd_146
#   powershell -ExecutionPolicy Bypass -File setup-dev.ps1 -Env waveshare_knob_18
#
# Afterwards, load the environment into the current PowerShell session:
#   . .\dev-env.ps1
#   pio run -d firmware -e waveshare_lcd_146 -t upload --upload-port COM7

param(
    [string]$Env = "waveshare_lcd_146"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Log {
    param([string]$Msg)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $Msg"
}

$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
$VenvDir  = Join-Path $RepoRoot ".venv-dev"
$PioCore  = Join-Path $VenvDir "platformio"

# ------------------------------------------------------------------
# Step 1: pick a Python. PlatformIO lags new CPython releases, so prefer
# 3.12 / 3.13 via the py launcher and fall back to whatever `python` is.
# ------------------------------------------------------------------
function Find-Python {
    foreach ($v in @("3.12", "3.13", "3.11")) {
        try {
            $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch { }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "No Python found. Install Python 3.12 from https://www.python.org/downloads/ and re-run."
}

if (Test-Path (Join-Path $VenvDir "Scripts\python.exe")) {
    Log "venv already exists at .venv-dev - reusing it"
} else {
    $py = Find-Python
    Log "Creating venv at .venv-dev with $py ..."
    & $py -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed (exit $LASTEXITCODE)" }
}

$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

# ------------------------------------------------------------------
# Step 2: Python tools
# ------------------------------------------------------------------
Log "Installing platformio, esptool, pyserial ..."
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install --upgrade platformio esptool pyserial --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }

# ------------------------------------------------------------------
# Step 3: PlatformIO platform, toolchain and libraries, all inside the venv
# ------------------------------------------------------------------
$env:PLATFORMIO_CORE_DIR = $PioCore
# Launched from Git Bash, MSYSTEM leaks into this process and pioarduino's
# idf_tools.py refuses to install the toolchain ("MSys/Mingw is not supported").
Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue
$Pio = Join-Path $VenvDir "Scripts\pio.exe"
Log "Fetching platform, toolchain and libraries for env '$Env' (first run downloads ~1 GB) ..."
& $Pio pkg install -d (Join-Path $RepoRoot "firmware") -e $Env
if ($LASTEXITCODE -ne 0) { throw "pio pkg install failed (exit $LASTEXITCODE)" }

Log "Done."
Log ""
Log "Load the environment into this shell:   . .\dev-env.ps1"
Log "Build:                                  pio run -d firmware -e $Env"
Log "Flash:                                  pio run -d firmware -e $Env -t upload --upload-port COMx"
