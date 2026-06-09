# 07 — Vertex AI Search Setup: REST API Traps and SDK Wins

**Date**: 2026-06-09
**Tags**: vertex-ai-search, discovery-engine, gcp, debugging, sdk-vs-rest

## Question I started with
"The phase1-managed.md runbook has clean curl commands for creating a Vertex
AI Search datastore. Should be straightforward — POST to discoveryengine API,
trigger import, smoke-test search. What could go wrong?"

## Short answer
Three independent traps in one chain: ADC quota project, regional API
endpoint vs `location` mismatch, and a path component (`collections/default_collection`)
the curl docs omit. Each returned an error message that pointed away from the
real cause. The fix wasn't "better curl" — it was switching to the **Python
SDK**, which handles all three implicitly.

---

## What I was trying to do

Phase 1 §6 from the runbook: bring up Vertex AI Search end-to-end.

```
1. Create a Datastore
2. Trigger PDF import from GCS
3. Create a search Engine fronting the Datastore
4. Smoke-test a search query
```

Inputs: a 1,151-page OpenStax PDF already in GCS at
`gs://my-rag-docs-bucket-123/astronomy-2e.pdf`. Project, billing, IAM, all
pre-validated.

---

## Trap 1 — ADC Quota Project Not Set

### What I saw

```json
{
  "error": {
    "code": 403,
    "message": "Your application is authenticating by using local Application Default Credentials. The discoveryengine.googleapis.com API requires a quota project, which is not set by default.",
    "status": "PERMISSION_DENIED"
  }
}
```

### What was actually wrong

`gcloud auth login` and `gcloud auth application-default login` are **two
separate authentication contexts**:

| Command | Used by | Stored where |
|---|---|---|
| `gcloud auth login` | The `gcloud` CLI itself | gcloud config |
| `gcloud auth application-default login` | SDKs and direct REST API calls | ADC well-known JSON |

When `curl` calls a Google API with a token from `gcloud auth print-access-token`,
the API treats it as ADC. Some APIs (Discovery Engine being one) **require an
explicit quota project** — they refuse to use the user's default-project as
the billing target.

The error message helpfully named the failing API but unhelpfully said
"PERMISSION_DENIED" — which makes you go check IAM. The actual fix is
authentication-layer, not authorization-layer.

### Fix

```bash
gcloud auth application-default login                          # one-time browser login
gcloud auth application-default set-quota-project <PROJECT>    # set the quota target
```

OR add an explicit header to every curl call:
```
-H "X-Goog-User-Project: ${PROJECT_ID}"
```

The Python SDK handles this automatically once `application-default login`
has been run.

### Pattern to watch for

**"PERMISSION_DENIED" with a hint about quota project = authentication
problem, not authorization problem.** Don't waste time auditing IAM bindings.

---

## Trap 2 — Regional API Endpoint Mismatch

### What I saw

After fixing Trap 1, the next request returned:

```json
{
  "error": {
    "code": 400,
    "message": "Incorrect API endpoint used. The current endpoint can only serve traffic from \"global\" region, but got \"us\" region from the API request.",
    "status": "INVALID_ARGUMENT"
  }
}
```

### What was actually wrong

Discovery Engine has **regional API endpoints**. Three of them:

| Location in path | Required endpoint |
|---|---|
| `locations/global` | `discoveryengine.googleapis.com` |
| `locations/us` | `us-discoveryengine.googleapis.com` |
| `locations/eu` | `eu-discoveryengine.googleapis.com` |

If you POST `…/locations/us/dataStores…` to the `discoveryengine.googleapis.com`
endpoint, the global endpoint sees a "wrong region" mismatch and rejects.

This is **different from how most Google APIs behave** — most APIs route
internally based on the path. Discovery Engine forces you to pick the right
hostname yourself.

### Fix

Match endpoint to location:

```bash
# location=us
curl "https://us-discoveryengine.googleapis.com/v1/projects/.../locations/us/..."
```

In the Python SDK:

```python
from google.api_core.client_options import ClientOptions
client_options = ClientOptions(api_endpoint=f"{location}-discoveryengine.googleapis.com")
client = discoveryengine_v1.DataStoreServiceClient(client_options=client_options)
```

### Pattern to watch for

**Discovery Engine, Vertex AI, AlloyDB, and a few other newer GCP services
require regional API endpoints.** When in doubt, check whether the documented
hostname has a region prefix. The error message names this clearly *if* you
read past the "INVALID_ARGUMENT" status.

---

## Trap 3 — Missing `collections/default_collection` in the Path

### What I saw

After fixing Traps 1 and 2:

```json
{
  "error": {
    "code": 500,
    "message": "Internal error encountered.",
    "status": "INTERNAL"
  }
}
```

`HTTP 500 INTERNAL` with no further detail — **looks like a Google service
outage**. It's not.

### What was actually wrong

The Discovery Engine resource hierarchy is:

```
projects/<id>/
  locations/<region>/
    collections/<collection>/        ← MUST be in the path
      dataStores/<datastore_id>      ← what you're creating
```

The official quickstart docs sometimes show:
```
.../locations/{location}/dataStores/{id}    ← WRONG
```

This works for **listing** datastores (which doesn't need the collection in
the path) but **fails opaquely** when creating a datastore or engine. The
server returns `500 INTERNAL` instead of a helpful "missing path component"
because the parser silently produces an invalid resource path that no handler
matches.

The correct path is:
```
.../locations/{location}/collections/default_collection/dataStores/{id}
```

`default_collection` is a literal string, not a placeholder.

### Fix

