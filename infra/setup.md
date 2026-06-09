# Phase 1 Infrastructure Runbook (gcloud)

This is the source-of-truth runbook for bringing up the Phase 1 GCP environment
from scratch. Every Console action is mirrored here as a copy-pasteable
`gcloud` command. Each section ends with a verification command you can run to
confirm the step succeeded.

> **Cost expectation**: idle ~$1/month, 100 q/day ~$10–20/month. Hard cap via
> the budget alert in §12. Tear down with `infra/scripts/destroy.sh` between
> dev sessions to keep idle cost near zero.

---

## 0. Variables — set these once per shell

Set these at the top of your terminal session before running any command in
this runbook. Pin the values; don't change them mid-runbook.

```bash
# Replace ANKI-RAG-DOCS with a globally-unique project ID (3-30 chars, lowercase, digits, hyphens)
export PROJECT_ID="anki-rag-docs"
export PROJECT_NAME="Anki RAG Docs (Phase 1)"
export BILLING_ACCOUNT="$(gcloud beta billing accounts list --format='value(ACCOUNT_ID)' --filter='OPEN=True' | head -1)"

export REGION="us-central1"
export LOCATION_DISCOVERY="us"            # Vertex AI Search uses 'us' / 'eu' / 'global'
export LOCATION_AI="us-central1"

# Service-account names (no @suffix; suffix appended below)
export SA_API="sa-run-api"
export SA_WORKER="sa-run-worker"
export SA_WEB="sa-run-web"
export SA_BUILD="sa-cloudbuild"
export SA_SETUP="sa-setup"

# Storage buckets (must be globally unique)
export BUCKET_RAW="${PROJECT_ID}-rag-raw"
export BUCKET_EVAL="${PROJECT_ID}-rag-eval"
export BUCKET_ARTIFACTS="${PROJECT_ID}-rag-artifacts"

# Vertex AI Search
export DATASTORE_ID="astronomy-2e-datastore"
export ENGINE_ID="astronomy-2e-engine"
```

**Verify**: `echo $PROJECT_ID $BILLING_ACCOUNT $REGION` — none should be empty.

---

## 1. Project & APIs

```bash
# Create the project (idempotent: skips if it exists)
gcloud projects create "$PROJECT_ID" --name="$PROJECT_NAME" || true
gcloud config set project "$PROJECT_ID"

# Link a billing account (REQUIRED — APIs won't enable without billing)
gcloud beta billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"

# Enable the 12 APIs we need across Phase 1
gcloud services enable \
    run.googleapis.com \
    eventarc.googleapis.com \
    discoveryengine.googleapis.com \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    logging.googleapis.com \
    monitoring.googleapis.com \
    secretmanager.googleapis.com \
    iam.googleapis.com \
    iamcredentials.googleapis.com
```

**Verify**:
```bash
gcloud services list --enabled --format='value(NAME)' | grep -E 'run|discovery|aiplatform' | wc -l
# Expect ≥ 3
```

---

## 2. Service accounts & IAM

```bash
# Create the 5 service accounts
for sa in $SA_API $SA_WORKER $SA_WEB $SA_BUILD $SA_SETUP; do
    gcloud iam service-accounts create "$sa" \
        --display-name="$sa" \
        --description="Phase 1 SA: $sa" || true
done

# Grant least-privilege roles
# api: read Discovery Engine + invoke Vertex AI for generation
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_API}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/discoveryengine.viewer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_API}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# worker: read GCS, write to Discovery Engine datastores, write logs
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_WORKER}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.objectViewer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_WORKER}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/discoveryengine.editor"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_WORKER}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter"

# cloudbuild: build images + push to Artifact Registry + deploy Cloud Run
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/cloudbuild.builds.builder"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/run.developer"
```

**Verify**:
```bash
gcloud iam service-accounts list --filter="email:sa-*@${PROJECT_ID}.iam.gserviceaccount.com" --format='value(email)' | wc -l
# Expect 5
```

---

## 3. Networking (single VPC, deferred to enterprise mode)

For Phase 1 personal scale, default network is sufficient. The full
Shared-VPC + private endpoint setup is documented but deferred until needed.

```bash
# Confirm default network exists (it does on a fresh project)
gcloud compute networks list --filter="NAME=default" --format='value(NAME)'

# Optional: enable Private Service Connect for googleapis.com
# (defer to Phase 2 when Cloud SQL needs private IP)
```

**Verify**:
```bash
gcloud compute networks list --format='value(NAME)' | head -3
# Expect 'default' present
```

