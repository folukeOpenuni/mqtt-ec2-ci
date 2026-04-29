#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# local-run.sh — Run MQTT tests locally via Docker Compose
# Usage: bash scripts/local-run.sh [--keep]
#   --keep  leave containers running after tests (useful for debugging)
# ─────────────────────────────────────────────────────

set -euo pipefail

KEEP=false
[[ "${1:-}" == "--keep" ]] && KEEP=true

echo "🐳  Building containers..."
docker compose build

echo ""
echo "🚀  Starting broker and running tests..."
docker compose up --abort-on-container-exit --exit-code-from test-runner

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  echo "✅  All MQTT protocol tests passed!"
else
  echo "❌  Some tests failed. Check reports/results.xml"
fi

if [ "$KEEP" = false ]; then
  echo "🧹  Tearing down containers..."
  docker compose down
fi

exit $EXIT_CODE