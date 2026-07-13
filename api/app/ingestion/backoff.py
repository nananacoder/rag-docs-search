"""Shared retry policy for Vertex LLM calls: exponential backoff on
429/503. 8-way→4-way concurrency still brushes RPM quotas; riding out the
window beats crashing a 20-minute ingest run."""

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def is_retryable(exc: BaseException) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code in (429, 503)


llm_retry = retry(
    retry=retry_if_exception(is_retryable),
    wait=wait_exponential(multiplier=2, max=60),
    stop=stop_after_attempt(8),
)
