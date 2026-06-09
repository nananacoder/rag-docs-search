# api/ — FastAPI backend

Serves `/api/books` and streaming `/api/query` (Server-Sent Events) to the Angular SPA.

## Stack
- Python 3.12
- FastAPI + Pydantic v2 + pydantic-settings
- structlog for JSON logs
- google-genai + google-cloud-discoveryengine (Phase 1 wiring; stubbed until GCP creds are configured)

## Design principle

Retrieval and generation are behind **protocol-style abstractions** (`Retriever`, `Generator`) so the same API code runs against three different backends selected by env var:

| `RETRIEVAL_BACKEND` | Retriever | Generator | When to use |
|---|---|---|---|
| `mock` (default) | static fixtures | scripted streaming | local dev, no GCP creds needed |
| `discovery_engine` | Vertex AI Search | Gemini (Vertex) | Phase 1 |
| `pgvector` | Cloud SQL + pgvector + hybrid | Gemini + LLM reranker | Phase 2 |

This lets the Angular UI be developed against a real streaming API without paying for GCP calls.

## Local dev

```bash
cp .env.example .env
poetry install
poetry run uvicorn app.main:app --reload --port 8000
# health: curl http://localhost:8000/healthz
# books:  curl http://localhost:8000/api/books | jq
# query:  curl -N -X POST http://localhost:8000/api/query \
#           -H 'content-type: application/json' \
#           -d '{"question": "why did Rome fall?"}'
```

## Test

```bash
poetry run pytest
```

## Project structure

```
app/
  main.py                    # FastAPI factory, lifespan, CORS, router wiring
  api/
    deps.py                  # typed dependencies (singletons for retriever/generator)
    health.py                # /healthz, /readyz
    books.py                 # GET /api/books
    query.py                 # POST /api/query — SSE stream
  core/
    config.py                # Settings via pydantic-settings
    logging.py               # structlog JSON setup
  models/
    book.py                  # Book + ApiModel base (camelCase alias for Angular)
    citation.py              # Citation, RetrievedChunk, BoundingBox
    query.py                 # QueryRequest + discriminated union of SSE events
  services/
    retrieval/
      base.py                # Retriever protocol
      mock.py                # static fixtures
      discovery_engine.py    # Phase 1 (stub)
    generation/
      base.py                # Generator protocol
      mock.py                # scripted streaming answer
      gemini.py              # Phase 1 (stub)
tests/
  test_smoke.py              # health + books + SSE smoke test
```

## SSE event schema

The `/api/query` endpoint emits one of four event types as `data: {json}\n\n` frames:

```json
{"type": "citations", "citations": [ ...Citation ]}
{"type": "token",     "text": "..."}
{"type": "done",      "inputTokens": N, "outputTokens": N, "totalMs": N, "model": "..."}
{"type": "error",     "message": "..."}
```

All fields are camelCase (Pydantic `alias_generator=to_camel`) to match the TypeScript models in `web/src/app/core/models/`.
