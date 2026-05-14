#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — Staffing Intelligence Platform bootstrap
# Supports: macOS (Apple Silicon & Intel), Linux
# For Windows: use install.ps1 (see docs/setup.md)
#
# Usage:
#   chmod +x install.sh && ./install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${BOLD}[SIP]${NC} $1"; }
success() { echo -e "${GREEN}[SIP] ✓${NC} $1"; }
warn()    { echo -e "${YELLOW}[SIP] ⚠${NC}  $1"; }
error()   { echo -e "${RED}[SIP] ✗${NC} $1"; exit 1; }

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  🧠 Staffing Intelligence Platform — Installer${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── 1. Check Docker ───────────────────────────────────────────────────────────
info "Checking Docker..."
if ! command -v docker &>/dev/null; then
  error "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
fi
if ! docker info &>/dev/null; then
  error "Docker is not running. Please start Docker Desktop and try again."
fi
success "Docker is running ($(docker --version))"

# ── 2. Check Python ───────────────────────────────────────────────────────────
info "Checking Python..."
if command -v python3 &>/dev/null; then
  PYTHON=python3
elif command -v python &>/dev/null; then
  PYTHON=python
else
  error "Python 3.10+ not found. Install from https://www.python.org/downloads/"
fi
PY_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
info "Found Python $PY_VERSION"

# ── 3. Set up .env ────────────────────────────────────────────────────────────
info "Setting up environment config..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  # Generate a random cookie secret
  SECRET=$($PYTHON -c "import secrets; print(secrets.token_hex(32))")
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/CHANGE_THIS_TO_A_RANDOM_32_CHAR_STRING/$SECRET/" .env
  else
    sed -i "s/CHANGE_THIS_TO_A_RANDOM_32_CHAR_STRING/$SECRET/" .env
  fi
  success ".env created with random secret key"
else
  warn ".env already exists — skipping"
fi

# ── 4. Python virtual env + dependencies ─────────────────────────────────────
info "Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
  $PYTHON -m venv .venv
  success "Virtual environment created at .venv/"
else
  warn ".venv already exists — skipping"
fi

info "Installing Python dependencies (this may take 2-3 minutes)..."
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Python dependencies installed"

# Download spaCy English model
info "Downloading spaCy language model..."
python -m spacy download en_core_web_sm --quiet
success "spaCy model downloaded"

# ── 5. Start Docker services ──────────────────────────────────────────────────
info "Starting Docker services (Postgres, Redis, Ollama)..."
docker compose up -d
success "Docker services started"

# ── 6. Wait for Postgres to be ready ─────────────────────────────────────────
info "Waiting for Postgres to be ready..."
MAX_WAIT=30
COUNT=0
until docker compose exec -T postgres pg_isready -U sip -q 2>/dev/null; do
  if [ $COUNT -ge $MAX_WAIT ]; then
    error "Postgres did not become ready in ${MAX_WAIT}s. Check: docker compose logs postgres"
  fi
  COUNT=$((COUNT + 1))
  sleep 1
done
success "Postgres is ready"

# ── 7. Run database migrations ────────────────────────────────────────────────
info "Running database migrations..."
alembic upgrade head
success "Database migrations complete"

# ── 8. Hash user passwords ────────────────────────────────────────────────────
info "Setting up default user accounts..."
python scripts/hash_passwords.py
success "Default users created (see docs/setup.md for credentials)"

# ── 9. Pull Ollama model (background) ────────────────────────────────────────
info "Pulling Llama3 model in background (this takes a few minutes on first run)..."
docker compose exec -d ollama ollama pull llama3 2>/dev/null || true
warn "Llama3 pull started in background. AI assistant will be available once it completes."
warn "Check progress: docker compose exec ollama ollama list"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  ✅ Installation complete!${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Start the platform:  ${BOLD}streamlit run app.py${NC}"
echo -e "  Open in browser:     ${BOLD}http://localhost:8501${NC}"
echo ""
echo -e "  Default logins (change in auth_config.yaml):"
echo -e "    recruiter1 / recruit123   (Recruiter)"
echo -e "    manager1   / manage123    (Manager)"
echo -e "    exec1      / exec123      (Executive)"
echo -e "    compliance1/ comply123    (Compliance)"
echo ""
echo -e "  Full setup guide:    ${BOLD}docs/setup.md${NC}"
echo ""
