# Phase 2 Infrastructure Runbook (gcloud) — Cloud SQL + pgvector

Companion to [setup.md](./setup.md) (Phase 1). Every action here is a
`gcloud` command or SQL statement so the setup is reproducible. Cost
control is session-based: `scripts/sql-start.sh` / `scripts/sql-stop.sh`.

## 0. Variables

```bash
source infra/env.sh          # PROJECT_ID, REGION, SQL_INSTANCE=rag-pg
export SQL_DB="rag"
export SQL_IAM_USER="ankiyang1201@gmail.com"   # your gcloud account
```

## 1. APIs

```bash
gcloud services enable sqladmin.googleapis.com --project=$PROJECT_ID
```

## 2. Instance (M2, one-time)

```bash
# db-f1-micro shared-core, PG16, 10GB SSD, IAM auth on.
# ~5-10 min. Billing starts here (~$9/mo while running).
gcloud sql instances create $SQL_INSTANCE \
  --project=$PROJECT_ID \
  --database-version=POSTGRES_16 \
  --edition=enterprise \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-type=SSD --storage-size=10GB \
  --database-flags=cloudsql.iam_authentication=on \
  --backup-start-time=03:00
```

## 3. Database + users

```bash
gcloud sql databases create $SQL_DB --instance=$SQL_INSTANCE --project=$PROJECT_ID

# Admin password for schema work (regenerate any time with the same command)
gcloud sql users set-password postgres --instance=$SQL_INSTANCE \
  --project=$PROJECT_ID --password="$(openssl rand -base64 24)"

# IAM database user — passwordless login via IAM tokens
gcloud sql users create $SQL_IAM_USER \
  --instance=$SQL_INSTANCE --project=$PROJECT_ID --type=cloud_iam_user

# IAM side: login permission for the principal
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$SQL_IAM_USER" --role="roles/cloudsql.instanceUser"
```

## 4. Schema + grants (as postgres)

Apply `api/app/db/schema.sql` — via Cloud SQL Studio (Console → instance →
Cloud SQL Studio → paste + Run), or programmatically through the Python
connector (no psql needed). Then grant the IAM user:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO "ankiyang1201@gmail.com";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "ankiyang1201@gmail.com";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "ankiyang1201@gmail.com";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "ankiyang1201@gmail.com";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO "ankiyang1201@gmail.com";
```

Sanity checks:

```sql
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm');
-- vector must be >= 0.8 (iterative index scans, phase2-selfbuilt.md §5.1)
\d chunks
```

## 5. App configuration

```bash
# api/.env
DB_MODE=cloudsql
GCP_PROJECT_ID=multimodal-rag-engine
GCP_LOCATION=us-central1
DB_INSTANCE=rag-pg
DB_NAME=rag
DB_IAM_USER=ankiyang1201@gmail.com
```

Local dev auths via ADC (`gcloud auth application-default login`); Cloud Run
will use its service account (M6 — add an IAM db user for it then).

## 6. Session workflow (every dev day)

```bash
bash infra/scripts/sql-start.sh   # before work  (~1-2 min to RUNNABLE)
bash infra/scripts/sql-stop.sh    # after work   (storage-only billing)
```

## Known traps

1. **`cloudsql.iam_authentication=on` must be set at create time (or patch
   + restart)** — IAM users can't log in without it.
2. **IAM user needs BOTH sides**: the database user (`gcloud sql users
   create --type=cloud_iam_user`) and the IAM role
   (`roles/cloudsql.instanceUser`). Missing either → opaque auth failure.
3. **Postgres role name = full email** for user accounts (quoted in SQL);
   service accounts drop the `.gserviceaccount.com` suffix.
4. **Tables created by `postgres` aren't visible to the IAM user until
   granted** — run §4 grants after every schema change that adds tables.
5. **db-f1-micro is shared-core**: HNSW index builds are slow and
   memory-tight. If a bulk-ingest index build OOMs, temporarily
   `gcloud sql instances patch rag-pg --tier=db-g1-small`, ingest, patch back.
