# System Design: Multimodal RAG over an Astronomy Textbook (NotebookLM-style)

> **Project Positioning.** Personal portfolio project designed to (1) master the Vertex AI product surface end-to-end, (2) demonstrate production-grade architectural thinking aligned with the Google Cloud Well-Architected Framework, and (3) serve as a substantive talking point in future interviews. Cost is actively managed: components are either scale-to-zero, bounded by free tier, or **designed-and-documented without being enforced** (with that trade-off stated explicitly).

---

## 1. Executive Summary

A **NotebookLM-style** Retrieval-Augmented Generation system over an **introductory astronomy textbook** — OpenStax *Astronomy 2e* (Fraknoi, Morrison, Wolff, 2026; CC BY-NC-SA 4.0). The 1,151-page textbook is split into 4 thematic parts (Foundations / Solar System / Stars / Galaxies & Cosmology) so users can scope queries to specific subject areas, NotebookLM-style. Users ask natural-language questions — *"How did Kepler derive elliptical orbits from Brahe's Mars data?"*, *"How does the redshift concept introduced in Ch. 5 apply to Hubble's law in Ch. 26?"* — and receive answers grounded in the actual text with precise chapter/page citations.

Delivered in **two phases**:

- **Phase 1 — Managed:** End-to-end pipeline on Vertex AI Search (Agent Builder) and Gemini. Goal: ship fast, establish baseline metrics, become fluent with the managed Vertex AI surface.
- **Phase 2 — Self-built:** Replace each managed "black box" (chunking, embedding, vector store, retrieval, reranking) with first-principles implementations on other GCP primitives (Cloud SQL + pgvector, Document AI, direct embedding API). Goal: internalize the mechanics, produce a direct A/B comparison on cost / latency / retrieval quality.

Both phases share the same generation model (Gemini 2.5), the same evaluation harness, and the same observability stack — so differences are attributable to the retrieval layer.

See [phase1-managed.md](./phase1-managed.md) and [phase2-selfbuilt.md](./phase2-selfbuilt.md) for implementation detail.

---

## 2. Problem Statement

Reading a long-form textbook is hard to search: a learner remembers a concept but not which chapter or page covered it. Keyword search (`Ctrl+F`) misses paraphrases and cross-chapter conceptual connections. LLMs know *about* astronomy but hallucinate specific quantitative claims, observational dates, and named constants — and cannot cite the textbook itself. Traditional text-only RAG also loses information in **diagrams, plots, spectra, H-R diagrams, and astronomical charts** that an astronomy textbook depends on.

This project builds a personal study engine over a college-level astronomy textbook that:
- Answers questions **grounded in the actual text** (no hallucination, always cited to part + chapter + page).
- Handles **multimodal content** (figures, diagrams, plots, spectra) in the source PDFs.
- Runs on a **cost-controlled personal GCP footprint** while demonstrating enterprise-architecture thinking.
- **Respects the corpus license**: every digital page that surfaces OpenStax content includes the required CC BY-NC-SA 4.0 attribution string.

---

## 3. Requirements

### 3.1 Functional Requirements (FR)

| ID | Requirement |
|---|---|
| FR-1 | Ingest textbook PDFs (OpenStax *Astronomy 2e*, split into 4 parts of ~220–320 pages each) from a GCS bucket on upload. |
| FR-2 | Extract and index text, tables, figures, and diagrams with structure awareness (book part / chapter / section / page). |
| FR-3 | Semantic retrieval with top-k relevant chunks, including hybrid (BM25 + vector) in Phase 2. |
| FR-4 | Every generated answer MUST include citations linking to **book part → chapter → page** (and bounding region in Phase 2), and surface the OpenStax CC BY-NC-SA attribution string. |
| FR-5 | Optional scoping: user can restrict a query to specific parts of the textbook (NotebookLM-style "source selection"). |
| FR-6 | Angular web UI: 3-pane layout (left: parts/chapters tree, center: query + streaming answer with inline citations, right: PDF preview jumping to cited page). |
| FR-7 | Offline evaluation harness producing faithfulness / answer-relevance / context-precision scores over a golden Q&A set derived from the corpus. |

### 3.2 Non-Functional Requirements (NFR)

