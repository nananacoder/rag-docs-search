#!/usr/bin/env bash
# Phase 1 teardown — reverse-order resource deletion.
# Run between dev sessions to keep idle cost at $0.
#
# Usage:
#   bash infra/scripts/destroy.sh                     # safe: keeps GCS buckets, project
#   DELETE_BUCKETS=1 bash infra/scripts/destroy.sh    # also wipes corpus + eval buckets
#   DELETE_PROJECT=1 bash infra/scripts/destroy.sh    # nuke the entire project (irreversible)

set -euo pipefail

# ---- Variables (must match infra/setup.md §0) ----
: "${PROJECT_ID:?PROJECT_ID env var required (set the same way as infra/setup.md §0)}"
REGION="${REGION:-us-central1}"
LOCATION_DISCOVERY="${LOCATION_DISCOVERY:-us}"
DATASTORE_ID="${DATASTORE_ID:-astronomy-2e-datastore}"
ENGINE_ID="${ENGINE_ID:-astronomy-2e-engine}"
BUCKET_RAW="${BUCKET_RAW:-${PROJECT_ID}-rag-raw}"
BUCKET_EVAL="${BUCKET_EVAL:-${PROJECT_ID}-rag-eval}"
BUCKET_ARTIFACTS="${BUCKET_ARTIFACTS:-${PROJECT_ID}-rag-artifacts}"

echo "==> Tearing down Phase 1 resources in project ${PROJECT_ID}"
echo "    Region: ${REGION}    Datastore: ${DATASTORE_ID}    Engine: ${ENGINE_ID}"
echo

gcloud config set project "$PROJECT_ID" >/dev/null

# ---- 1. Cloud Run services ----
echo "==> Deleting Cloud Run services"
for svc in api web worker; do
    if gcloud run services describe "$svc" --region="$REGION" >/dev/null 2>&1; then
        gcloud run services delete "$svc" --region="$REGION" --quiet
    fi
done

# ---- 2. Eventarc triggers ----
echo "==> Deleting Eventarc triggers"
for trig in $(gcloud eventarc triggers list --location="$REGION" --format='value(name)' 2>/dev/null); do
    gcloud eventarc triggers delete "$trig" --location="$REGION" --quiet || true
done

# ---- 3. Vertex AI Search: engine before datastore ----
ACCESS_TOKEN=$(gcloud auth print-access-token)

echo "==> Deleting search engine ${ENGINE_ID}"
curl -s -X DELETE \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/collections/default_collection/engines/${ENGINE_ID}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" || true

echo "==> Deleting datastore ${DATASTORE_ID}"
curl -s -X DELETE \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/dataStores/${DATASTORE_ID}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" || true

# ---- 4. GCS buckets (gated) ----
if [[ "${DELETE_BUCKETS:-0}" == "1" ]]; then
    echo "==> Deleting GCS buckets (DELETE_BUCKETS=1)"
    for b in "$BUCKET_RAW" "$BUCKET_EVAL" "$BUCKET_ARTIFACTS"; do
        if gcloud storage buckets describe "gs://$b" >/dev/null 2>&1; then
            gcloud storage rm -r "gs://$b" --quiet
        fi
    done
else
    echo "==> Skipping GCS buckets (set DELETE_BUCKETS=1 to wipe)"
fi

# ---- 5. Artifact Registry ----
echo "==> Deleting Artifact Registry repo rag-docs"
gcloud artifacts repositories delete rag-docs --location="$REGION" --quiet 2>/dev/null || true

# ---- 6. Service accounts ----
echo "==> Deleting service accounts"
for sa in sa-run-api sa-run-worker sa-run-web sa-cloudbuild sa-setup; do
    email="${sa}@${PROJECT_ID}.iam.gserviceaccount.com"
    if gcloud iam service-accounts describe "$email" >/dev/null 2>&1; then
        gcloud iam service-accounts delete "$email" --quiet
    fi
done

# ---- 7. Project (gated) ----
if [[ "${DELETE_PROJECT:-0}" == "1" ]]; then
    echo "==> Deleting project ${PROJECT_ID} (DELETE_PROJECT=1, IRREVERSIBLE)"
    gcloud projects delete "$PROJECT_ID" --quiet
else
    echo "==> Project ${PROJECT_ID} retained (set DELETE_PROJECT=1 to delete)"
fi

echo
echo "==> Teardown complete."
echo "    Idle cost should now be ≤ \$1/month (mostly bucket retention if kept)."
