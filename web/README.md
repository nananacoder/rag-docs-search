# web/ — Angular SPA

NotebookLM-style 3-pane UI: **Library** (left) · **Conversation** (center) · **PDF viewer** (right).

## Stack
- Angular 19 (standalone components, signals, new control flow `@if / @for / @let`)
- Angular Material (Material 3 theming via `mat.theme`)
- `fetch` + `ReadableStream` for Server-Sent Events from FastAPI
- nginx (alpine) for production serving

## Local dev

```bash
npm install
npm start     # ng serve --proxy-config proxy.conf.json
# opens http://localhost:4200 — /api/* proxied to http://localhost:8000
```

The FastAPI backend must be running on port 8000 (`cd ../api && poetry run uvicorn app.main:app --reload`), or the in-repo `docker-compose.yml` wires both up.

## Build

```bash
npm run build:prod    # outputs dist/web/browser
docker build -t rag-docs-web .
docker run -p 8080:8080 rag-docs-web
```

## Project structure

```
src/app/
  app.ts                # root component (router-outlet)
  app.config.ts         # providers: router, http (fetch), animations
  app.routes.ts         # lazy-loads Workspace
  core/
    models/             # Book, Citation, QueryEvent types
    services/           # BookService, QueryService (signal-based state)
  features/
    workspace/          # 3-column layout shell
    library/            # left pane — book list + scope selection
    conversation/       # center pane — question input + streaming answer
      answer-view.ts    # parses [n] citations into clickable chips
    pdf-viewer/         # right pane — shows active citation source
```

## Key design choices

- **Signals for state.** `BookService` and `QueryService` expose readonly signals; components use `computed()` for derived state. No RxJS `BehaviorSubject` boilerplate.
- **Streaming via `fetch` + `ReadableStream`.** SSE is hand-parsed in `QueryService.ask()` — no libraries, full control over reconnect/abort semantics.
- **Citation chips.** The answer text contains raw `[n]` markers; `AnswerView.segments` splits the string into a `(text | cite)` array and renders clickable pills that update `QueryService.activeCitation`.
- **PDF pane is a placeholder in Phase 1.** Phase 2 will swap in `ngx-extended-pdf-viewer` with bbox overlay.