---

## 4. GCS buckets

```bash
# Raw corpus bucket — UBLA + versioning + 30-day lifecycle on noncurrent versions
gcloud storage buckets create "gs://${BUCKET_RAW}" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention

gcloud storage buckets update "gs://${BUCKET_RAW}" --versioning

# Lifecycle: delete noncurrent versions after 30 days
cat > /tmp/lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {"action": {"type": "Delete"}, "condition": {"daysSinceNoncurrentTime": 30}}
    ]
  }
}
EOF
gcloud storage buckets update "gs://${BUCKET_RAW}" --lifecycle-file=/tmp/lifecycle.json

# Eval results bucket
gcloud storage buckets create "gs://${BUCKET_EVAL}" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention

# Artifacts bucket (build cache, eval reports)
gcloud storage buckets create "gs://${BUCKET_ARTIFACTS}" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
```

**Verify**:
```bash
gcloud storage buckets list --format='value(name)' | grep -c "${PROJECT_ID}-rag"
# Expect 3
```

---

## 5. Artifact Registry (Docker repo)

```bash
gcloud artifacts repositories create rag-docs \
    --repository-format=docker \
    --location="$REGION" \
    --description="Phase 1 container images: api, worker, web"

# Configure Docker to authenticate to Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
```

**Verify**:
```bash
gcloud artifacts repositories list --location="$REGION" --format='value(name)' | grep rag-docs
```

---

## 6. Vertex AI Search datastore + corpus upload

This is the core retrieval backend.

### 6a. Upload PDFs to GCS (corpus prep)

```bash
# Copy the local OpenStax PDF + meta.json to the raw bucket
gcloud storage cp \
    "pdfs/astronomy-2e.pdf" \
    "gs://${BUCKET_RAW}/books/openstax-astronomy-2e/openstax-astronomy-2e.pdf"

# Create a meta.json (you may already have it; otherwise generate it)
cat > /tmp/meta.json <<EOF
{
  "book_id": "openstax-astronomy-2e",
  "title": "Astronomy 2e",
  "authors": ["Andrew Fraknoi", "David Morrison", "Sidney C. Wolff"],
  "year": 2026,
  "license": "CC BY-NC-SA 4.0",
  "source_url": "https://openstax.org/details/books/astronomy-2e",
  "page_count": 1151
}
EOF
gcloud storage cp /tmp/meta.json "gs://${BUCKET_RAW}/books/openstax-astronomy-2e/meta.json"
```

### 6b. Create the Vertex AI Search datastore

Vertex AI Search is at the time of writing primarily managed via the Console
or the REST API; some `gcloud` surface exists under `alpha discovery-engine`.

```bash
# Datastore creation via REST API (most reliable surface in 2026)
ACCESS_TOKEN=$(gcloud auth print-access-token)
curl -X POST \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/dataStores?dataStoreId=${DATASTORE_ID}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "displayName": "Astronomy 2e datastore",
      "industryVertical": "GENERIC",
      "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
      "contentConfig": "CONTENT_REQUIRED"
    }'

# Trigger document import from GCS — layout parser handles PDFs
curl -X POST \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/dataStores/${DATASTORE_ID}/branches/0/documents:import" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"gcsSource\": {
        \"inputUris\": [\"gs://${BUCKET_RAW}/books/openstax-astronomy-2e/openstax-astronomy-2e.pdf\"],
        \"dataSchema\": \"content\"
      },
      \"reconciliationMode\": \"FULL\"
    }"
```

### 6c. Create the search engine that fronts the datastore

```bash
curl -X POST \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/collections/default_collection/engines?engineId=${ENGINE_ID}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"displayName\": \"Astronomy 2e search engine\",
      \"solutionType\": \"SOLUTION_TYPE_SEARCH\",
      \"searchEngineConfig\": {\"searchTier\": \"SEARCH_TIER_STANDARD\"},
      \"dataStoreIds\": [\"${DATASTORE_ID}\"]
    }"
```

**View in Console** (no menu path — direct URL only):
```
https://console.cloud.google.com/gen-app-builder/engines?project=${PROJECT_ID}
```
Console UI lives under "AI Applications" / "Agent Builder" / "gen-app-builder"
depending on which version you find. The URL above is the most reliable entry
point — `Console → AI menu → ...` does not lead here in 2026 builds.

Inside the engine page:
- **Preview** tab — interactive search query against the engine, no API call needed
- **Configurations** — engine settings, attached datastore
- **Activity** (on the datastore page) — import operation status

