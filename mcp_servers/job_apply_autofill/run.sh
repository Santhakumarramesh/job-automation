#!/bin/bash
# Run Career Copilot MCP server
# Requires: pip install fastmcp playwright mcp && playwright install chromium
cd "$(dirname "$0")/../.."
exec python -m mcp_servers.job_apply_autofill.server
