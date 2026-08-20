#!/usr/bin/env bash
# Smoke test: health check + register/login/list-patients flow against a
# running SEPHIROTH backend. Used two places:
#   - CI's docker-build-smoke-test job (ephemeral local container)
#   - the post-deploy workflow (against the real, deployed URL)
#
# Usage: scripts/smoke_test.sh <base_url>
#   scripts/smoke_test.sh http://127.0.0.1:8000
#   scripts/smoke_test.sh https://sephiroth-api.onrender.com
#
# Portable: avoids GNU-only flags (e.g. `head -n -1`) since this also runs
# on macOS (BSD userland) during local development.
#
# Auth: against an ephemeral DB (CI's docker-build-smoke-test job) there's
# no clinician yet, so it self-registers -- that only works because
# ENVIRONMENT=development there leaves settings.allow_bootstrap_registration
# at its default True. Against the real deployed service (post-deploy
# workflow) that flag is False (render.yaml) -- registration requires an
# existing clinician's token, so set SMOKE_TEST_EMAIL/SMOKE_TEST_PASSWORD
# (a dedicated, already-registered service account) to log in instead.

set -euo pipefail

BASE_URL="${1:?Usage: smoke_test.sh <base_url>}"
EMAIL="smoke-test-$(date +%s)@example.org"

echo "==> Smoke testing $BASE_URL"

echo "--> GET /health/ready"
HEALTH_CODE=$(curl -s -o /tmp/smoke_health.json -w '%{http_code}' "$BASE_URL/health/ready")
if [ "$HEALTH_CODE" != "200" ]; then
  echo "FAIL: /health/ready returned $HEALTH_CODE"
  cat /tmp/smoke_health.json
  exit 1
fi
cat /tmp/smoke_health.json
echo

if [ -n "${SMOKE_TEST_EMAIL:-}" ] && [ -n "${SMOKE_TEST_PASSWORD:-}" ]; then
  echo "--> POST /api/auth/login (service account)"
  curl -sf -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$SMOKE_TEST_EMAIL\", \"password\": \"$SMOKE_TEST_PASSWORD\"}" \
    -o /tmp/smoke_register.json
  TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/smoke_register.json'))['access_token'])")
  if [ -z "$TOKEN" ]; then
    echo "FAIL: login did not return an access_token"
    exit 1
  fi
  echo "logged in, token acquired"
else
  echo "--> POST /api/auth/register"
  curl -sf -X POST "$BASE_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL\", \"name\": \"Smoke Test\", \"password\": \"smoketest123\"}" \
    -o /tmp/smoke_register.json
  TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/smoke_register.json'))['access_token'])")
  if [ -z "$TOKEN" ]; then
    echo "FAIL: registration did not return an access_token"
    exit 1
  fi
  echo "registered, token acquired"
fi

echo "--> GET /api/patients (authenticated)"
PATIENTS_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/patients" -H "Authorization: Bearer $TOKEN")
if [ "$PATIENTS_CODE" != "200" ]; then
  echo "FAIL: /api/patients returned $PATIENTS_CODE"
  exit 1
fi

echo "--> GET /api/dashboard/stats (authenticated)"
DASH_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/dashboard/stats" -H "Authorization: Bearer $TOKEN")
if [ "$DASH_CODE" != "200" ]; then
  echo "FAIL: /api/dashboard/stats returned $DASH_CODE"
  exit 1
fi

rm -f /tmp/smoke_health.json /tmp/smoke_register.json
echo "==> Smoke test PASSED"
