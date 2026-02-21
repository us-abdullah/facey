# Run backend from project root (so you don't have to cd backend every time)
Set-Location $PSScriptRoot\backend
if (Test-Path .\venv\Scripts\Activate.ps1) {
    .\venv\Scripts\Activate.ps1
}
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
