# Phase 1 — Managed Implementation (Vertex AI Search + Gemini)

> **Goal.** Ship an end-to-end **NotebookLM-style** RAG system over OpenStax *Astronomy 2e* (CC BY-NC-SA 4.0), a 1,151-page college-level astronomy textbook split into thematic parts, using fully managed Vertex AI services. Produce a **baseline** (latency, cost, retrieval quality) that Phase 2 will be measured against. Resist the urge to self-optimize here — the point is to see what "Vertex AI does by default" and learn the managed surface deeply.

**Timeline:** ~2 weeks of evenings. **Cost target:** < $15/month idle, < $30/month active at 100 queries/day.

See [technical-design.md](./technical-design.md) for overall architecture and [phase2-selfbuilt.md](./phase2-selfbuilt.md) for the self-built counterpart.

---

## 1. Scope of Phase 1

**In scope**
- Corpus: OpenStax *Astronomy 2e* (Fraknoi, Morrison, Wolff, 2026), split into 4 thematic parts as PDFs (Foundations / Solar System / Stars / Galaxies & Cosmology). License CC BY-NC-SA 4.0; every UI citation surfaces an "Access for free at openstax.org" attribution.
- GCS landing bucket + Eventarc-triggered ingestion into a Vertex AI Search datastore.
- Vertex AI Search (Agent Builder) "Search + Summarize" queries via Discovery Engine SDK.
- FastAPI backend on Cloud Run + **Angular** SPA (served by nginx on Cloud Run).
- Golden eval dataset (30–50 Q&A) + RAGAS-based offline evaluation.
- Structured logging + Cloud Monitoring dashboard.
- **Infrastructure via a scripted `gcloud` runbook** (`infra/setup.md`).
- Security foundations: IAM least privilege, WIF for CI, UBLA, single-VPC with firewall rules.

**Explicitly deferred to Phase 2**
- Self-built chunking / embedding / vector store.
- Hybrid retrieval, rerankers, figure-caption pipeline.
- Bbox-based citation highlighting in the PDF pane.

**Designed but not enforced in Phase 1** (to keep cost down)
- Shared VPC (single-project at runtime).
- VPC Service Controls (dry-run).
- Cloud Armor (preview mode).
- CMEK (command documented; Google-managed keys used at runtime).

---

## 2. Architecture (Phase 1)

```
       ┌────────────────────┐
user ─▶│  Angular SPA        │
       │  (Cloud Run + nginx)│
       └──────────┬──────────┘
                  │ /api/query (SSE)
                  ▼
           ┌──────────────┐
           │ FastAPI api  │───────────────┐
           │ (Cloud Run)  │               │ Gemini 2.5
           └──┬────────┬──┘               │ (generate)
              │        │                  │
     Disc.Eng │        │ PSC              │
         SDK  ▼        ▼                  │
      ┌──────────────────────┐            │
      │  Vertex AI Search    │────────────┘
      │  (Agent Builder)     │
      │  - datastore         │
      │  - auto-chunk/embed  │
      └──────────┬───────────┘
                 │ indexed from
                 ▼
         ┌───────────────┐
 upload ▶│ GCS raw bucket│──┐
         └───────────────┘  │
                            ▼
                  ┌───────────────────┐
                  │ Eventarc trigger  │
                  │ → worker (Cloud   │
                  │   Run, optional   │
                  │   DLP + import)   │
                  └───────────────────┘
```

**Note on the worker in Phase 1.** Vertex AI Search supports direct GCS import, so the worker is thin — mostly an optional DLP pre-scan + triggering the datastore import API. In Phase 2 this worker grows into the full ingestion pipeline.

---

## 3. Implementation Steps

### 3.1 Infrastructure setup — the runbook approach

All Console actions are mirrored in `infra/setup.md` as copy-pasteable `gcloud` commands. 

