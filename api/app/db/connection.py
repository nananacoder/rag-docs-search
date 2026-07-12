"""Dual-mode asyncpg pool (phase2-selfbuilt.md §2.5).

DB_MODE=cloudsql — cloud-sql-python-connector with IAM auth: no password
anywhere, the ambient identity (Cloud Run service account, or your gcloud
ADC in local dev) obtains short-lived tokens.
DB_MODE=direct — plain DSN, for CI and local docker Postgres, which have
no GCP credentials.

Both modes install the same connection init (pgvector codec + JSONB codec),
so everything above this module is mode-agnostic.
"""

import asyncio
import json
from typing import Any, cast

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()
_connector: Any = None  # google.cloud.sql.connector.Connector, cloudsql mode only


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection setup: teach asyncpg the vector type and JSONB<->dict."""
    await register_vector(conn)
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool, _connector
    async with _pool_lock:
        if _pool is not None:
            return _pool

        settings = get_settings()
        if settings.db_mode == "direct":
            if not settings.database_url:
                raise ValueError("DATABASE_URL is required when DB_MODE=direct")
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
                init=_init_connection,
            )
        else:
            # Imported lazily so direct-mode environments (CI) don't need
            # GCP credentials just to import this module.
            from google.cloud.sql.connector import create_async_connector

            if not settings.db_iam_user:
                raise ValueError("DB_IAM_USER is required when DB_MODE=cloudsql")
            # lazy refresh per GCP's June 2026 serverless guidance:
            # no background token refresh burning CPU between requests.
            _connector = await create_async_connector(refresh_strategy="lazy")
            instance = settings.db_instance_connection_name

            # asyncpg's pool invokes this with (loop=…, connection_class=…,
            # record_class=…) kwargs — accept and discard them; the connector
            # builds the connection itself.
            async def _connect(*_args: Any, **_kwargs: Any) -> asyncpg.Connection:
                conn = await _connector.connect_async(
                    instance,
                    "asyncpg",
                    user=settings.db_iam_user,
                    db=settings.db_name,
                    enable_iam_auth=True,  # IAM-issued token, no password
                )
                return cast(asyncpg.Connection, conn)

            _pool = await asyncpg.create_pool(
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
                connect=_connect,
                init=_init_connection,
            )

        logger.info(
            "db_pool_created",
            db_mode=settings.db_mode,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
        )
        return _pool


async def close_pool() -> None:
    """FastAPI lifespan shutdown hook."""
    global _pool, _connector
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None
        if _connector is not None:
            await _connector.close_async()
            _connector = None
        logger.info("db_pool_closed")
