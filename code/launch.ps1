$ErrorActionPreference = 'Stop'
try {
    $codeDir = $PSScriptRoot
    $projectDir = Split-Path -Parent $codeDir
    $pythonPath = Join-Path $projectDir '.venv\Scripts\pythonw.exe'
    $url = 'http://127.0.0.1:18763'
    if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Run setup\install.cmd first.' }
    $instance = $null
    try { $instance = Invoke-RestMethod "$url/api/instance" -TimeoutSec 2 } catch {}
    if ($instance) {
        if ($instance.project -ne $projectDir) { throw 'Another workbench is running. Stop that workbench before opening this copy.' }
    } else {
        if (Get-NetTCPConnection -LocalPort 18763 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 18763 is occupied. Stop the other workbench first.' }
        $dataDir = Join-Path $projectDir 'data'
        New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
        Start-Process -FilePath $pythonPath -ArgumentList @('-B','-u',('"' + (Join-Path $codeDir 'app.py') + '"')) -WorkingDirectory $codeDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataDir 'server.log') -RedirectStandardError (Join-Path $dataDir 'server-error.log') | Out-Null
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Milliseconds 300
            try { $instance = Invoke-RestMethod "$url/api/instance" -TimeoutSec 1; break } catch {}
        }
        if (!$instance -or $instance.project -ne $projectDir) { throw 'Startup failed. See data\server-error.log.' }
    }
    Start-Process $url
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