The Python SDK constructs this path correctly via the `parent` parameter:

```python
parent = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection"

operation = client.create_data_store(
    parent=parent,
    data_store=datastore,
    data_store_id=DATASTORE_ID,
)
```

In raw curl, you must include `collections/default_collection` in every
create/update path.

### Pattern to watch for

**A `500 INTERNAL` from a GCP API after the request body parses cleanly is
almost always a malformed resource path** — wrong order of components, missing
required segment, or wrong API version. The 500 is the server's polite way of
saying "I don't know how to route this."

When you hit `500 INTERNAL` and you've ruled out outage:
1. Check the [resource hierarchy docs](https://cloud.google.com/generative-ai-app-builder/docs/about) for hidden path components
2. Switch from curl to the SDK — SDKs encode the resource hierarchy
3. Compare with `gcloud` command output for the same operation if available

---

## Why the Python SDK won where curl lost

```python
from google.cloud import discoveryengine_v1
from google.api_core.client_options import ClientOptions

client_options = ClientOptions(api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com")
client = discoveryengine_v1.DataStoreServiceClient(client_options=client_options)

operation = client.create_data_store(
    parent=f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection",
    data_store=discoveryengine_v1.DataStore(...),
    data_store_id=DATASTORE_ID,
)
result = operation.result(timeout=300)   # blocks until ready
```

Done in 30 seconds.

The SDK absorbs all three traps:
- **ADC quota project**: auto-injected from gcloud config
- **Regional endpoint**: explicit `ClientOptions(api_endpoint=...)`
- **Resource path**: typed `parent` parameter prevents missing components

It also turns the long-running create operation into a Pythonic `operation.result()`
call. Curl + REST forces you to poll an `operations/...` resource yourself.

---

## What worked end-to-end

Once on the SDK path, the flow was:

### 1. Datastore (Python SDK, ~30 sec)

```python
client = discoveryengine_v1.DataStoreServiceClient(client_options=...)
operation = client.create_data_store(
    parent="projects/PROJECT/locations/us/collections/default_collection",
    data_store=DataStore(
        display_name="Astronomy 2e datastore",
        industry_vertical=IndustryVertical.GENERIC,
        solution_types=[SolutionType.SOLUTION_TYPE_SEARCH],
        content_config=DataStore.ContentConfig.CONTENT_REQUIRED,
    ),
    data_store_id="astronomy-2e-datastore",
)
operation.result(timeout=300)
```

### 2. Document import (async, returned immediately)

```python
client = discoveryengine_v1.DocumentServiceClient(client_options=...)
operation = client.import_documents(request=ImportDocumentsRequest(
    parent="…/dataStores/{id}/branches/default_branch",
    gcs_source=GcsSource(
        input_uris=["gs://bucket/astronomy-2e.pdf"],
        data_schema="content",
    ),
    reconciliation_mode=ReconciliationMode.INCREMENTAL,
))
# Don't block — indexing is 5-30 minutes for a 1151-page PDF
```

### 3. Search Engine (~30 sec)

```python
client = discoveryengine_v1.EngineServiceClient(client_options=...)
operation = client.create_engine(
    parent="projects/PROJECT/locations/us/collections/default_collection",
    engine=Engine(
        display_name="Astronomy 2e search engine",
        solution_type=SolutionType.SOLUTION_TYPE_SEARCH,
        industry_vertical=IndustryVertical.GENERIC,
        data_store_ids=["astronomy-2e-datastore"],
        search_engine_config=Engine.SearchEngineConfig(
            search_tier=SearchTier.SEARCH_TIER_STANDARD,
        ),
    ),
    engine_id="astronomy-2e-engine",
)
operation.result(timeout=180)
```

### 4. Smoke-test search (worked first try after indexing)

```python
client = discoveryengine_v1.SearchServiceClient(client_options=...)
response = client.search(SearchRequest(
    serving_config="…/engines/astronomy-2e-engine/servingConfigs/default_search",
    query="Kepler third law of planetary motion",
    page_size=3,
    content_search_spec=ContentSearchSpec(
        snippet_spec=SnippetSpec(return_snippet=True),
    ),
))
# Returned 1 document with bolded snippet hitting "Kepler's third law"
```

Indexing a 1,151-page PDF was unexpectedly fast — under 5 minutes — but
plan for 30 minutes in case of larger corpora or service load.

---

## Trap 4 — `SearchServiceAsyncClient` Conflicts with FastAPI's Worker Threads

### What I saw

After wiring the async client into `DiscoveryEngineRetriever.__init__`, the
first request hit:

```
RuntimeError: There is no current event loop in thread 'AnyIO worker thread'.
  File ".../grpc/aio/_channel.py", line 369, in __init__
    self._loop = cygrpc.get_working_loop()
```

500 from the API; nothing about Discovery Engine in the trace. The error
came from `grpc-asyncio` trying to bind to an event loop at construction time.

### What was actually wrong

FastAPI's dependency injection runs synchronous dependencies (like our
`build_retriever()` factory) in a worker thread via `anyio.to_thread.run_sync`.
That worker thread has no event loop. `SearchServiceAsyncClient` internally
uses grpc-asyncio, which **at construction** tries to grab the current
event loop — and crashes when it's called from a non-loop thread.

This is specifically a problem with `*AsyncClient` types from google-cloud-*
that wrap grpc-asyncio. Sync clients (`SearchServiceClient`) don't have this
issue because they use blocking grpc, no event loop required.

### Fix

Use the **synchronous client** and wrap calls in `asyncio.to_thread`:

