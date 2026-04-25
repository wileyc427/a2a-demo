#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

# Anthropic API key — required as the first argument.
if [[ -z "${1:-}" ]]; then
  echo "Usage: bash start.sh <ANTHROPIC_API_KEY>" >&2
  exit 1
fi
export ANTHROPIC_API_KEY="$1"

# Locate a Python 3.10+ interpreter, installing via Homebrew if needed.
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

if [[ -z "$PYTHON" ]]; then
  echo "Python 3 not found. Attempting to install via Homebrew..."
  if ! command -v brew &>/dev/null; then
    echo "Error: Homebrew is also not installed." >&2
    echo "Install Python 3.10+ from https://www.python.org/downloads/ and re-run." >&2
    exit 1
  fi
  brew install python3
  PYTHON=$(command -v python3 2>/dev/null || true)
  if [[ -z "$PYTHON" ]]; then
    echo "Error: Python installation failed. Install manually from https://www.python.org/downloads/" >&2
    exit 1
  fi
  echo "Python installed: $($PYTHON --version)"
fi

# Verify the interpreter is Python 3.10+
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10) ]]; then
  echo "Error: Python 3.10+ required (found $PY_VERSION)." >&2
  echo "Install a newer version from https://www.python.org/downloads/" >&2
  exit 1
fi

# Create the venv if it doesn't exist
if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment at $VENV ..."
  "$PYTHON" -m venv "$VENV"
fi

# Activate
source "$VENV/bin/activate"

# Install/sync dependencies if requirements.txt changed since last install
STAMP="$VENV/.installed_stamp"
REQ="$SCRIPT_DIR/requirements.txt"
if [[ ! -f "$STAMP" || "$REQ" -nt "$STAMP" ]]; then
  echo "Installing dependencies from requirements.txt ..."
  pip install --quiet --upgrade pip
  pip install --quiet -r "$REQ"
  touch "$STAMP"
fi

export PYTHONPATH="$SCRIPT_DIR"
export PYTHONUNBUFFERED=1

# Kill all background children on exit (Ctrl-C or script error)
PIDS=()
cleanup() {
  echo ""
  echo "Stopping all services..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting Solar Developer  (port 8001)..."
python "$SCRIPT_DIR/agents/solar_developer/main.py" &
PIDS+=($!)

echo "Starting Underwriter      (port 8002)..."
python "$SCRIPT_DIR/agents/underwriter/main.py" &
PIDS+=($!)

echo "Starting Orchestrator     (port 8080)..."
python "$SCRIPT_DIR/orchestrator/main.py" &
PIDS+=($!)

echo ""
echo "All services started. Press Ctrl-C to stop."
echo ""
echo "Run the demo in another terminal:"
echo ""
echo "  # Default — reads from prompt.md at the project root:"
echo "  python run_demo.py"
echo ""
echo "  # Or pass an idea directly:"
echo "  python run_demo.py --idea \"80MW agrivoltaic project in Texas\""
echo ""

# Wait for any child to exit unexpectedly
wait -n 2>/dev/null || wait
