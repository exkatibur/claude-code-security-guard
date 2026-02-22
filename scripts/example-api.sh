#!/usr/bin/env bash
# Example: Credential-isolated API wrapper script
#
# This script sources .env internally - the LLM never sees the keys.
# Claude Code calls this script via Bash, gets structured output back.
#
# Usage: ./example-wrapper.sh <command> [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load credentials (isolated in this process)
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

if [[ -z "${API_KEY:-}" ]]; then
  echo "ERROR: API_KEY not set (check .env)" >&2
  exit 1
fi

case "${1:-}" in
  fetch)
    # Example: fetch data from an API
    # The LLM sees the JSON response, never the API_KEY
    curl -s \
      -H "Authorization: Bearer $API_KEY" \
      -H "Content-Type: application/json" \
      "https://api.example.com/data"
    ;;
  *)
    echo "Usage: $0 {fetch}" >&2
    exit 1
    ;;
esac
