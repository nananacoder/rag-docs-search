"""Stream the corpus PDF from GCS, same-origin, with HTTP Range support.

The Angular source pane renders the PDF for bbox highlighting. pdf.js pulls
byte ranges so it never downloads the whole 155MB file — this proxy honors
`Range` and caps open-ended ranges to a window so memory stays bounded. A
same-origin proxy (vs redirecting to storage.googleapis.com) sidesteps GCS
CORS config entirely.

Reads use the sync google-cloud-storage client in a thread (asyncpg-style),
so they don't block the event loop.
"""

import asyncio
import re

from fastapi import APIRouter, Header, HTTPException, Response

from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(prefix="/pdf", tags=["pdf"])
log = get_logger(__name__)

_RANGE_WINDOW = 2 * 1024 * 1024  # cap open-ended ranges at 2MB per response
_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    bucket, _, obj = uri.removeprefix("gs://").partition("/")
    return bucket, obj


def _blob_size(bucket: str, obj: str) -> int:
    from google.cloud import storage  # type: ignore[attr-defined]

    blob = storage.Client().bucket(bucket).blob(obj)
    blob.reload()
    return int(blob.size)


def _download_range(bucket: str, obj: str, start: int, end: int) -> bytes:
    from google.cloud import storage  # type: ignore[attr-defined]

    blob = storage.Client().bucket(bucket).blob(obj)
    data: bytes = blob.download_as_bytes(start=start, end=end)  # end inclusive
    return data


@router.get("/{name}")
async def get_pdf(name: str, range_header: str | None = Header(None, alias="Range")) -> Response:
    settings = get_settings()
    bucket, obj = _parse_gcs_uri(settings.pdf_gcs_uri)

    try:
        size = await asyncio.to_thread(_blob_size, bucket, obj)
    except Exception as exc:  # object missing / no GCS creds
        log.warning("pdf_blob_unavailable", error=str(exc), uri=settings.pdf_gcs_uri)
        raise HTTPException(status_code=404, detail="PDF not available") from exc

    common = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}

    if not range_header or not (m := _RANGE_RE.search(range_header)):
        # No range: advertise range support and return the first window so
        # pdf.js switches to range requests without pulling the whole file.
        end = min(_RANGE_WINDOW - 1, size - 1)
        data = await asyncio.to_thread(_download_range, bucket, obj, 0, end)
        return Response(
            content=data, status_code=206, media_type="application/pdf",
            headers={**common, "Content-Range": f"bytes 0-{end}/{size}",
                     "Content-Length": str(len(data))},
        )

    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start + _RANGE_WINDOW - 1
    end = min(end, size - 1)
    if start >= size or start > end:
        raise HTTPException(
            status_code=416, headers={"Content-Range": f"bytes */{size}"}
        )
    data = await asyncio.to_thread(_download_range, bucket, obj, start, end)
    return Response(
        content=data, status_code=206, media_type="application/pdf",
        headers={**common, "Content-Range": f"bytes {start}-{end}/{size}",
                 "Content-Length": str(len(data))},
    )
