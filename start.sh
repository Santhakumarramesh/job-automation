#!/usr/bin/env bash
# Career Copilot MCP — stdio (Claude Desktop / Cursor) or SSE (debugging).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  echo "Usage: bash start.sh           # stdio (default)"
  echo "       bash start.sh --sse     # HTTP SSE (e.g. curl http://127.0.0.1:\${MCP_SSE_PORT:-8765}/sse)"
  echo "Env: MCP_SSE_PORT (default 8765), MCP_SSE_HOST (default 127.0.0.1)"
  exit 1
}

case "${1:-}" in
  -h|--help) usage ;;
  --sse|--http)
    HOST="${MCP_SSE_HOST:-127.0.0.1}"
    PORT="${MCP_SSE_PORT:-8765}"
    exec fastmcp run mcp_servers/job_apply_autofill/server.py \
      --transport sse --host "$HOST" --port "$PORT" --no-banner
    ;;
  "")
    exec python3 -m mcp_servers.job_apply_autofill.server
    ;;
  *)
    usage
    ;;
esac