Mapped to **Well-Architected Framework** pillars — see [§7](#7-well-architected-framework-alignment).

| ID | Pillar | Requirement |
|---|---|---|
| NFR-1 | Security | Least-privilege IAM; no long-lived keys; private connectivity to Google APIs; data residency within a single region. |
| NFR-2 | Reliability | Idempotent ingestion; retries with backoff; graceful degradation when Gemini is rate-limited. |
| NFR-3 | Cost | ≤ $15/month idle cost; scale-to-zero for all compute; budget alert at $30/month. |
| NFR-4 | Performance | p95 end-to-end query latency < 6 s (warm); time-to-first-token < 2 s. |
| NFR-5 | Operational Excellence | Reproducible setup via scripted `gcloud` runbook + Cloud Build CI/CD; structured logs + SLO dashboard. |
| NFR-6 | Sustainability | Prefer `us-central1` (low-carbon); shut down non-prod resources off-hours. |

---

## 4. Architecture Overview

### 4.1 Projects & Network Topology (Shared VPC Pattern)

Designed as a **Shared VPC** topology — the PCA-canonical enterprise pattern. For this personal project, the design is documented and **deployed into a single project** to avoid the cost and Org Policy overhead of a real multi-project setup. The separation is preserved conceptually (and in the `gcloud` setup runbook organization) so it can be promoted to real Shared VPC later.

```
┌─────────────────────────────────────────────────────────────────┐
│ Host Project (design-time; collapsed into single project at run)│
│   - Shared VPC                                                  │
│   - Subnets (Cloud Run connector, Cloud SQL, proxy)             │
│   - Cloud NAT, Firewall rules, Private Service Connect endpts   │
│   - VPC Service Controls perimeter (DRY-RUN mode only)          │
└──────────────────┬──────────────────────────────────────────────┘
                   │ Shared VPC attachment (design)
       ┌───────────┴────────────┐
       ▼                        ▼
┌──────────────────┐    ┌──────────────────┐
│ Service Project  │    │ Service Project  │
│  "app"           │    │  "data"          │
│  - Cloud Run     │    │  - GCS buckets   │
│  - Cloud Build   │    │  - Cloud SQL     │
│  - Artifact Reg  │    │  - Vertex AI     │
└──────────────────┘    └──────────────────┘
```

 being able to articulate *why* Shared VPC exists (centralized network governance, separation of network admin from app admin, quota pooling) is a PCA-exam staple.

### 4.2 Data Layer

- **GCS** — landing zone (`gs://<proj>-rag-raw/`), organized by domain folder. **UBLA** enabled, **CMEK** in design (CMEK enabled only if budget permits, otherwise Google-managed keys with rationale documented).
- **Cloud SQL for PostgreSQL 16 + pgvector** (Phase 2) — vector store. `db-f1-micro` / smallest tier, private IP only, automated backups, point-in-time recovery.
- **Vertex AI Search Datastore** (Phase 1) — managed chunking + embedding + index.

### 4.3 AI & Search Layer

- **Phase 1:** Vertex AI Search (Agent Builder) handles parsing, chunking, embedding, indexing, retrieval.
- **Phase 2:**
  - **Document AI Layout Parser** for structure-aware PDF parsing (returns blocks with bounding boxes).
  - **`text-embedding-005`** (768-dim) via Vertex AI Embedding API for text chunks.
  - **Gemini 2.5 Flash Vision** to generate captions for image/diagram chunks; captions embedded alongside text.
  - **pgvector** with HNSW index for ANN search.
  - **Hybrid retrieval**: BM25 (Postgres `tsvector`) + vector ANN, fused via **Reciprocal Rank Fusion (RRF)**.
  - **Reranking**: Gemini 2.5 Flash as LLM reranker on top-20 → top-5 (scale-to-zero; no long-running rerank service).
- **Generation (both phases):** Gemini 2.5 Flash by default; Gemini 2.5 Pro for queries flagged as complex by the Router (see §4.5).

### 4.4 Compute & Interface Layer

- **Cloud Run** (min-instances=0) hosts three services:
  - `api` — FastAPI (Python), orchestrates retrieval + generation, exposes streaming `/query` via Server-Sent Events.
  - `worker` — Python, Eventarc-triggered ingestion pipeline.
  - `web` — **Angular** (latest stable, standalone components + signals + new control flow) SPA served behind the same Cloud Run service using a slim nginx container (`dist/` static files). NotebookLM-style three-pane layout.
- **Serverless VPC Access connector** for Cloud Run → Cloud SQL private IP.
- **Global External HTTPS Load Balancer** routes `/` → `web`, `/api/*` → `api` via path-based URL maps; **Cloud Armor** policy attached in **preview mode** only (no enforcement → no Enterprise-tier cost).
- **Artifact Registry** for container images (Angular build + two Python services); **Cloud Build** for CI/CD with Workload Identity Federation from GitHub Actions (no service account keys).

### 4.5 Inference Control Plane

- **Router** (deterministic, not LLM-based — cheaper and explainable):
  - Default → Gemini 2.5 Flash.
  - Escalate to Gemini 2.5 Pro if any of: (a) retrieved context includes ≥1 image/diagram chunk, (b) query contains explicit visual keywords (`diagram`, `architecture`, `chart`, `图`, `架构`), (c) retrieved top-1 similarity < threshold (low-confidence retrieval).
  - Decisions are logged as structured events for later analysis.
- **Grounding guardrails**: prompt enforces "answer only from provided context; otherwise say 'I don't know'"; post-generation check that every `[n]` citation corresponds to a returned chunk.
- **LLM-as-judge is offline only** (in eval harness). On the hot path we use lightweight citation validation to avoid doubling per-query cost.

### 4.6 Data Synchronization Pipeline

```
GCS (PDF upload) → Eventarc → Cloud Run Worker → [Parse → Chunk → Embed → Upsert]
                                   │
                                   └─ DLP inspection (API mode, on-demand; not continuous)
```

Idempotency keyed by `(gcs_object, generation)`; re-upload triggers upsert, not duplicate.

### 4.7 MLOps & Evaluation

- **Vertex AI Pipelines** (Kubeflow SDK) for the evaluation workflow: load golden Q&A set → run retrieval → run generation → compute RAGAS metrics → publish run card. Runs on-demand (not scheduled), so cost is only incurred on eval runs.
- **Golden dataset** versioned in GCS (`gs://<proj>-rag-eval/golden/v{n}.jsonl`).
- **CI gate**: PRs that touch retrieval/prompt code trigger an eval run in Cloud Build; merge requires faithfulness ≥ baseline − 2%.
- **Model/config versioning**: prompt templates, chunking params, and embedding model version all stored in a single YAML registry; every eval run pins a version and logs it.

---

## 5. Two-Phase Implementation Strategy

### 5.1 Component Comparison Matrix

| Component | Phase 1 (Managed) | Phase 2 (Self-built) | Core concept learned |
|---|---|---|---|
| PDF parsing | Vertex AI Search built-in | Document AI Layout Parser + `pymupdf` fallback | Layout-aware parsing; bbox-based citation; detect chapter headings |
| Chunking | Auto | Recursive + semantic + **chapter/section-aware**, with overlap | Chunk boundaries respect textbook structure; size/overlap trade-offs |
| Metadata | Auto | Explicit: `book_id` (textbook part), `authors`, `chapter`, `section`, `page` | Metadata-filtered retrieval (part scoping) |
| Embedding | Managed | `text-embedding-005` API, batched | Batching, retries, dim choice |
| Vector store | Black box | **Cloud SQL + pgvector** (HNSW) | ANN indexes, metadata filters, vector + SQL joins |
| Retrieval | Vector only | **Hybrid (BM25 + vector) + RRF** | Sparse vs dense; proper-noun recall (names/places/dates) |
| Multimodal | Layout-aware | Gemini Vision → figure/diagram caption → embed caption | Multimodal embedding vs description-based |
| Reranking | None (implicit) | Gemini Flash as LLM reranker | Cross-encoder vs LLM rerank trade-off |
| Orchestration | Discovery Engine SDK | Hand-written (no LangChain) | Prompt assembly, citation injection |
| Generation | Gemini 2.5 | Gemini 2.5 | *(kept identical for fair comparison)* |
| Eval / Obs | Self-built | Self-built | *(kept identical for fair comparison)* |

### 5.2 What the comparison is designed to show

By keeping generation and evaluation identical and varying only the retrieval stack, the A/B lets us attribute differences in faithfulness, context precision, latency, and cost to specific retrieval decisions. Expected findings to validate or refute:

- **Hypothesis H1:** Hybrid retrieval (Phase 2) improves context precision on queries containing rare scientific proper nouns and named entities (Chandrasekhar, Carrington Event, Cepheid variable, Schwarzschild radius) by ≥ 10%.
- **Hypothesis H2:** LLM reranking reduces "irrelevant chunk" contamination but adds 500–1500 ms latency.
- **Hypothesis H3:** Phase 2 per-query cost is lower at steady state; Phase 1 is lower at low QPS due to no Cloud SQL idle cost — crossover around ~X QPS.
- **Hypothesis H4:** Chapter/section-aware chunking (Phase 2) improves context recall on "in Chapter X" / "in Section X.Y" style queries vs Phase 1's auto chunking.

---

## 6. Technology Choices

| Component | Technology | Rationale |
|---|---|---|
| Generation | Gemini 2.5 Flash (default), 2.5 Pro (escalated) | Flash covers 90%+ of RAG-shaped queries at ~1/10 cost of Pro. |
| Embedding | `text-embedding-005` (768-dim) | Latest Vertex embedding model; 768 dims balances quality vs storage. Handles modern technical English (textbook prose with scientific terminology) — verified on eval set. |
| Vector store (Phase 2) | Cloud SQL + pgvector | Cheapest production-viable option; allows JOINs with part/chapter metadata for scoped queries; same `psycopg` workflow engineers already know. |
| Parsing (Phase 2) | Document AI Layout Parser | Returns blocks with bounding boxes → enables precise citation highlighting and chapter-heading detection. |
| Orchestration | FastAPI + direct SDK calls | Explicit control over prompt assembly and citation logic; no framework magic to debug in interviews. |
| Backend framework | FastAPI (Python 3.12) | Async SSE support for streaming answers; type-safe; same ecosystem as Vertex AI SDK. |
| Frontend framework | Angular (latest stable) — standalone components, signals, new control flow | User's explicit choice; Material UI for Google-native look; `ng-pdf-viewer` or pdf.js for PDF pane. |
| Infrastructure management | **Console-driven with `gcloud` runbook** (`infra/setup.md` + `infra/scripts/*.sh`) | Personal project — no Terraform overhead. Every Console action is mirrored by a `gcloud` command in the runbook so the setup is reproducible and demonstrable. Promote to Terraform/Pulumi if the project grows. |
| CI/CD | Cloud Build + GitHub Actions (WIF) | Keyless auth; PCA-aligned. |

---

## 7. Well-Architected Framework Alignment

### 7.1 Operational Excellence
- **Reproducible setup**: `infra/setup.md` is the single source of truth; every Console action mirrored by a committed `gcloud` command. A fresh GCP project can be brought up by following the runbook top-to-bottom. Helper shell scripts in `infra/scripts/` for repeat operations (start/stop Cloud SQL, redeploy services, rotate images).
- **Application code in Git** — FastAPI, Angular, worker pipelines, eval harness, and the runbook itself all version-controlled.
- Structured JSON logs to Cloud Logging; log-based metrics for token usage and retrieval latency.
- SLO dashboard in Cloud Monitoring (latency, error rate, eval score trend).
- Runbooks for common failures (Gemini quota, Cloud SQL failover, bad ingestion).
- **Interview honesty:** Terraform is the right answer at team scale, but for a solo project a disciplined `gcloud` runbook is faster to author, cheaper (no state bucket lifecycle, no provider churn), and still reproducible. The runbook is itself the demonstrable artifact.

### 7.2 Security
- **Identity**: per-service SA, least privilege. Human access via Google identity only; no SA keys issued. GitHub → GCP via **Workload Identity Federation**.
- **Network**: Shared VPC design (single-project collapsed for cost); Cloud Run → Cloud SQL via private IP only; Google APIs reached via **Private Service Connect** endpoints.
- **Perimeter**: **VPC Service Controls** perimeter **in dry-run mode** around Vertex AI / GCS / Cloud SQL. Violations logged and reviewed; no enforcement (to allow free-tier tooling to function).
- **Data**: UBLA on all buckets; CMEK designed, Google-managed keys used at runtime (budget); DLP on-demand scan hook before indexing.
- **Edge**: Cloud Armor policy attached in **preview mode** (OWASP top-10 + rate limit rules logged but not enforced).

### 7.3 Reliability
- Stateless Cloud Run services; Cloud SQL HA disabled in personal env but **documented HA enable command** in the runbook (one `gcloud sql instances patch --availability-type=REGIONAL` away).
- Eventarc → Cloud Run with at-least-once delivery; ingestion is idempotent.
- Retries with exponential backoff on all external API calls; circuit breaker around Gemini.

### 7.4 Cost Optimization
- Everything scale-to-zero: Cloud Run min-instances=0, no Vertex AI endpoints (use API), no GKE.
- Cloud SQL `db-f1-micro`, start-stop script for non-active weeks.
- Budget + alert at $30/month; label every resource with `env=personal` for attribution.
- Embedding cache (Redis-free: store `hash(chunk_text) → vector` in a GCS JSON) to avoid re-embedding on redeploy.
- See [phase1-managed.md §Cost](./phase1-managed.md) and [phase2-selfbuilt.md §Cost](./phase2-selfbuilt.md) for phase-specific estimates.

### 7.5 Performance Efficiency
- Region pinned to `us-central1` (proximity to Vertex AI, low carbon, lowest egress).
- Gemini streaming responses; TTFT < 2s target.
- pgvector HNSW tuned (`m=16, ef_construction=64, ef_search=40`); validated against recall target in eval harness.
- Query embedding cache for repeated questions (24h TTL).

### 7.6 Sustainability
- Low-carbon region selection (`us-central1`).
- Scale-to-zero eliminates idle emissions.
- Eval pipeline runs on-demand, not nightly cron.

---

## 8. Security Design Deep-Dive

### 8.1 IAM & Service Accounts

| Service Account | Purpose | Key Roles |
|---|---|---|
| `sa-run-api` | Cloud Run API service | `roles/aiplatform.user`, `roles/cloudsql.client`, `roles/secretmanager.secretAccessor` |
| `sa-run-worker` | Ingestion worker | `roles/storage.objectViewer` (raw bucket only), `roles/aiplatform.user`, `roles/cloudsql.client` |
| `sa-run-web` | Angular static-serving Cloud Run | No GCP roles needed (only serves static files); allow unauthenticated invocations through the LB only |
| `sa-cloudbuild` | CI/CD | `roles/run.admin`, `roles/artifactregistry.writer`, scoped to app project |
| `sa-setup` | Admin (runbook) | Elevated; **impersonated via `gcloud` `--impersonate-service-account`**, no keys issued |

**IAM Conditions** applied: `sa-run-worker` storage access restricted to bucket prefix; `sa-run-api` restricted to specific Vertex AI resources. Human admin access uses **`gcloud` impersonation** of `sa-setup` — no exported keys, no long-lived credentials.

### 8.2 Network

- Private IP on Cloud SQL; no public IP anywhere except the LB.
- Cloud NAT for egress from Cloud Run connector subnet (only used when Cloud Run needs to reach external HTTPS, e.g. GitHub webhooks).
- Private Service Connect endpoints for `googleapis.com` from the VPC.
- Firewall rules: default-deny egress; explicit allow to `restricted.googleapis.com`, Cloud SQL subnet, internal health checks.

### 8.3 VPC Service Controls (Dry-Run Design)

Perimeter includes: Vertex AI, Cloud Storage, Cloud SQL, Artifact Registry. Ingress rule allows identities on `sa-run-*` from the Cloud Run source. Egress rule denies all by default; explicit allow for Gemini API via PSC. **Operated in dry-run:** violations land in `_Default` log bucket under `protoPayload.metadata.dryRun=true` and are reviewed weekly. Enforcement is one `gcloud access-context-manager perimeters update --policy=... --dry-run=false` away, with the exact command committed in `infra/setup.md`.

### 8.4 Data Protection

- **CMEK** configured for GCS + Cloud SQL (design); Google-managed keys used at runtime unless budget permits.
- **Secret Manager** for all credentials; access via SA, no env-var secrets.
- **DLP** inspection template configured; called on-demand from worker before indexing documents from untrusted sources.

---

## 9. Cost Analysis (Target: ≤ $15/month idle, ≤ $50/month active)

| Component | Idle | Active (100 queries/day) | Notes |
|---|---|---|---|
| Cloud Run (all services) | $0 | ~$2 | scale-to-zero |
| Cloud SQL (db-f1-micro) | ~$8 | ~$8 | largest fixed cost in Phase 2 |
| GCS storage | ~$0.50 | ~$1 | small PDF corpus |
| Artifact Registry | ~$0.10 | ~$0.10 | |
| Vertex AI Search (Phase 1) | $0 | ~$5–15 | per-query; see phase1-managed.md |
| Embedding API | $0 | < $1 | cached |
| Gemini 2.5 Flash | $0 | ~$2 | default path |
| Gemini 2.5 Pro | $0 | ~$1 | router-gated |
| Cloud Logging/Monitoring | $0 | ~$0.50 | within free tier |
| **Total** | **~$10** | **~$20–30** | |

Budget alert at $30/month. Cloud SQL has a `stop` script for long idle periods.

---

## 10. Implementation Roadmap

### Phase 0 — Corpus prep *(target: 1 evening, prerequisite)*
1. Download OpenStax *Astronomy 2e* PDF (CC BY-NC-SA 4.0). Split into 4 thematic parts (~220–320 pages each) corresponding to Chapters 1–6 / 7–14 / 15–24 / 25–30. Each part gets its own GCS path and `meta.json`.
2. Verify the PDF contains a real text layer (`pdftotext` smoke test) and that chapter/section headings parse cleanly.
3. Author 30–50 golden Q&A pairs covering: factual lookup, chapter-scoped reasoning, cross-topic comparison (multi-chapter), figure/diagram questions (H-R diagram, electromagnetic spectrum, galaxy classification). Commit to `eval/golden/v1.jsonl`.

### Phase 1 — Managed MVP *(target: 2 weeks, evenings)*
1. GCP project bootstrap via `infra/setup.md` runbook: APIs, GCS, IAM, single VPC, service accounts.
2. Vertex AI Search datastore + ingestion from GCS.
3. FastAPI `api` service calling Discovery Engine SDK with SSE streaming.
4. **Angular** web SPA: 3-pane NotebookLM layout (textbook parts tree / query+answer / PDF preview); deployed as third Cloud Run service via nginx image.
5. Structured logging + basic Cloud Monitoring dashboard.
6. Run eval harness over golden set → baseline RAGAS scores in `eval/runs/phase1-v1.md`.
7. Document baseline cost and latency.

### Phase 2 — Self-built *(target: 4 weeks, evenings)*
1. Provision Cloud SQL + pgvector via runbook: private IP, VPC connector, backups.
2. Ingestion worker v2: Document AI → chapter/section detection → chunking → embedding → upsert.
3. Hybrid retrieval (BM25 + vector + RRF) + LLM reranker.
4. Multimodal: Gemini Vision captioning for maps/figures; cache captions in GCS.
5. Router + grounding guardrails.
6. Angular: upgrade PDF pane with bbox-highlighting of cited region.
7. Run eval harness in CI; publish A/B comparison report.

### Phase 3 — Hardening & MLOps *(target: 1–2 weeks)*
1. Vertex AI Pipelines for eval workflow.
2. Cloud Armor preview mode, VPC-SC dry-run.
3. Workload Identity Federation for CI.
4. SLO dashboards + alerting policies.
5. Write-up: architecture post-mortem + interview-ready summary + ADRs.

---

## 11. Open Questions / Future Work

- **Incremental indexing at scale:** current design re-embeds on every upload. For 10k+ docs, add a content-hash check before re-embedding.
- **Multi-tenancy:** not in scope; would require row-level security in Cloud SQL or per-tenant datastores in Phase 1.
- **Fine-tuning:** deferred; out of scope for cost reasons. Would revisit with Gemini supervised tuning if eval plateaus.
- **Agentic extensions:** the current system is single-turn RAG. Tool-using agent mode (e.g., "search + summarize + draft email") is a natural Phase 4 but deliberately deferred.
