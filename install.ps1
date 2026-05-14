# install.ps1 — Staffing Intelligence Platform bootstrap for Windows
# Run in PowerShell as Administrator:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#   .\install.ps1

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  🧠 Staffing Intelligence Platform — Windows Installer" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# ── Check Docker ──────────────────────────────────────────────────────────────
Write-Host "[SIP] Checking Docker..." -ForegroundColor Yellow
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[SIP] ✗ Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
    exit 1
}
docker info | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[SIP] ✗ Docker is not running. Start Docker Desktop and retry." -ForegroundColor Red
    exit 1
}
Write-Host "[SIP] ✓ Docker is running" -ForegroundColor Green

# ── Check Python ──────────────────────────────────────────────────────────────
Write-Host "[SIP] Checking Python..." -ForegroundColor Yellow
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[SIP] ✗ Python not found. Install from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "[SIP] ✓ $(python --version)" -ForegroundColor Green

# ── Set up .env ───────────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $secret = python -c "import secrets; print(secrets.token_hex(32))"
    (Get-Content ".env") -replace "CHANGE_THIS_TO_A_RANDOM_32_CHAR_STRING", $secret | Set-Content ".env"
    Write-Host "[SIP] ✓ .env created" -ForegroundColor Green
} else {
    Write-Host "[SIP] ⚠ .env already exists — skipping" -ForegroundColor Yellow
}

# ── Virtual env + dependencies ────────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    Write-Host "[SIP] ✓ Virtual environment created" -ForegroundColor Green
}
& .venv\Scripts\Activate.ps1
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
python -m spacy download en_core_web_sm --quiet
Write-Host "[SIP] ✓ Dependencies installed" -ForegroundColor Green

# ── Docker services ───────────────────────────────────────────────────────────
Write-Host "[SIP] Starting Docker services..." -ForegroundColor Yellow
docker compose up -d
Write-Host "[SIP] ✓ Docker services started" -ForegroundColor Green

# ── Wait for Postgres ─────────────────────────────────────────────────────────
Write-Host "[SIP] Waiting for Postgres..." -ForegroundColor Yellow
$maxWait = 30; $count = 0
do {
    Start-Sleep 1; $count++
    if ($count -ge $maxWait) { Write-Host "[SIP] ✗ Postgres timeout" -ForegroundColor Red; exit 1 }
    $ready = docker compose exec -T postgres pg_isready -U sip -q 2>$null
} until ($LASTEXITCODE -eq 0)
Write-Host "[SIP] ✓ Postgres ready" -ForegroundColor Green

# ── Migrations ────────────────────────────────────────────────────────────────
alembic upgrade head
Write-Host "[SIP] ✓ Database migrations complete" -ForegroundColor Green

# ── Hash passwords ────────────────────────────────────────────────────────────
python scripts/hash_passwords.py
Write-Host "[SIP] ✓ Default users created" -ForegroundColor Green

# ── Pull Ollama model ─────────────────────────────────────────────────────────
Write-Host "[SIP] ⚠ Pulling Llama3 model in background..." -ForegroundColor Yellow
Start-Job { docker compose exec ollama ollama pull llama3 } | Out-Null

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  ✅ Installation complete!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "  Start: streamlit run app.py"
Write-Host "  Open:  http://localhost:8501"
Write-Host ""
Write-Host "  Logins: recruiter1/recruit123  manager1/manage123"
Write-Host "          exec1/exec123  compliance1/comply123"
Write-Host ""
