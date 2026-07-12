#!/usr/bin/env bash
# Start the Phase 2 Cloud SQL instance for a dev session.
# Billing: compute charges resume while running (~$9/mo equivalent for
# db-f1-micro); stop with sql-stop.sh when done.
#
# Usage:
#   source infra/env.sh && bash infra/scripts/sql-start.sh

set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID env var required (source infra/env.sh)}"
SQL_INSTANCE="${SQL_INSTANCE:-rag-pg}"

echo "Starting Cloud SQL instance '${SQL_INSTANCE}' (takes ~1-2 min)..."
gcloud sql instances patch "${SQL_INSTANCE}" \
  --project="${PROJECT_ID}" \
  --activation-policy=ALWAYS

gcloud sql instances describe "${SQL_INSTANCE}" \
  --project="${PROJECT_ID}" \
  --format="value(state)"
echo "Done. Stop it after your session: bash infra/scripts/sql-stop.sh"