Runbook sections:
1. **Project & APIs** — `gcloud projects create`, enable ~12 APIs (run, eventarc, discoveryengine, aiplatform, storage, cloudbuild, artifactregistry, logging, monitoring, secretmanager, cloudsql, iam).
2. **Service accounts** — create `sa-run-api`, `sa-run-worker`, `sa-run-web`, `sa-cloudbuild`, `sa-setup`; attach least-privilege roles; add IAM Conditions.
3. **Network** — single VPC, subnets (Cloud Run connector, reserved for Cloud SQL in Phase 2), Cloud NAT, Firewall rules, Private Service Connect endpoint for `googleapis.com`.
4. **Storage** — GCS buckets (`-rag-raw`, `-rag-eval`, `-rag-artifacts`) with UBLA, versioning, lifecycle.
5. **Artifact Registry** — Docker repo for Angular image, FastAPI api image, worker image.
6. **Vertex AI Search** — datastore + engine creation (via `gcloud alpha discovery-engine`).
7. **Eventarc** — trigger on `google.cloud.storage.object.v1.finalized` → worker service.
8. **Cloud Run deploys** — three services (`web`, `api`, `worker`), min-instances=0, per-service SA.
9. **Load Balancer** — URL map routing `/` → `web`, `/api/*` → `api`; Cloud Armor policy attached in preview.
10. **Observability** — log sinks, log-based metrics, dashboard, alert policies.
11. **WIF** — pool + provider bound to a specific GitHub repo for CI.
12. **Budget alert** — $30/month with email notification.
13. **Teardown** — matching `destroy.sh` that removes resources in reverse order (essential for cost control between dev sessions).

Each numbered section ends with a **verification command** (e.g., `gcloud run services list --region=us-central1`) so you can confirm the step succeeded.

### 3.2 GCS + Ingestion
- Bucket `gs://<proj>-rag-raw/books/` with UBLA, versioning, 30-day lifecycle on noncurrent versions.
- Organize by book part: `gs://<proj>-rag-raw/books/<book_id>/<book_id>.pdf` + `meta.json` (title, authors, year, edition, source_url, license, chapter range, chapter-heading hints if available). `book_id` is the textbook split, e.g. `openstax-astronomy-2e-pt2` for the Solar System part.
- Eventarc trigger on `.finalized` → Cloud Run worker.
- Worker logic:
  1. Parse `meta.json` alongside the PDF.
  2. Optional DLP inspect (skippable via env flag to save quota — Gutenberg texts are public domain, but keep the hook for user's own PDFs later).
  3. Call Discovery Engine `documents.import` with the GCS URI and book metadata attached as `structData`.
  4. Log structured event `{book_id, gcs_uri, ingestion_status, duration_ms}`.
- Idempotency: use GCS object generation as part of the document ID.

### 3.3 Vertex AI Search datastore
- Datastore type: **unstructured with layout parser enabled** (handles text + any embedded images/tables in PDFs).
- Search tier: **Standard** to start (cheaper). Upgrade to Enterprise only if eval shows Standard is insufficient — document the comparison if upgraded.
- Schema: minimal; use `structData` for book-level metadata (`book_id`, `title`, `authors`, `year`, `license`, `chapter_range`) so queries can filter by part of the textbook.

### 3.4 FastAPI `api` service

Endpoints:
- `POST /api/query` — body `{question, top_k?, book_ids?}`. Calls Discovery Engine `search` (with `filter` on `book_id` if scoped) → assembles context → calls Gemini for generation → **streams answer via SSE** with inline `[n]` citations.
- `GET /api/books` — returns the library catalog (book_id, title, author, page_count) for the Angular left pane.
- `GET /healthz` — liveness.
- Custom metrics exposed for Cloud Monitoring.

Notes:
- SDK: `google-cloud-discoveryengine` + `google-cloud-aiplatform` (Gemini).
- Use **streaming** generation and Server-Sent Events to the browser (Angular consumes via `EventSource` or `fetch` + `ReadableStream`).
- CORS configured to allow only the LB hostname.
- Structured log every query: `{trace_id, question_hash, book_filter, retrieved_doc_ids, retrieved_score_top1, model, input_tokens, output_tokens, total_ms, status}`.

### 3.5 Angular `web` SPA

**Stack:** Angular latest stable, standalone components, signals, new `@if/@for` control flow, Angular Material for components, pdf.js (or `ngx-extended-pdf-viewer`) for the PDF pane.

**Layout (NotebookLM-style, 3 columns):**
- **Left pane — Library & sources**: tree of books (`BookService` fetches `/api/books`); checkboxes to scope the query to a subset; basic search across book titles.
- **Center pane — Conversation**: question input at top, streaming answer below with inline clickable `[n]` citations; expandable "Sources" list per answer showing book + chapter + page + snippet; history of the last 10 queries (session-only for Phase 1).
- **Right pane — PDF viewer**: shows the PDF of the most recently cited source, jumps to the cited page. Phase 1 is page-accurate; Phase 2 adds bbox highlight.

**Implementation notes:**
- Single-app, no NgModules (standalone). Bootstrap with `provideRouter`, `provideHttpClient(withInterceptors([...]))`.
- Use `signals` for reactive state: `selectedBooks = signal<string[]>([])`, `currentQuery = signal<string>('')`, `streamingAnswer = signal<string>('')`.
- SSE handling: wrap `fetch` with `ReadableStream` reader and push tokens into `streamingAnswer` via `.update`.
- Build with `ng build --configuration=production`; Dockerfile uses multi-stage: `node` build → `nginx:alpine` serve `dist/`.
- Auth deferred in Phase 1 (public read via LB; document IAP as Phase 3 upgrade).

### 3.6 Router (Phase 1 version)
Minimal: always Gemini 2.5 Flash. Rationale: Vertex AI Search already does retrieval; for Phase 1 baseline we want the cheapest model. The full router lands in Phase 2 once we have self-built retrieval confidence scores to work with.

### 3.7 Prompting & Grounding
- System prompt forces: answer only from provided context; if unknown, say so; always cite with `[n]` matching the context index.
- Prompt includes book metadata in each context block: *"[1] From OpenStax Astronomy 2e, Ch. 26 (Galaxies), p. 902: ..."* — trains the model to produce rich citations.
- After generation, validate every `[n]` refers to an actually-returned chunk; flag unmatched citations as a quality metric.
- Every API response appends the OpenStax attribution string ("Access for free at openstax.org") as a footer, satisfying the CC BY-NC-SA 4.0 redistribution requirement on every digital page that surfaces this content.

### 3.8 Observability
- **Structured logs** (JSON) → Cloud Logging.
- **Log-based metrics**:
  - `rag_query_latency_ms` (distribution)
  - `rag_query_cost_estimate_usd` (distribution; computed from token counts)
  - `rag_citation_validation_failures` (counter)
  - `rag_ingestion_latency_ms` (distribution)
- **Cloud Monitoring dashboard** with 6 panels: QPS, p50/p95 latency, cost/day, citation-fail rate, ingestion latency, error rate.
- **Alert policies**: error rate > 5% for 10 min; daily cost > $2; citation-fail rate > 10%.

### 3.9 Evaluation harness (critical for Phase 2 comparison)
- **Golden dataset** `gs://<proj>-rag-eval/golden/v1.jsonl`: 30–50 entries of the form:
  ```json
  {
    "qid": "astro-001",
    "question": "Working with whose Mars data did Kepler discover that planetary orbits are ellipses, not circles?",
    "expected_answer_keywords": ["Tycho Brahe", "Mars", "ellipse"],
    "expected_book": "openstax-astronomy-2e-pt1",
    "expected_chapter": "3",
    "expected_page_range": [68, 73],
    "query_type": "factual"
  }
  ```
  Cover four `query_type`s: `factual`, `chapter_scoped`, `cross_topic`, `figure_or_diagram` (latter two marked "not expected to work well in Phase 1" but recorded to see the delta in Phase 2). `cross_topic` queries span multiple chapters within the textbook (e.g. linking redshift in Ch. 5 to Hubble's law in Ch. 26); `figure_or_diagram` queries reference figures or diagrams (HR diagram, galaxy classification, electromagnetic spectrum).
- **Harness** (`eval/run_eval.py`): load golden → call `/api/query` → compute:
  - **Faithfulness** (RAGAS): answer stays grounded in retrieved context?
  - **Answer relevance** (RAGAS): does it answer the question?
  - **Context precision** (RAGAS): are retrieved chunks relevant?
  - **Context recall**: does retrieval surface the expected source book/chapter?
  - **Citation accuracy**: does the cited `book/chapter/page` match the golden range?
- Run manually at first; wire into Cloud Build later (Phase 3).
- **Output**: a versioned run card (markdown + JSON) committed to `eval/runs/phase1-v{n}.md`.

---

## 4. Security Posture (Phase 1)

| Control | State in Phase 1 |
|---|---|
| IAM least privilege | ✅ Enforced |
| WIF for CI | ✅ Enforced |
| UBLA on GCS | ✅ Enforced |
| Private IP on Cloud SQL | N/A (no SQL in Phase 1) |
| PSC for Google APIs | ✅ Enforced |
| VPC Service Controls | 🟡 **Dry-run** (perimeter defined, violations logged) |
| Cloud Armor | 🟡 **Preview mode** (policies attached, not enforcing) |
| CMEK | 🟡 Command documented in runbook; Google-managed keys at runtime |
| DLP | 🟡 On-demand API calls; not continuous scanning |

Each 🟡 is deliberate — documented in the runbook with a `# COST: enforced in prod` note and the exact `gcloud` command to flip on.

---

## 5. Cost Breakdown (Phase 1)

| Line Item | Est. Monthly (idle) | Est. Monthly (100 q/day) | Mitigation |
|---|---|---|---|
| Cloud Run (3 services, scale-to-zero) | $0 | $1–2 | min-instances=0 |
| GCS storage (small corpus, ~100 MB/book × 5) | $0.50 | $1 | lifecycle rules |
| Eventarc | $0 | $0 | within free tier |
| **Vertex AI Search (Standard)** | $0 | $5–15 | largest variable cost; see notes |
| Gemini 2.5 Flash | $0 | $1–2 | Flash only in Phase 1 |
| Embedding (handled by Search) | — | — | included in Search cost |
| Cloud Logging/Monitoring | $0 | $0.50 | within free tier |
| Artifact Registry | $0.10 | $0.10 | |
| **Total** | **~$1** | **~$10–20** | |

**Notes on Vertex AI Search cost:** priced per query + per GB stored. 100 queries/day × 30 days = 3k queries/month, likely within a few dollars. Watch out for **indexing cost on initial import** — it's one-time but can surprise. Budget $30/month with alert at $20 and $30.

---

## 6. Deliverables (Phase 1 "Done" Checklist)

- [x] Corpus: OpenStax *Astronomy 2e* PDF uploaded to GCS bucket.
- [x] Vertex AI Search datastore + engine created and indexed.
- [x] `POST /api/query` returns a grounded, cited answer end-to-end (Discovery Engine + Gemini 2.5 Flash).
- [x] Angular UI renders streaming responses with clickable `[n]` citations.
- [x] Golden eval set v1 (8 questions) committed; baseline scores recorded in `eval/runs/phase1-discovery-engine-v1.md`.
- [x] `infra/setup.md` runbook + `infra/scripts/destroy.sh` written and verified through §1–§6, §12.
- [ ] Cloud Monitoring dashboard with 6 panels (deferred — see §6.1).
- [ ] Book-scoping checkbox UI (deferred — single book in Phase 1 corpus, no real test).
- [ ] PDF preview with per-citation page jump (deferred — Standard tier returns no page metadata; Phase 2 fixes).

### 6.1 Deliverables intentionally deferred

This section names what was *deliberately not done* in Phase 1, with the
reasoning. Treating these as "deferred" rather than "missed" is itself a
project-judgment signal: Phase 1's scope was bounded to producing a
**measured baseline**, not to bringing every checkbox green.

#### Cloud Run deployment — *deferred to Phase 2*

**Phase 1 was not deployed to Cloud Run.** The full deployment was
designed and committed to `infra/setup.md` (§5, §7–§11), but execution
was held back. Reasoning:

- **Phase 1's deliverable is a baseline measurement, not a product.** The
  baseline numbers (`eval/runs/phase1-discovery-engine-v1.md`) are
  identical whether the FastAPI runs locally or in a Cloud Run container,
  because the slow / authoritative parts of the pipeline are managed services
  (Discovery Engine, Gemini API). The container is just a transport.

- **Cost per month with no value gained.** A scale-to-zero Cloud Run
  deployment is approximately $5/month (Artifact Registry storage + cold-start
  invocations from periodic eval runs + minimal egress). For a baseline
  whose numbers don't change, that's $5 per month buying nothing.

- **Cold starts are a *worse* demo experience.** A Cloud Run service
  with min-instances=0 takes 8–15 seconds to respond to the first
  request after idle. Asking an interviewer to wait 15 seconds for the
  first query is harmful. Local `uvicorn` is 0 seconds. If the goal is
  "share a URL during an interview," Cloud Run with min-instances=0
  actively underperforms localhost.

- **Phase 2 forces an always-on resource anyway.** Phase 2 introduces
  Cloud SQL + pgvector, which cannot be scale-to-zero (it can be stopped,
  but not zero-instance). Once Cloud SQL exists in the architecture, an
  always-on Cloud Run service is the natural deployment target — no
  longer "extra cost for no benefit." Deploying Phase 2 to Cloud Run is
  in scope; deploying Phase 1 to Cloud Run beforehand would be running
  the same deployment work twice.

- **The runbook is itself the artifact.** `infra/setup.md` is the
  demonstrable proof of "I know how to deploy this." Whether I ran the
  commands or not is a separate question from whether I designed the
  deployment correctly. In an interview, walking through the runbook is
  more substantive than showing a URL.

The interview-version: *"Phase 1 wasn't deployed to Cloud Run. I designed
the deployment in `infra/setup.md`, but for a baseline whose numbers don't
change between localhost and Cloud Run, paying ~$5/month for visible
cold starts adds nothing to the project narrative. Phase 2 will deploy
because Cloud SQL forces an always-on resource."*

中文版："Phase 1 没部署到 Cloud Run。完整部署在 `infra/setup.md` 里设计好了，
但 Phase 1 baseline 的数字不管在本地还是 Cloud Run 上跑都一样——所以花 $5/月
换肉眼可见的 cold start，对项目故事是零增益。Phase 2 会部署，因为 Cloud SQL
强制了一个长 running 的资源。"

#### Cloud Monitoring dashboard — *deferred*

The structured logs are in place (`structlog` JSON output, log-based
metrics designed in §3.8), but the 6-panel Cloud Monitoring dashboard
itself was not built. Same reasoning: a baseline run is short-lived;
a dashboard's value is in *long-running* observation. Phase 2 will need
this for the A/B latency comparison; building it then makes the dashboard
panels actually informative.

#### Book-scoping UI — *partially deferred*

The wiring is complete (`book_ids` parameter flows from frontend chip-set
through `/api/query` into `discovery_engine.retrieve()`), but the corpus
is currently a single OpenStax PDF — there's only one book to scope to.
The feature is testable when Phase 2 adds chapter-level segmentation, at
which point "scope to chapter X" becomes the meaningful filter.

#### PDF preview with bbox highlighting — *deferred to Phase 2*

The Angular `pdf-pane.ts` component has the data structure for
`{page, bbox}` ready, but Phase 1's Standard-tier Discovery Engine
returns no page metadata and no bounding boxes. So the data flow has
nothing real to display. Phase 2's Document AI Layout Parser is the
fix — see `phase2-selfbuilt.md §8`.

---

---

## 7. What to Watch For (Pitfalls)

- **Vertex AI Search quota**: default quotas are generous but can surprise on bulk import of 1000+ page books. Check `Discovery Engine API` quotas early.
- **Layout parser limits**: max pages per document, max doc size — splitting *Astronomy 2e* into 4 thematic parts (~220–320 pages each) keeps each PDF well below typical limits and makes book-scoping in the UI more meaningful.
- **Gemini safety filters**: some historical content (wars, violence) triggers safety filters. Tune `safety_settings` and log blocked responses.
- **Angular Cloud Run cold starts**: nginx container cold start is fast (~1s), but combined with API cold start the first query can be slow. Acceptable for a portfolio project; document it.
- **SSE through Cloud Run**: Cloud Run supports streaming but has a 60-min request timeout; fine here. Make sure the LB path for `/api/*` doesn't buffer — set `--timeout=3600` and avoid CDN caching.
- **Eventarc delivery delays**: not instant; budget 30–90s end-to-end for the upload-to-indexed path.
- **Project Gutenberg PDFs**: some are scanned image PDFs — verify they contain real text before ingest, otherwise you need OCR (defer to Phase 2).

---

## 8. Exit Criteria → Start Phase 2

Phase 2 begins only after:
1. Baseline eval scores recorded.
2. Baseline cost (per query and per month) recorded.
3. Baseline latency (p50, p95 TTFT and total) recorded.
4. At least 10 real queries written up as "interesting cases" for comparison in Phase 2 — ideally including 2–3 where Phase 1 visibly fails (e.g., cross-topic queries spanning distant chapters, figure/diagram-related queries) to set up the Phase 2 improvement narrative.

Without this baseline, Phase 2's A/B has no reference point — and the whole two-phase narrative loses its strongest selling point.
