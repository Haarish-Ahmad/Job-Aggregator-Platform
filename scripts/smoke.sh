#!/usr/bin/env bash
# End-to-end smoke test of the whole stack, with Firecrawl and Ollama mocked (no external services needed).
#
#   bash scripts/smoke.sh            # builds and starts a separate stack ("jobsmoke"), checks it, tears it down
#   KEEP=1 bash scripts/smoke.sh     # leave it running afterwards (http://localhost:8080)
#
# It checks: every container healthy, nginx routing, the frontend, API health, auth, Prometheus targets,
# Grafana provisioning, a scraper pipeline run (twice: no duplicates), and an alert email reaching Mailpit.
# shellcheck disable=SC2015  # "cond && ok || bad" is deliberate: ok and bad always succeed
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.smoke.env
PROJECT=jobsmoke
PORT=8080
PROM_PORT=19090
MAIL_PORT=18025
MOCK_FC_PORT=13002      # not 3002/11434: a real Firecrawl/Ollama usually owns those on a dev machine
MOCK_OLLAMA_PORT=11435
rand() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
alnum() { python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range($1)))"; }
dc() { docker compose -p "$PROJECT" --env-file "$ENV_FILE" "$@"; }

GRAFANA_PW=$(alnum 16)
cat > "$ENV_FILE" <<ENV
POSTGRES_PASSWORD=$(alnum 20)
SECRET_KEY=$(rand 40)
INGEST_TOKEN=$(rand 24)
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PW
ADMIN_EMAIL=admin@college.edu
ADMIN_PASSWORD=$(alnum 16)
HTTP_PORT=$PORT
PROMETHEUS_PORT=$PROM_PORT
MAILPIT_UI_PORT=$MAIL_PORT
RUN_ON_START=false
SERVE_SOURCES=shine
FIRECRAWL_API_URL=http://host.docker.internal:$MOCK_FC_PORT
OLLAMA_HOST=http://host.docker.internal:$MOCK_OLLAMA_PORT
ENV

MOCK_PID=""
cleanup() {
  [ -n "$MOCK_PID" ] && kill "$MOCK_PID" 2>/dev/null || true
  if [ "${KEEP:-0}" != "1" ]; then dc down -v --remove-orphans >/dev/null 2>&1 || true; rm -f "$ENV_FILE"; fi
}
trap cleanup EXIT

retry() { local n=$1; shift; for _ in $(seq "$n"); do "$@" && return 0; sleep 3; done; return 1; }
pass=0; fail=0
ok()   { echo "  PASS  $1"; pass=$((pass+1)); }
bad()  { echo "  FAIL  $1"; fail=$((fail+1)); }
check() { local desc=$1; shift; if "$@" >/dev/null 2>&1; then ok "$desc"; else bad "$desc"; fi; }
contains() { local desc=$1 needle=$2 haystack=$3; if grep -qF -- "$needle" <<<"$haystack"; then ok "$desc"; else bad "$desc (missing: $needle)"; fi; }

echo "== starting mocks (Firecrawl :$MOCK_FC_PORT, Ollama :$MOCK_OLLAMA_PORT)"
MOCK_FIRECRAWL_PORT=$MOCK_FC_PORT MOCK_OLLAMA_PORT=$MOCK_OLLAMA_PORT python3 scripts/ci_mocks.py & MOCK_PID=$!
mocks_up() { curl -fsS "http://localhost:$MOCK_FC_PORT/" >/dev/null 2>&1 && curl -fsS "http://localhost:$MOCK_OLLAMA_PORT/api/tags" >/dev/null 2>&1; }
retry 10 mocks_up 2>/dev/null || { echo "mock servers did not start (are ports $MOCK_FC_PORT/$MOCK_OLLAMA_PORT free?)"; exit 1; }

echo "== building and starting the stack (waits for every healthcheck)"
dc up -d --build --wait --wait-timeout 420
echo "== services"; dc ps --format 'table {{.Service}}\t{{.Status}}'
unhealthy=$(dc ps --format '{{.Service}} {{.Health}}' | grep -vE ' healthy$' || true)
[ -z "$unhealthy" ] && ok "every service reports healthy" || bad "not healthy: $unhealthy"

BASE=http://localhost:$PORT
echo "== nginx, frontend, API"
check  "nginx /healthz" curl -fsS "$BASE/healthz"
contains "frontend served at /" '<div id="root">' "$(curl -fsS "$BASE/")"
contains "runtime config served" 'apiBase: "/api"' "$(curl -fsS "$BASE/config.js")"
contains "deep link falls back to the app" '<div id="root">' "$(curl -fsS "$BASE/analytics/skills")"
contains "/api/health reports the database" '"db":"ok"' "$(curl -fsS "$BASE/api/health")"
contains "API docs reachable behind the prefix" 'Job Aggregator Platform' "$(curl -fsS "$BASE/api/openapi.json")"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/metrics")" = 404 ] && ok "/api/metrics is not public" || bad "/api/metrics is public"
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/internal/jobs")" = 404 ] && ok "/api/internal/* is not public" || bad "/api/internal/* is public"
hdrs=$(curl -sI "$BASE/")
contains "security header: nosniff" "nosniff" "$hdrs"
contains "security header: CSP" "Content-Security-Policy" "$hdrs"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/jobs")" = 401 ] && ok "jobs require a login" || bad "jobs are public"

echo "== accounts"
JAR=$(mktemp); trap 'rm -f "$JAR"; cleanup' EXIT
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/register" -H 'Content-Type: application/json' \
  -d '{"name":"Smoke","email":"smoke@college.edu","password":"Smoke@12345","branch":"CSE","cgpa":8,"grad_year":2026,"skills":["java","python"]}')
