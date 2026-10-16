param([switch]$Local)   # -Local: self-contained SQLite mode (no cloud database)
if ($Local) { $env:FINSHIELD_LOCAL = '1' }
# Starts backend (8000) and frontend (3000) against the database configured in backend/.env.
# First run: creates tables, generates the dataset, trains the 3 models, clusters, seeds demo users.
$root = Split-Path $PSScriptRoot -Parent
$b = "$root\backend"
if (-not (Test-Path "$b\.venv")) { python -m venv "$b\.venv"; & "$b\.venv\Scripts\python.exe" -m pip install -e "$b[dev]" }
Push-Location $b
& .\.venv\Scripts\python.exe -m app.cli db-upgrade
$built = & .\.venv\Scripts\python.exe -c "from app.store import Store; print(Store().ready)"
if ($built -notmatch "True") { & .\.venv\Scripts\python.exe -m app.ml.pipeline all }
& .\.venv\Scripts\python.exe -m app.cli seed-users
Start-Process .\.venv\Scripts\python.exe -ArgumentList "-m","uvicorn","app.main:app","--port","8000" -WorkingDirectory $b
Pop-Location
Set-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm install }
npm run dev