```python
from google.cloud import discoveryengine_v1
import asyncio

class DiscoveryEngineRetriever:
    def __init__(self, settings):
        self._client = discoveryengine_v1.SearchServiceClient(client_options=...)

    async def retrieve(self, query, top_k, book_ids=None):
        request = discoveryengine_v1.SearchRequest(...)
        # Run sync gRPC off the event loop thread
        response = await asyncio.to_thread(self._client.search, request=request)
        ...
```

This pattern is mildly counterintuitive ("why not the async client in an
async app?") but it's what google-cloud SDK maintainers actually recommend
for FastAPI / Starlette use cases. Construction in any thread, calls
non-blocking via `to_thread`.

### Pattern to watch for

**`AsyncClient` + framework with thread-pool dependency injection = event
loop conflict.** If you see `RuntimeError: There is no current event loop`
in a stack trace that mentions `grpc/aio` or `cygrpc`, the fix is to switch
to the sync client. Don't fight it.

---

## Trap 5 — Standard Tier Has No Extractive Segments

### What I saw

After wiring the sync client and getting past the event loop issue:

```
"Retrieval failed: 400 Cannot use enterprise edition features (website search,
multi-modal search, extractive answers/segments, etc.) in a standard edition
search engine."
```

### What was actually wrong

I'd built the search request with both:

```python
content_search_spec=ContentSearchSpec(
    snippet_spec=SnippetSpec(return_snippet=True),                        # OK on Standard
    extractive_content_spec=ExtractiveContentSpec(...),                   # ENTERPRISE ONLY
)
```

Following the docs' default examples without realizing some features are
gated by the engine's `search_tier`. Phase 1's runbook explicitly chose
`SEARCH_TIER_STANDARD` to keep cost down — but the docs frequently show
features that require `SEARCH_TIER_ENTERPRISE`, with no warning.

### Tier-gated features (Standard ❌, Enterprise ✅)

- Extractive segments / extractive answers
- Document summarization
- Website search
- Multi-modal search
- Some advanced semantic ranking knobs

Standard tier basically gives you: snippet, query expansion, basic ranking,
filters, page-level results.

### Fix

Drop the `extractive_content_spec`; only use `snippet_spec`:

```python
content_search_spec=ContentSearchSpec(
    snippet_spec=SnippetSpec(return_snippet=True),
),
```

This is the *intended* Phase 1 behavior — but I had to rediscover it from
runtime errors, not the docs.

### Cascading consequence: no page numbers

Standard tier's snippet response **does not include page numbers** in the
returned document metadata. Each `SearchResponse.results[i].document` has
no `page_number` field. Without extractive segments (which Enterprise would
provide with `pageNumber`), there's no per-result page info to populate
into our `RetrievedChunk.page`.

For Phase 1 we set `page = 1` as a placeholder. This makes `citation_accuracy`
score 0% for every question — *because the system literally cannot return
correct page numbers under Standard tier*. This is **expected** for Phase 1;
Phase 2's self-built Document AI Layout Parser pipeline restores per-chunk
page tracking and is the planned fix.

This is in fact one of the strongest motivations for Phase 2 existing.

### Pattern to watch for

**Tier-gating in GCP managed services is real and not always documented at
the feature level.** The docs say "extractive segments are useful for X" —
they don't always say "and they require Enterprise tier." When a 400 error
mentions "edition" or "tier", check the engine config first, not the request
payload.

---

## Trap 6 — `GeminiGenerator` Was a Stub

### What I saw

```
"Generation failed: Gemini streaming — implement once GCP creds are configured"
```

### What was actually wrong

`api/app/services/generation/gemini.py` had been left as a stub with a
deliberate `raise NotImplementedError(...)` since Phase 1 hadn't been
deployed yet. The retriever side had been kept as a stub too (Trap 1
fixed that), but the generator side wasn't on anyone's radar — it doesn't
fail at import time, only when actually invoked.

### Fix

Wired up `google-genai` in Vertex mode with streaming + usage_metadata
capture:

```python
from google import genai
from google.genai import types

class GeminiGenerator(Generator):
    def __init__(self, settings):
        self._client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,    # us-central1
        )

    async def stream(self, question, context):
        prompt = build_user_prompt(question, context)
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=self.settings.generation_temperature,
        )
        last_chunk = None
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self.settings.gemini_model,
            contents=prompt,
            config=config,
        ):
            last_chunk = chunk
            if chunk.text:
                yield chunk.text
        if last_chunk and last_chunk.usage_metadata:
            um = last_chunk.usage_metadata
            self._metrics = GenerationMetrics(
                input_tokens=um.prompt_token_count or 0,
                output_tokens=um.candidates_token_count or 0,
                model=self.settings.gemini_model,
            )
```

Two things worth noting:
1. **`google-genai` async client works fine in FastAPI** — unlike Discovery
   Engine's `*AsyncClient`, it doesn't have the event-loop-construction issue.
   So async-in-async, no `to_thread` needed.
2. **`usage_metadata` is on the last chunk only.** If you only look at the
   first or middle chunks you'll see `None`. Capture-and-overwrite pattern.

### Pattern to watch for

**Stubs that raise on call (not on import) are silent until first invocation.**
A "compiles, runs, has tests" project can still have entire code paths that
fail at runtime. The `RETRIEVAL_BACKEND=mock` default protected us from this
during local dev — only the moment we flipped to `discovery_engine` did the
generator stub matter.

Add a system-level smoke test that exercises every backend before claiming
deployment readiness.

---

## What I had to give up on (yet)

**Document-level vs chunk-level retrieval.** The `data_schema="content"`
import schema treats the whole PDF as one document. The smoke-test query
returned 1 result — meaning all subsequent ranking/filtering happens at
the document level, not per chunk.

For chunk-level retrieval (which is what we want for RAG citations), you
need either:
- A per-chunk pre-processing step before import (split PDF, upload one file
  per chunk), OR
- Use Discovery Engine's built-in chunking via `data_schema="custom"` with
  metadata, OR
- Wait for Phase 2 where the self-built pgvector pipeline gives full control

This is a known Phase 1 limitation, not a bug. It's part of *why* Phase 2
exists — Phase 1 trades chunk-level control for managed simplicity.

---

## Cost so far (for the curious)

After all Phase 1 §6 actions:
- Datastore creation: free
- Engine creation: free
- Document import (1 PDF, 1,151 pages): ~$2-3 one-time indexing fee
- Search queries during smoke test: trivial (~$0.01)

Total real cost across this entire setup chain: **under $5 USD**, well within
the ¥2,000 budget alert. Standard tier idle is essentially free; per-query
charges only kick in once eval starts hammering it.

---

## Takeaway

Three takeaways, increasing in generalizability:

1. **For Vertex AI Search specifically**: use the Python SDK from day one.
   The REST API has too many implicit conventions (regional endpoint, ADC
   quota project, collection in path) that the docs spread across multiple
   pages. The SDK absorbs them all.

2. **For GCP REST API debugging**: when an error message says PERMISSION_DENIED
   or 500 INTERNAL, the wording usually points away from the real cause.
   `quota_project` errors are auth-layer (not IAM); `500 INTERNAL` after a
   well-formed body is path-layer. Reading past the status code is mandatory.

3. **For all infrastructure work**: a working SDK call is more valuable than
   a working curl call, because the SDK encodes the conventions that the
   curl docs assume you already know. Curl is good for understanding what's
   on the wire; SDKs are good for actually getting work done.

Companions:
- See `learnings/02-eval-before-deploy.md` for why Vertex AI Search setup
  comes after eval design, not before
- See `infra/setup.md` §6 for the curl-based reference (kept for educational
  value; the actual project uses the SDK calls documented here)

---

## Appendix — Engine vs Datastore: the two-layer mental model
## 附录 —— Engine 与 Datastore 的两层抽象

When you open the Console, Vertex AI Search resources appear under "Apps" /
"AI Applications" as **two separate things**: an **Engine** and a
**Datastore**. The same split appears in the SDK and in resource paths.
Understanding why GCP made this distinction is one of the more common
interview questions about managed search products.

打开 Console 时，Vertex AI Search 的资源在 "Apps" / "AI Applications"
菜单下显示为**两个独立的对象**：**Engine（搜索引擎）**和 **Datastore（数据存储）**。
SDK 和资源路径里也是分两层。理解这个分离的设计是理解 managed RAG 服务
的关键。

### The picture / 全图

```
                       ┌──────────────────────────────────────┐
                       │  Your FastAPI / web client            │
                       │  你的 FastAPI / Web 客户端              │
                       │  /api/query                          │
                       └─────────────────┬────────────────────┘
                                         │ search request
                                         │ 查询请求
                                         ▼
       ┌─────────────────────────────────────────────────────────┐
       │  ENGINE  (搜索引擎)                                       │
       │  astronomy-2e-engine                                     │
       │  ─────────────────                                       │
       │  - solution_type: SEARCH                                 │
       │  - search_tier: STANDARD                                 │
       │  - serving_config: default_search                        │
       │  - ranking / query expansion / snippet generation        │
       │  - 可挂多个 datastore (one engine, many datastores)      │
       └────────────────────┬─────────────────────────────────────┘
                            │ "give me documents matching this query"
                            │ "返回匹配此查询的文档"
                            ▼
       ┌─────────────────────────────────────────────────────────┐
       │  DATASTORE  (数据存储)                                    │
       │  astronomy-2e-datastore                                  │
       │  ─────────────────                                       │
       │  - container of indexed documents                        │
       │  - 已索引文档的容器                                        │
       │  - content_config: CONTENT_REQUIRED                      │
       │  - branches/0/documents/<doc_id>                         │
       │  - indexed: 1 document (1151-page PDF)                  │
       │      ↑ layout parser ran here, embeddings + inverted    │
       │        index built here                                  │
       │      ↑ Layout parser 在这里跑过, 生成向量 + 倒排索引       │
       └────────────────────┬─────────────────────────────────────┘
                            │ ImportDocuments operation (one-time)
                            │ 一次性导入操作
                            ▼
       ┌─────────────────────────────────────────────────────────┐
       │  GCS                                                     │
       │  gs://my-rag-docs-bucket-123/astronomy-2e.pdf            │
       │  ─────────────────                                       │
       │  - raw PDF, not searchable                               │
       │  - 原始 PDF 文件, 不可被搜索                                │
       │  - safe to delete after indexing — content is copied     │
       │  - 索引完成后即使删除, 搜索照样工作 (内容已被复制走)         │
       └─────────────────────────────────────────────────────────┘
```

### One-line distinction / 一句话区分

| Layer | Plain English | 类比 |
|---|---|---|
| **Datastore** | A container of indexed documents | 图书馆的**书架** —— 书放在这里，可被检索 |
| **Engine** | A query-serving service that fronts one or more datastores | 图书馆的**前台** —— 接受用户提问，去书架查 |

### Why split into two? / 为什么要分两层？

**1. One datastore can feed multiple engines** /
   **一份索引数据可以喂给多个 engine**

```
                    ┌→ search-engine    (regular search)
astronomy-2e-datastore ─┼→ chat-engine      (conversational)
                    └→ recommend-engine (recommendations)
```
索引很贵 (indexing is expensive)；建一次，多种查询模式复用。

**2. One engine can attach multiple datastores** /
   **一个 engine 可以挂多个 datastore**

```
                ┌─ astronomy-2e-datastore
unified-engine ─┼─ physics-textbook-datastore
                └─ chemistry-textbook-datastore
```
统一搜索多个语料库 (search across multiple corpora)。我们项目里"book
scoping"功能可以这样实现 —— 每本书一个 datastore，engine 把它们统一起来。

**3. Different engines can have different tiers and configs** /
   **同一份数据可以同时有多种查询行为**

- One Standard-tier engine for production (cheap, basic features) /
  一个 Standard-tier engine 给生产用 (便宜)
- One Enterprise-tier engine for research (extractive segments etc.) /
  一个 Enterprise-tier engine 给研究用 (功能多)
- Same underlying indexed data / **底层索引数据是同一份**

### How this maps to our code / 跟我们代码的对应关系

The serving_config path encodes the layered hierarchy /
serving_config 路径里能看到层级关系：

```python
self._serving_config = (
    f"projects/{settings.gcp_project_id}"
    f"/locations/{location}"
    f"/collections/{settings.discovery_engine_collection}"
    f"/engines/{settings.discovery_engine_engine_id}"     # ← 调 Engine
    f"/servingConfigs/default_search"                      # ← Engine 暴露的入口
)
```

We **don't query the datastore directly** — we query the engine, which knows
which datastore(s) to consult. /
我们**不直接查 datastore** —— 我们查 engine，engine 自己知道要去哪个
datastore 找数据。

Datastore-level operations are different — used at ingestion time only /
Datastore 级别的操作是另一类，只在 ingestion 时用：

```python
# Import documents into the datastore (one-time)
# 把文档导入 datastore (一次性)
parent = f".../dataStores/{DATASTORE_ID}/branches/default_branch"
client.import_documents(...)   # ← document-level, directly on datastore
                                #   文档级操作，直接对 datastore
```

### Interview-grade summary / 面试级总结

If asked "how did you use Vertex AI Search?" /
如果有人问"你怎么用的 Vertex AI Search"：

> "Vertex AI Search splits the RAG backend into two layers: a **datastore**
> is the container of indexed documents, an **engine** is the query-serving
> service that fronts one or more datastores. I imported the OpenStax PDF
> into the datastore via `ImportDocuments`, which triggers Discovery Engine's
> internal layout parser, chunker, embedder, and indexer. Then I created a
> Standard-tier engine attached to that datastore. My FastAPI client queries
> through the engine's `serving_config`. This separation lets one indexed
> dataset serve multiple query modes, and lets the search tier change
> without re-indexing — both useful properties for a multi-corpus product."

> 中文版："Vertex AI Search 把 RAG 后端拆成两层：**datastore** 是已索引文档
> 的容器，**engine** 是暴露查询接口的服务。我用 `ImportDocuments` 把 OpenStax
> PDF 导入 datastore，Discovery Engine 内部跑了 layout parser、chunking、
> embedding 然后建了索引。然后建了一个 Standard tier 的 engine 挂到这个
> datastore 上。FastAPI 通过 engine 的 `serving_config` 发查询。这种分离
> 让一份索引数据可以喂多种查询模式，也让 search tier 升级不需要重新索引文档
> —— 对多语料的产品都是有用的属性。"

---

## Appendix — What's actually inside a Datastore?
## 附录 —— Datastore 内部到底装了什么？

A datastore is **not** "just a vector database." It's a **managed RAG-ready
document store** — a packaging of several retrieval mechanisms behind a
single API. Knowing what's inside makes the Phase 1 → Phase 2 narrative
concrete.

Datastore **不是**"单纯的向量数据库"。它是**managed 的 RAG-ready 文档存储**
—— 把多种检索机制打包在同一个 API 后面。理解内部结构就能讲清楚 Phase 1 →
Phase 2 的故事。

### Inside view / 剖面图

```
┌──────────────────────────────────────────────────────────────┐
│  DATASTORE  astronomy-2e-datastore                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Document b8a8860dee... (1 个,因为只导了 1 个 PDF)       │ │
│  │                                                        │ │
│  │  ├─ Original metadata                                  │ │
│  │  │   gcs_uri, title, doc_id, ingested_at, ...         │ │
│  │  │                                                    │ │
│  │  ├─ Chunks  (layout parser 切出的 N 段)                 │ │
│  │  │   ├─ chunk_001: "Kepler initially assumed..."      │ │
│  │  │   ├─ chunk_002: "Working with the data for..."     │ │
│  │  │   └─ ... (typically 100s of chunks per book)       │ │
│  │  │                                                    │ │
│  │  ├─ Embeddings  (1 vector per chunk)                  │ │
│  │  │   ├─ chunk_001 → [0.12, -0.34, 0.56, ...]         │ │← 向量数据库
│  │  │   ├─ chunk_002 → [0.45,  0.78, -0.21, ...]        │ │  在这里
│  │  │   └─ stored in an ANN index (HNSW-ish)             │ │
│  │  │      (内部用某种 ANN 索引,没公开是哪种)              │ │
│  │  │                                                    │ │
│  │  └─ Inverted index  (token → chunk_ids)               │ │← BM25 关键词
│  │      ├─ "kepler" → [chunk_001, chunk_007, ...]        │ │  检索在这里
│  │      ├─ "ellipse" → [chunk_002, chunk_015, ...]       │ │
│  │      └─ ...                                           │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### What you can NOT see / 你看不到的部分

The above is **what must be there given the system's behavior** — but
Discovery Engine is fully managed and **does not expose**:

- The actual chunking strategy (chunk size, overlap, boundary rules) /
  实际的分块策略 (块大小、重叠、边界规则)
- The embedding model used (Google internal, not named publicly) /
  使用的 embedding 模型 (Google 内部模型, 不公开)
- The ANN algorithm parameters (m, ef_construction, etc. for HNSW-class) /
  ANN 算法参数 (HNSW 类的 m, ef_construction 等)
- Per-chunk page numbers (Standard tier doesn't surface them) /
  每个 chunk 的页码 (Standard tier 不暴露)
- The raw chunks themselves — you can only see snippets at query time /
  原始 chunks 本身 —— 你只能在查询时看到 snippet

This **opacity is the price of "managed"**. You trade introspection /
control for not having to build any of it. /
**这种"看不见"是 managed 服务的代价**。你用可视化和可控性换取"什么都不用自己建"。

### The Phase 1 → Phase 2 mapping / Phase 1 到 Phase 2 的对应

The single best way to understand why Phase 2 exists is to see it as
**unpacking the Datastore black box layer by layer** /
理解 Phase 2 存在的最好方式: 把它看成**把 Datastore 这个黑盒一层层拆开**：

| Layer inside Datastore (Phase 1) | Phase 2 self-built equivalent |
|---|---|
| PDF parsing & layout detection | **Document AI Layout Parser** — exposes block-level (text/table/figure) + bbox + page |
| Chunking | **Recursive splitter, chapter-aware** — `chunk_size=800, overlap=120`, never split across chapters |
| Embedding generation | **`text-embedding-005` API call**, 768-dim, batched and cached |
| Vector storage + ANN index | **Cloud SQL `chunks.embedding` column + pgvector HNSW** (`m=16, ef_construction=64`) |
| Inverted (keyword) index | **Postgres `tsvector` + GIN index** for BM25 |
| Metadata filtering (book/chapter) | **Plain SQL columns** (`book_id`, `chapter_id`) with regular B-tree indexes |
| Snippet generation | **Hand-written prompt assembly** with explicit citation format |
| Reranking | **Gemini 2.5 Flash as LLM reranker** (Phase 1 has no reranker) |

每一行都是 **"Phase 1 让 Discovery Engine 做了什么 → Phase 2 自己用什么做"**。
Phase 2 的工作量大约是 Phase 1 的 2-3 倍, 换来对每一层的完全控制。

### What about the original PDF in GCS? / 原 PDF 在 GCS 里还需要吗？

Once `ImportDocuments` completes, the chunks and embeddings inside Datastore
are **independent copies**. Deleting the GCS PDF will not break search
queries for our setup (`contentConfig: CONTENT_REQUIRED`, which copies
content into Datastore). /

`ImportDocuments` 完成后, Datastore 里的 chunks 和 embeddings 是**独立副本**。
我们用的 `contentConfig: CONTENT_REQUIRED` 模式会复制内容进去, 所以删 GCS 里的
PDF **不会**导致搜索失效。

**Important exception** / **例外**: if you used `contentConfig:
PUBLIC_WEBSITE` or attached a BigQuery table directly, deleting the source
breaks search — those modes hold pointers, not copies. Always check which
mode you're in before tear-down. /

如果用的是 `PUBLIC_WEBSITE` 或者直接挂 BigQuery 表的模式, 那是引用关系不是
复制 —— 删原数据搜索就废了。teardown 前一定要确认是哪种模式。

---

## Appendix — What is "Discovery Engine" actually doing?
## 附录 —— "Discovery Engine" 到底做了哪些工作？

`discoveryengine.googleapis.com` is the **API name** behind the product
"Vertex AI Search" / "AI Applications" / "Agent Builder" (the marketing
name has changed several times since 2023). It is **not** a single service —
it's a portfolio of capabilities packaged together. /

`discoveryengine.googleapis.com` 是产品 "Vertex AI Search" / "AI Applications"
/ "Agent Builder"（市场名字 2023 年起改过好几次）背后的 **API 名称**。它**不是**
一个单一服务 —— 它是**一组能力的打包**。

### What Discovery Engine actually does internally
### Discovery Engine 内部到底在做什么

Roughly, the work splits into **ingestion-time** and **query-time** phases /
大致分**索引时**和**查询时**两个阶段：

```
═══ INGESTION-TIME (one-time per document) ═══
═══ 索引时 (每个文档一次)                    ═══

GCS PDF
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│ 1. PDF parsing                                          │
│    - Detects pages, blocks, headings, tables            │
│    - 检测页面、段落、标题、表格                            │
│    - On Standard tier: text only                         │
│    - On Enterprise tier: also extracts figures + bboxes │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Chunking                                             │
│    - Splits parsed text into retrieval-sized chunks     │
│    - 切成检索粒度的 chunks                                │
│    - Strategy NOT exposed (chunk size, overlap, etc.)   │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Embedding generation                                 │
│    - Each chunk → high-dim vector (Google's model)      │
│    - 每个 chunk → 高维向量 (Google 自有模型)              │
│    - Stored in the datastore's ANN index                │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 4. Inverted index build                                 │
│    - Tokenize, stem, build keyword → chunk index        │
│    - 构建关键词到 chunk 的倒排索引 (供 BM25 使用)         │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 5. Metadata index build                                 │
│    - book_id, structData fields → searchable filters    │
│    - 元数据字段建立可过滤索引                              │
└─────────────────────────────────────────────────────────┘

═══ QUERY-TIME (per request) ═══
═══ 查询时 (每个请求)         ═══

Query string + filter
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│ A. Query understanding                                  │
│    - Spell correction, query expansion (synonyms etc.)  │
│    - 拼写纠错、同义词扩展                                  │
│    - 我们的代码里 condition=AUTO 让它自动决定要不要扩展     │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ B. Embedding the query                                  │
│    - Same embedding model as ingestion                  │
│    - 用同一个模型把 query 变成向量                          │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ C. Hybrid retrieval (vector + keyword)                  │
│    - ANN search on embedding index                      │
│    - BM25 search on inverted index                      │
│    - Apply metadata filters                             │
│    - 向量 + 关键词 + 元数据过滤,内部融合                    │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ D. Result ranking & fusion                              │
│    - Combine signals into final ordering                │
│    - 把多路召回的结果融合排序                              │
│    - Algorithm NOT exposed                              │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ E. Snippet/extractive generation                        │
│    - For each top result, build a short relevant excerpt│
│    - 给每个结果生成一段相关的简短摘录                       │
│    - Standard tier: snippet only (highlighted text)     │
│    - Enterprise tier: also extractive segments + answers│
└──────────────────┬──────────────────────────────────────┘
                   ▼
SearchResponse  → 返回给我们的 FastAPI client
```

### So is Discovery Engine "an embedding model + a vector DB"?
### 所以 Discovery Engine 是 "embedding 模型 + 向量数据库" 吗？

**No** — it's substantially more. **It packages**:

**不是** —— 它不止于此。**它打包了**:

1. **A document parser** that handles PDF/HTML/DOCX/etc. /
   一个支持 PDF/HTML/DOCX 等的文档解析器
2. **A chunking strategy** /
   一套分块策略
3. **An embedding model + serving infrastructure** /
   一个 embedding 模型 + 推理服务
4. **A vector database** (with ANN index) /
   一个向量数据库 (带 ANN 索引)
5. **A keyword inverted index** (BM25-style) /
   一个关键词倒排索引 (BM25 风格)
6. **A query understanding layer** (spell-correct, expansion) /
   一层查询理解 (拼写纠错、查询扩展)
7. **A hybrid retrieval engine** (combines vector + keyword + filter) /
   一个混合检索引擎 (向量 + 关键词 + 过滤)
8. **A ranking / fusion algorithm** /
   一套排序融合算法
9. **A snippet/extract generator** /
   一个摘要/抽取生成器
10. **Multi-tenancy, scaling, billing, monitoring** (the boring but expensive plumbing) /
    多租户、扩展、计费、监控等基础设施

Built individually, each of these is a multi-week engineering project.
Discovery Engine bundles them — that's why it costs money, and that's why
"Phase 2 self-built" is a serious commitment, not a weekend rewrite. /

每一项单独建都是几周的工程项目。Discovery Engine 把它们打包 —— 这就是它收
钱的原因, 也是为什么 "Phase 2 self-built" 是个认真的承诺, 不是周末就能
重写完的事。

### Why a developer would still pick Phase 2 over Discovery Engine
### 为什么开发者还是会选 Phase 2 而不是 Discovery Engine

Despite Discovery Engine being objectively more capable, three reasons
push real teams to self-build /
尽管 Discovery Engine 客观上能力更全, 真实团队选择自建有三个理由：

1. **Cost at scale** — Per-query fees + indexing fees grow linearly. At
   high QPS, a self-hosted Cloud SQL + pgvector setup becomes cheaper. /
   **规模成本** —— 按查询和索引收费, 线性增长。高 QPS 下, 自建 Cloud SQL +
   pgvector 反而便宜。

2. **Control over relevance** — When Discovery Engine ranks the wrong
   chunk first and you can't tune the ranker, you have no fix. With
   self-built, you control every weight. /
   **相关性可控** —— Discovery Engine 排错了你也调不动。自建可以控每个权重。

3. **Domain-specific features** — Document AI Layout Parser exposes bbox
   and page-level metadata that Discovery Engine Standard hides. For
   citation-heavy products (legal, medical, NotebookLM-style), this is
   non-negotiable. /
   **领域特性** —— Layout Parser 暴露 bbox 和页码元数据, Discovery Engine
   Standard 隐藏。对法律/医疗/NotebookLM 这种重 citation 的产品, 是硬需求。

This project's two-phase design exists to **make exactly this comparison**
on real numbers, not on speculation. /
本项目的两阶段设计就是为了**用真实数据做这个对比**, 而不是凭空猜。

---

## Appendix — Structural noise: a concrete failure case
## 附录 —— 结构噪声：一个具体的失败案例

The previous appendix described **what** Discovery Engine does. This one
describes **what it does wrong on long-form structured documents** —
discovered by directly using the Console Preview tab against our deployed
engine. /

上一节附录讲了 Discovery Engine **做什么**。这一节讲它在**长篇结构化文档上
做错了什么** —— 是直接用 Console Preview 测试我们部署的 engine 时发现的。

### What I observed / 实际看到的现象

Two Console-Preview queries against `astronomy-2e-engine`:

| Query | Top snippet returned |
|---|---|
| `Hertzsprung Russell diagram` | "**Diagram** 609 Key Terms..." |
| `Slipher spiral nebulae redshift` | "We'll be discussing these 'death shroud' **nebulae** in Further Evolution of Stars. (b) Stephan's Quintet..." |

Neither snippet is from the body text that actually answers the question /
两个 snippet 都不是真正回答问题的正文：

- The H-R query landed on the **end-of-chapter Key Terms list** /
  H-R 查询落到了**章末术语列表**
- The Slipher query landed on a **figure caption** for an unrelated cluster
  (Stephan's Quintet, not Slipher's redshift work) /
  Slipher 查询落到了一个**毫无关系的图注**

### Why this happens / 为什么会这样

Discovery Engine indexes the entire 1,151-page PDF as **one document**
(Standard tier behavior). Inside that document, the parser/chunker doesn't
distinguish between block types — everything is just "text" /
Discovery Engine 把整本 1,151 页 PDF 当成**一个文档**索引（Standard tier 默认
行为）。在这个文档内部, parser/chunker 不区分 block 类型 —— 所有内容都是"text"：

- Body paragraphs (the actual explanations) ✅ 我们想要的
- Section headings / 章节标题
- Figure captions / 图注
- End-of-chapter **Key Terms** lists (glossary-style) / 章末术语表
- Chapter Summaries / 章节小结
- Review/Exercise questions / 复习题
- Appendices and indexes / 附录和索引

Worse, **terse glossary lines and figure captions often outscore long
expository prose** on short-query retrieval — keyword density per token
is higher in glossary entries than in body paragraphs. /
更糟的是, **简短的术语条目和图注在短查询检索中往往比长解释段落得分更高** ——
因为术语条目里关键词密度高于正文段落。

### Mapping the failure to Discovery Engine's pipeline
### 把这个失败映射到 Discovery Engine 的处理流水线

Going back to the ingestion-time pipeline diagram earlier in this learning,
the failure is concentrated in **steps 2–4** /
回到本文前面的 ingestion-time 流水线图, 失败集中在**步骤 2–4**：

| Pipeline step | What went wrong / 出了什么问题 |
|---|---|
| 1. PDF parsing | Captures everything correctly — including the structurally-irrelevant text |
|   PDF 解析 | 抓得没错 —— 但把所有文本都抓了, 包括结构上不相关的部分 |
| **2. Chunking** | **No block-type filtering**. Glossary entries become chunks just like body text. |
|   **分块** | **不按 block 类型过滤**。术语条目跟正文段落一样被切成 chunk。 |
| **3. Embedding** | Embeds glossary chunks with same weight as explanatory chunks. |
|   **嵌入** | 把术语 chunk 和讲解 chunk 用同样权重嵌入。 |
| **4. Inverted index** | Glossary entries (high keyword density) match better on short queries. |
|   **倒排索引** | 术语条目 (关键词密度高) 在短查询上匹配得更好。 |
| 5. Metadata filter | We have no metadata to filter on (book is one chunk-less PDF). |
|   元数据过滤 | 我们没有可用的元数据 (整本书是一个无 chunks 的 PDF)。 |

The root cause is that **Discovery Engine's chunking is structure-blind**.
It can't be configured to "only index body text" or "down-weight figure
captions" — those knobs simply aren't exposed. /
根本原因是 **Discovery Engine 的 chunking 对结构无感**。它没有"只索引正文" 或
"降低图注权重"这种配置 —— 这些旋钮根本没暴露给用户。

### What Phase 2 does differently / Phase 2 怎么不一样

Document AI Layout Parser (which Phase 2 uses for ingestion) returns blocks
with a `layoutType` field. Typical values: /
Document AI Layout Parser (Phase 2 ingestion 用的) 返回的 block 带 `layoutType`
字段, 典型值有：

- `heading-1` / `heading-2` (chapter / section titles)
- `body-text` (the explanatory prose we usually want)
- `list-item` (Key Terms, exercises)
- `caption` (figure / table captions)
- `table-cell` (table content)
- `footer` / `header` (page furniture)

Phase 2 chunking can then make explicit choices /
Phase 2 chunking 可以做明确的选择:

```python
# Phase 2 ingestion sketch — block-type aware filtering
for block in document_ai.parse(pdf):
    if block.layoutType in {"body-text", "heading-1", "heading-2"}:
        chunk_for_main_index(block)
    elif block.layoutType == "caption":
        chunk_for_figure_index(block)   # separate index, only retrieved on figure queries
    elif block.layoutType in {"list-item", "footer", "header"}:
        skip()                          # don't index at all
```

The same physical PDF, indexed this way, would not have surfaced "Diagram
609 Key Terms" for the H-R query — that block would simply not exist in
the body-text index. /
同一份物理 PDF, 用这种方式索引, "Diagram 609 Key Terms" 不会出现在 H-R 查询的
结果里 —— 那个 block 根本不在正文索引里。

### Why this is in **this** learning / 为什么写在这一篇里

This appendix sits in 07 (the Vertex AI Search setup learning) rather than
08 (the baseline interpretation) because the failure is fundamentally
about **what Discovery Engine does internally**. The Console-Preview view
of structural noise is the most direct evidence that "managed RAG is
opaque to structure" — a property of the service itself, not of how we
configured it. /

这段附录写在 07 (Vertex AI Search 部署) 而不是 08 (baseline 解读), 是因为这个
失败本质上是 **Discovery Engine 内部的事**。Console Preview 看到的结构噪声是
"managed RAG 对结构无感"的最直接证据 —— 这是服务本身的属性, 不是我们怎么配它的
问题。

For the **user-facing impact** of this same failure (over-refusal,
0% citation accuracy, 0% on chapter_scoped buckets), see
`learnings/08-phase1-baseline-interpretation.md`. /
关于这个失败的**用户感知影响** (过度拒答、0% citation accuracy、chapter_scoped
桶 0%), 见 `learnings/08-phase1-baseline-interpretation.md`。
