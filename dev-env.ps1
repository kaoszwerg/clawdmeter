# dev-env.ps1 - load the firmware toolchain from setup-dev.ps1 into this shell
#
# Dot-source it so the changes stick to the current session:
#   . .\dev-env.ps1
#
# Activates .venv-dev (pio, esptool on PATH) and points PlatformIO at the
# platform/toolchain copy inside the venv.

$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
$VenvDir  = Join-Path $RepoRoot ".venv-dev"
$Activate = Join-Path $VenvDir "Scripts\Activate.ps1"

if (-not (Test-Path $Activate)) {
    Write-Host "No .venv-dev yet - run: powershell -ExecutionPolicy Bypass -File setup-dev.ps1"
    return
}

. $Activate
$env:PLATFORMIO_CORE_DIR = Join-Path $VenvDir "platformio"
# Set by Git Bash; pioarduino's idf_tools.py refuses to install tools with it.
Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue
Write-Host "Clawdmeter dev env loaded: $(pio --version)"
