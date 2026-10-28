#!/usr/bin/env bash
# Run from Server in an ordinary terminal. Uses a fresh, isolated Compose project.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence
exec > >(tee evidence/docker-verification.txt) 2>&1
task_project="campusmeet-l4-check-$(date +%s)"
cleanup() {
  # Only this script's newly created demo containers/volumes are removed.
  docker compose -p "$task_project" --profile database down --volumes
}
trap cleanup EXIT
docker compose config --quiet
docker compose -p "$task_project" --profile database up --build --wait -d
docker compose -p "$task_project" ps
python3 scripts/smoke_http.py --output evidence/http-session.json
curl --fail --silent --show-error http://127.0.0.1:3000/health
docker compose -p "$task_project" exec -T postgres psql -U campusmeet -d campusmeet -v ON_ERROR_STOP=1 -c '\dt'
task_table_count=$(docker compose -p "$task_project" exec -T postgres psql -U campusmeet -d campusmeet -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
test "$task_table_count" = "17"
printf '\nPASS: Docker API/Web, 8 HTTP requests, PostgreSQL 17 tables\n'
