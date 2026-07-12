#!/usr/bin/env bash
# Stop the Phase 2 Cloud SQL instance between dev sessions.
# A stopped instance bills storage only (~$1-2/mo for 10GB SSD);
# data, schema, extensions, and users are all preserved.
#
# Usage:
#   source infra/env.sh && bash infra/scripts/sql-stop.sh

set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID env var required (source infra/env.sh)}"
SQL_INSTANCE="${SQL_INSTANCE:-rag-pg}"

echo "Stopping Cloud SQL instance '${SQL_INSTANCE}'..."
gcloud sql instances patch "${SQL_INSTANCE}" \
  --project="${PROJECT_ID}" \
  --activation-policy=NEVER

gcloud sql instances describe "${SQL_INSTANCE}" \
  --project="${PROJECT_ID}" \
  --format="value(state)"
echo "Done. Compute billing stopped; storage-only until sql-start.sh."
