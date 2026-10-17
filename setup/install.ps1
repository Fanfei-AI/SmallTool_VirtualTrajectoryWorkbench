param([string]$Python = '')
$ErrorActionPreference = 'Stop'
try {
    $projectDir = Split-Path -Parent $PSScriptRoot
    $venvDir = Join-Path $projectDir '.venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    if (!(Test-Path -LiteralPath $venvPython)) {
        if (Test-Path -LiteralPath $venvDir) { throw 'Incomplete .venv found. Rename it before retrying; no files were deleted.' }
        if ($Python) {
            & $Python -c "import sys; assert sys.version_info[:2] == (3,13), 'Python 3.13 required'"
            if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
            & $Python -m venv $venvDir
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.13 -m venv $venvDir
        } else {
            & python -c "import sys; assert sys.version_info[:2] == (3,13), 'Python 3.13 required'"
            if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.13 or supply -Python.' }
            & python -m venv $venvDir
        }
        if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $venvPython)) { throw 'Virtual environment creation failed.' }
    }
    & $venvPython -B -c "import sys; assert sys.version_info[:2] == (3,13), 'Python 3.13 required'"
    if ($LASTEXITCODE -ne 0) { throw 'Existing environment is not Python 3.13.' }
    & $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Download or installation failed. Check network access and retry.' }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
    & $venvPython -B -c "from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation"
    if ($LASTEXITCODE -ne 0) { throw 'Location service import failed.' }
    Write-Host 'Installation complete. Use the launcher in the project root. No phone settings have been changed.'
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
