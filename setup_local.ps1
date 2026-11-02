$ErrorActionPreference = "Stop"
$py = "py -3.11"
Write-Host "Creating local Python virtual environment (.venv)..."
Invoke-Expression "$py -m venv .venv"
$python = Join-Path $PWD ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements-ml.txt
& $python -m pip install -r requirements.txt
Write-Host "Setup finished. Open this folder in VS Code and select .venv as the notebook kernel."

Write-Host "Preparing/validating DNN-HMM deployment files..."
& $python "scripts\prepare_deployment.py"
if ($LASTEXITCODE -ne 0) { Write-Warning "Artifact check needs attention; see output above." }
