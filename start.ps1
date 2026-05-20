$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python .\app\backend\env_check.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Environment check failed. Install missing dependencies or free port 8765 first."
    exit $LASTEXITCODE
}

Write-Host "Starting Slide2Study at http://127.0.0.1:8765"
python .\app\backend\server.py
