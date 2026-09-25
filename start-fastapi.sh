#!/usr/bin/env bash
# DIP Group 5 - FastAPI Launcher (macOS/Linux)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$SCRIPT_DIR/apps/api"
PYTHON_EXE="$API_DIR/.venv/bin/python"
DOCS_URL="http://127.0.0.1:8000/docs"
OPENAPI_URL="http://127.0.0.1:8000/openapi.json"

die() {
  echo
  echo "[ERROR] $1"
  exit 1
}

echo "[1/7] Checking the project environment..."
[ -f "$API_DIR/compose.yaml" ] || die "Cannot find apps/api/compose.yaml under: $SCRIPT_DIR"
[ -x "$PYTHON_EXE" ] || die "The Python virtual environment is missing: $PYTHON_EXE"

# Locate the Docker CLI (Apple Silicon installs it inside Docker.app)
if ! command -v docker >/dev/null 2>&1; then
  if [ -x "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
    export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
  elif [ -x "/usr/local/bin/docker" ]; then
    export PATH="/usr/local/bin:$PATH"
  fi
fi
command -v docker >/dev/null 2>&1 || die "Docker CLI was not found. Install or repair Docker Desktop."

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "Docker Compose was not found."
fi

echo "[2/7] Checking Docker Desktop..."
if ! docker info >/dev/null 2>&1; then
  [ -d "/Applications/Docker.app" ] || die "Docker is not running and Docker Desktop could not be located."
  echo "      Starting Docker Desktop. This can take a minute after boot..."
  open -a Docker
  ready=0
  for _ in $(seq 1 180); do
    docker info >/dev/null 2>&1 && { ready=1; break; }
    sleep 2
  done
  [ "$ready" -eq 1 ] || die "Docker Desktop did not become ready within 180 seconds."
fi

cd "$API_DIR"

echo "[3/7] Starting PostgreSQL and pgvector..."
$COMPOSE up -d || die "Docker Compose could not start the database."

echo "[4/7] Waiting for PostgreSQL..."
ready=0
for _ in $(seq 1 90); do
  $COMPOSE exec -T db pg_isready >/dev/null 2>&1 && { ready=1; break; }
  sleep 2
done
[ "$ready" -eq 1 ] || die "PostgreSQL did not become ready within 90 seconds."

echo "[5/7] Applying migrations and confirming development data..."
"$PYTHON_EXE" -m alembic upgrade head || die "Database migration failed."
"$PYTHON_EXE" -m app.db.seed || die "Development data setup failed."

echo "[6/7] Chatbot knowledge base (optional)..."
echo "      Skipped automatically. To (re)build the RAG knowledge base, run:"
echo "        python -m app.db.reindex"
echo "      (from apps/api; requires GEMINI_API_KEY in apps/api/.env)."

echo "[7/7] Starting FastAPI..."
"$PYTHON_EXE" -m fastapi dev app/main.py &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

api_is_ready() {
  "$PYTHON_EXE" -c "import json,sys,urllib.request; d=json.load(urllib.request.urlopen('$OPENAPI_URL', timeout=2)); sys.exit(0 if d.get('info',{}).get('title')=='NTU Foodie Hub API' else 1)" >/dev/null 2>&1
}

ready=0
for _ in $(seq 1 60); do
  api_is_ready && { ready=1; break; }
  sleep 2
done

if [ "$ready" -eq 1 ]; then
  echo "      FastAPI is ready at $DOCS_URL"
  command -v open >/dev/null 2>&1 && open "$DOCS_URL"
  wait "$SERVER_PID"
else
  echo
  echo "[ERROR] FastAPI did not become ready within 60 seconds."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi