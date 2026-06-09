# rag-docs — Personal NotebookLM over an astronomy textbook

A two-phase RAG system on GCP that grounds Gemini answers in OpenStax
*Astronomy 2e* (CC BY-NC-SA 4.0), a 1,151-page college-level astronomy textbook,
with precise part / chapter / page citations.

> **Corpus**: OpenStax *Astronomy 2e* (Fraknoi, Morrison, Wolff, 2026).
> [Access for free at openstax.org](https://openstax.org/details/books/astronomy-2e).
> Licensed under CC BY-NC-SA 4.0 — this project is non-commercial and surfaces
> the required attribution string with every answer.

- **Phase 1** — managed (Vertex AI Search + Gemini).
- **Phase 2** — self-built (Cloud SQL + pgvector, Document AI, hybrid retrieval, rerank).

Full design: [technical-design.md](./technical-design.md) ·
[phase1-managed.md](./phase1-managed.md) ·
[phase2-selfbuilt.md](./phase2-selfbuilt.md).

## Repo layout

```
rag-docs/
├── api/                     # FastAPI + Pydantic backend (Poetry)
├── web/                     # Angular 19 SPA (standalone + signals + Material)
├── infra/                   # gcloud runbook + helper scripts (WIP)
├── eval/                    # golden Q&A + eval harness (Phase 1+)
├── docker-compose.yml       # local prod-like sanity check
├── technical-design.md
├── phase1-managed.md
└── phase2-selfbuilt.md
```

## Quick start — local dev, no GCP

The API defaults to `RETRIEVAL_BACKEND=mock` so you can develop the UI
end-to-end without any GCP credentials or costs.

### Two-terminal workflow (recommended for active dev)

```bash
# Terminal 1 — API with auto-reload
cd api
cp .env.example .env
poetry install
poetry run uvicorn app.main:app --reload --port 8000

# Terminal 2 — Angular with HMR + proxy
cd web
npm install
npm start       # http://localhost:4200  (proxies /api → localhost:8000)
```

### Single-command (prod-like via Docker Compose)

```bash
docker compose up --build
# Web → http://localhost:8080
# API → http://localhost:8000
```

## Test

```bash
cd api && poetry run pytest         # API smoke tests
cd web && npm test                  # (once unit tests are added)
```

## Next steps toward Phase 1 on GCP

See [phase1-managed.md §3.1](./phase1-managed.md) for the `infra/setup.md`
runbook. Once a Vertex AI Search datastore exists, flip
`RETRIEVAL_BACKEND=discovery_engine` in the API env and fill in
`DISCOVERY_ENGINE_*` + `GCP_PROJECT_ID`.

## Stack summary

| Layer | Tech |
|---|---|
| Frontend | Angular 19, standalone components, signals, Material 3, pdf.js |
| Backend | FastAPI, Pydantic v2, Poetry, structlog |
| Generation | Gemini 2.5 Flash/Pro via google-genai (Vertex mode) |
| Retrieval (P1) | Vertex AI Search / Agent Builder |
| Retrieval (P2) | Cloud SQL + pgvector, Document AI, BM25 + vector + RRF + LLM rerank |
| Compute | Cloud Run (scale-to-zero) |
| Events | Eventarc on GCS finalize → worker |
| Observability | Cloud Logging (JSON), Cloud Monitoring dashboards |
| IaC | Scripted `gcloud` runbook (not Terraform — see technical-design.md §7.1) |
