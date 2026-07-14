# ADR-006: Figures as Gemini-Vision captions, not multimodal embeddings

**Status**: Accepted, shipped (M3, route B+). **Measured**: figure bucket 0% → 100% keyword.

## Decision
Extract embedded images (pymupdf, sha256-deduped, icon-filtered → 678
figures), caption each with Gemini Vision using an astronomy-specific
prompt, store captions as `modality='figure'` chunks — embedded and
BM25-indexed like text. Captions cached by image hash (re-ingest free).

## Why captions over CLIP-style multimodal embeddings
One unified BM25+vector pipeline instead of a second index; captions are
human-readable in the citation panel; BM25 keeps working (images have no
words); cheaper (~$1 for the whole book).

## Upgrade paths, in order
1. "Retrieve by caption, generate from the raw image" — pass the actual
   figure to multimodal Gemini at generation time; no index change.
2. Native multimodal embeddings — if caption quality caps the figure
   bucket (eval will say).
3. ColPali page-image late-interaction — Phase 3 research track
   (learnings/10 Deferral 1); incompatible with HNSW storage.