[ "$code" = 201 ] && ok "register through nginx" || bad "register -> $code"
code=$(curl -s -o /dev/null -w '%{http_code}' -c "$JAR" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d '{"email":"smoke@college.edu","password":"Smoke@12345"}')
[ "$code" = 200 ] && ok "login through nginx" || bad "login -> $code"
contains "session works" '"smoke@college.edu"' "$(curl -fsS -b "$JAR" "$BASE/api/me")"
curl -fsS -b "$JAR" -X PATCH "$BASE/api/me/update" -H 'Content-Type: application/json' -d '{"alerts_enabled":true}' >/dev/null && ok "opt in to alerts"
ADMIN_PW=$(grep ^ADMIN_PASSWORD= "$ENV_FILE" | cut -d= -f2)
ADMIN_JAR=$(mktemp)
code=$(curl -s -o /dev/null -w '%{http_code}' -c "$ADMIN_JAR" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"admin@college.edu\",\"password\":\"$ADMIN_PW\"}")
[ "$code" = 200 ] && ok "bootstrapped admin can log in" || bad "admin login -> $code"

echo "== scraper pipeline, run twice (mock Firecrawl -> Shine -> mock Ollama -> backend)"
run1=$(dc exec -T scraper python - < scripts/smoke_pipeline.py 2>&1) && ok "first run" || bad "first run: $run1"; echo "      $run1" | tail -1
total1=$(curl -fsS -b "$JAR" -D - -o /dev/null "$BASE/api/jobs?source=shine&scope=all" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-total-count"{print $2}')
[ "${total1:-0}" -ge 1 ] && ok "scraped jobs are visible through the API ($total1)" || bad "no scraped jobs visible"
run2=$(dc exec -T scraper python - < scripts/smoke_pipeline.py 2>&1) && ok "second run" || bad "second run: $run2"; echo "      $run2" | tail -1
total2=$(curl -fsS -b "$JAR" -D - -o /dev/null "$BASE/api/jobs?source=shine&scope=all" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-total-count"{print $2}')
[ "$total1" = "$total2" ] && ok "second run created no duplicates ($total1 == $total2)" || bad "duplicates: $total1 -> $total2"
job=$(curl -fsS -b "$JAR" "$BASE/api/jobs?source=shine&scope=all&limit=1")
contains "extracted skills reached the backend" '"necessary_skills":["java","python"]' "$job"
contains "scraped job has company, apply link and freshness" '"last_seen_at"' "$job"
contains "student matches the scraped job" '"score":100' "$(curl -fsS -b "$JAR" "$BASE/api/me/matches")"
contains "analytics available to the admin" '"skills"' "$(curl -fsS -b "$ADMIN_JAR" "$BASE/api/analytics/skill-gap")"
[ "$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "$BASE/api/analytics/skill-gap")" = 403 ] && ok "skill gap is admin-only" || bad "skill gap not restricted"

echo "== email alert reaches Mailpit"
dc exec -T scraper python - <<'PY' >/dev/null && ok "alert run triggered with the ingest token" || bad "alert run failed"
import os, httpx
r = httpx.post("http://backend:8000/internal/alerts/run", headers={"X-Ingest-Token": os.environ["INGEST_TOKEN"]}, timeout=30)
r.raise_for_status(); print(r.json())
PY
# Mailpit receives the message asynchronously: wait until it lists one.
mail_arrived() { curl -fsS "http://localhost:$MAIL_PORT/api/v1/messages" | grep -q 'smoke@college.edu'; }
retry 10 mail_arrived || true
contains "an email for smoke@college.edu arrived" 'smoke@college.edu' "$(curl -fsS "http://localhost:$MAIL_PORT/api/v1/messages")"

echo "== monitoring"
targets_up() {
  local json; json=$(curl -fsS "http://localhost:$PROM_PORT/api/v1/targets") || return 1
  python3 - "$json" <<'PY'
import json, sys
t = json.loads(sys.argv[1])["data"]["activeTargets"]
names = {x["labels"]["job"] for x in t}
sys.exit(0 if {"backend", "scraper", "prometheus"} <= names and all(x["health"] == "up" for x in t) else 1)
PY
}
retry 20 targets_up && ok "Prometheus targets (backend, scraper, prometheus) are all UP" || bad "a Prometheus target is down"
contains "Grafana reachable at /grafana/" '"database": "ok"' "$(curl -fsS "$BASE/grafana/api/health")"
dash=$(curl -fsS -u "admin:$GRAFANA_PW" "$BASE/grafana/api/search?query=")
contains "dashboard 'API health' provisioned" "API health" "$dash"
contains "dashboard 'Scraper pipeline' provisioned" "Scraper pipeline" "$dash"
contains "Prometheus datasource provisioned" '"uid": "prometheus"' "$(curl -fsS -u "admin:$GRAFANA_PW" "$BASE/grafana/api/datasources/uid/prometheus" | python3 -m json.tool)"
q() { curl -fsS -G "http://localhost:$PROM_PORT/api/v1/query" --data-urlencode "query=$1"; }
retry 10 bash -c "curl -fsS -G 'http://localhost:$PROM_PORT/api/v1/query' --data-urlencode 'query=sum(http_requests_total)' | grep -q '\"result\":\[{'" && ok "backend request metrics are being collected" || bad "no backend metrics"
# The pipeline run above happened in a separate `exec` process, so its counters are not in the served process;
# what Prometheus can always see from the served scraper is its own gauges.
retry 10 bash -c "curl -fsS -G 'http://localhost:$PROM_PORT/api/v1/query' --data-urlencode 'query=scraper_run_in_progress' | grep -q '\"result\":\[{'" && ok "scraper metrics are being collected" || bad "no scraper metrics"

rm -f "$ADMIN_JAR"
echo; echo "smoke test: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
