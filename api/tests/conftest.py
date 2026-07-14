"""Test-environment isolation: tests must not inherit the developer's .env
backend (learned when RETRIEVAL_BACKEND=pgvector made smoke tests dial the
stopped Cloud SQL instance). Real env vars take precedence over .env in
pydantic-settings, so setting them here pins the test config regardless of
local dev state. test_db_roundtrip overrides DB_MODE itself.
"""

import os

os.environ["RETRIEVAL_BACKEND"] = "mock"
os.environ.setdefault("DB_MODE", "direct")
