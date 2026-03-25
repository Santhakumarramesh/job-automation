#!/usr/bin/env bash
# One-time install: project deps + MCP extras (system Python, no .venv).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python3 -m pip install -U pip
python3 -m pip install -e ".[mcp]"

if [[ ! -f .env ]] && [[ -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — add API keys and LinkedIn credentials."
fi

echo "Done. For Playwright apply flows: python3 -m playwright install chromium"
echo "Run Career Copilot MCP:  bash start.sh"
echo "SSE test: bash start.sh --sse   then curl -sL -o /dev/null -w '%{http_code}\\n' http://127.0.0.1:8765/sse"
