"""Tiny persistent JSON cache for embeddings/captions (§4.4).

Local-dir JSON per namespace; cheap and sufficient for a personal project.
(The design allows a GCS-backed variant later — same interface.)
"""

import json
import pathlib
from typing import Any


class JsonCache:
    def __init__(self, cache_dir: str, namespace: str) -> None:
        self._path = pathlib.Path(cache_dir) / f"{namespace}.json"
        self._data: dict[str, Any] = {}
        if self._path.exists():
            self._data = json.loads(self._path.read_text())

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data))

    def __len__(self) -> int:
        return len(self._data)