Datastores live at:
```
https://console.cloud.google.com/gen-app-builder/data-stores?project=${PROJECT_ID}
```

**Verify** (indexing is asynchronous — wait 5–30 minutes):
```bash
# Check import operation
curl -s \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/dataStores/${DATASTORE_ID}/branches/0/operations" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    | python3 -m json.tool | head -30

# Once done, smoke-test a search
curl -X POST \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/collections/default_collection/engines/${ENGINE_ID}/servingConfigs/default_search:search" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d '{"query": "Kepler third law", "pageSize": 5}'
# Expect a JSON response with `results` array containing chunks of OpenStax content
```

---

## 7. Eventarc trigger (auto re-ingest on PDF upload)

```bash
# Trigger fires when objects are finalized in the raw bucket
gcloud eventarc triggers create rag-ingest-trigger \
    --location="$REGION" \
    --destination-run-service="worker" \
    --destination-run-region="$REGION" \
    --event-filters="type=google.cloud.storage.object.v1.finalized" \
    --event-filters="bucket=${BUCKET_RAW}" \
    --service-account="${SA_WORKER}@${PROJECT_ID}.iam.gserviceaccount.com"
```

(Note: requires the worker Cloud Run service from §8 to exist first; you may
do §8 then come back to §7.)

**Verify**:
```bash
gcloud eventarc triggers list --location="$REGION" --format='value(name)'
```

---

## 8. Cloud Run services (api, web, worker)

```bash
# Build and push images via Cloud Build
gcloud builds submit api/ \
    --tag="${REGION}-docker.pkg.dev/${PROJECT_ID}/rag-docs/api:latest" \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud builds submit web/ \
    --tag="${REGION}-docker.pkg.dev/${PROJECT_ID}/rag-docs/web:latest" \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com"

# Deploy api
gcloud run deploy api \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/rag-docs/api:latest" \
    --region="$REGION" \
    --service-account="${SA_API}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --min-instances=0 --max-instances=3 \
    --set-env-vars="RETRIEVAL_BACKEND=discovery_engine,GCP_PROJECT_ID=${PROJECT_ID},DISCOVERY_ENGINE_LOCATION=${LOCATION_DISCOVERY},DISCOVERY_ENGINE_ID=${ENGINE_ID}" \
    --no-allow-unauthenticated \
    --timeout=3600

# Deploy web (nginx + Angular dist)
gcloud run deploy web \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/rag-docs/web:latest" \
    --region="$REGION" \
    --service-account="${SA_WEB}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --min-instances=0 --max-instances=3 \
    --no-allow-unauthenticated

# Worker is built when needed for Phase 1 (thin trigger handler)
```

**Verify**:
```bash
gcloud run services list --region="$REGION" --format='value(SERVICE)'
# Expect: api, web (worker if built)
```

---

## 9. Load Balancer + Cloud Armor (optional for Phase 1)

For Phase 1, direct Cloud Run URLs suffice. The full HTTPS LB + URL map +
Cloud Armor preview is documented in `phase1-managed.md §3.1` but skipped
here for cost — flip it on when going public.

---

## 10. Logging & Monitoring

```bash
# Log-based metrics for query latency, cost estimate, citation failures
gcloud logging metrics create rag_query_latency_ms \
    --description="Phase 1 RAG query latency distribution" \
    --log-filter='resource.type="cloud_run_revision" AND jsonPayload.event="query_complete"' \
    --value-extractor='EXTRACT(jsonPayload.total_ms)' \
    --metric-descriptor-metric-kind=DELTA \
    --metric-descriptor-value-type=DISTRIBUTION

gcloud logging metrics create rag_citation_validation_failures \
    --description="Citations that failed [n] validation" \
    --log-filter='resource.type="cloud_run_revision" AND jsonPayload.event="citation_validation_failure"'

# Alert: error rate > 5% for 10 min — define via Console or YAML upload
# (long YAML omitted from this runbook; see infra/monitoring/alerts.yaml)

# Alert: daily cost > $2 — see §12
```

---

## 11. Workload Identity Federation (CI keyless auth)

```bash
gcloud iam workload-identity-pools create github \
    --location=global \
    --display-name="GitHub Actions WIF pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
    --location=global \
    --workload-identity-pool=github \
    --display-name="GitHub OIDC provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --issuer-uri="https://token.actions.githubusercontent.com"

# Bind to a specific repo (replace YOUR_GH_USER/REPO)
gcloud iam service-accounts add-iam-policy-binding \
    "${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/github/attribute.repository/YOUR_GH_USER/REPO"
```

**Verify**:
```bash
gcloud iam workload-identity-pools list --location=global --format='value(name)'
```

---

## 12. Budget alert ($30/month)

```bash
# Requires the Cloud Billing Budgets API (enable if not yet)
gcloud services enable billingbudgets.googleapis.com

# Use the gcloud beta billing budgets command (or Console)
gcloud beta billing budgets create \
    --billing-account="$BILLING_ACCOUNT" \
    --display-name="Phase 1 RAG monthly cap" \
    --budget-amount=30USD \
    --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 \
    --threshold-rule=percent=1.0 \
    --filter-projects="projects/${PROJECT_ID}"
```

**Verify**:
```bash
gcloud beta billing budgets list --billing-account="$BILLING_ACCOUNT" \
    --format='value(displayName)' | grep "RAG"
```

---

## 13. Teardown — `infra/scripts/destroy.sh`

Reverse-order tear-down. Run between dev sessions to keep idle costs at $0.
The script is in `infra/scripts/destroy.sh`; key actions:

1. Delete Cloud Run services (`api`, `web`, `worker`)
2. Delete Eventarc triggers
3. Delete the search engine + datastore
4. Empty + delete GCS buckets (`-rag-raw` retained by default — set
   `DELETE_BUCKETS=1` to wipe)
5. Delete Artifact Registry repo
6. Delete service accounts (after ensuring no IAM bindings linger)
7. Disable APIs (optional — the project stays free if APIs are off)
8. Optionally delete the project itself: `gcloud projects delete $PROJECT_ID`

```bash
bash infra/scripts/destroy.sh
```

---

## Smoke test — full Phase 1 health check

After §1–§8, run this end-to-end check:

```bash
# 1. Project + APIs
gcloud config get-value project
gcloud services list --enabled --format='value(NAME)' | wc -l   # ≥ 12

# 2. SAs
gcloud iam service-accounts list --filter="email:sa-*" --format='value(email)' | wc -l   # = 5

# 3. Buckets
gcloud storage buckets list --format='value(name)' | grep -c "${PROJECT_ID}-rag"   # = 3

# 4. Vertex AI Search engine (smoke query)
curl -X POST \
    "https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_DISCOVERY}/collections/default_collection/engines/${ENGINE_ID}/servingConfigs/default_search:search" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d '{"query": "Kepler", "pageSize": 3}' \
    | python3 -m json.tool | head -40

# 5. Cloud Run services
gcloud run services list --region="$REGION" --format='value(SERVICE)'   # api, web

# 6. End-to-end: hit the deployed api with a question and check SSE flow
API_URL=$(gcloud run services describe api --region="$REGION" --format='value(status.url)')
curl -X POST "${API_URL}/api/query" \
    -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    -H "Content-Type: application/json" \
    -d '{"question": "How did Kepler discover his third law?"}' \
    --max-time 60
```

If all 6 pass, run the eval harness pointing at the cloud API:

```bash
poetry run python eval/run_eval.py \
    --api "$API_URL" \
    --golden eval/golden/v1.jsonl \
    --out eval/runs/phase1-discovery-engine-v1.md
```

This produces the **Phase 1 baseline** that Phase 2 will A/B against.

---

## Known traps (read before executing)

These are the failure modes to expect, ordered by likelihood:

1. **Billing not linked → API enable fails silently or with quota=0.** Always
   confirm `gcloud beta billing projects describe $PROJECT_ID` shows `billingEnabled: true`.

2. **Vertex AI Search indexing is async and can take 5–30 minutes** on a
   1151-page PDF. Don't assume a successful POST means the data is queryable —
   poll the operation status or just wait and retry the smoke query.

3. **`SOLUTION_TYPE_SEARCH` vs `SOLUTION_TYPE_CHAT`**: at engine creation time,
   pick `SEARCH` for our use case. Wrong type → engine can't be queried via
   the search API.

4. **`gcloud builds submit` fails with permissions error**: the Cloud Build
   default SA needs `roles/run.developer` AND ability to act-as the runtime
   SAs. See §2.

5. **Eventarc trigger requires Pub/Sub + Eventarc API enabled together** —
   both are in §1 already, but if you skip a step, it'll silently fail to fire.

6. **Cloud Run cold starts** can make the first eval-harness run timeout.
   Set `--min-instances=1` temporarily during eval, then back to 0 for cost.

7. **`destroy.sh` won't delete a datastore that's still attached to an
   engine.** Reverse order: delete engine first, then datastore.
