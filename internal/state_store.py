from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from threading import Lock

from internal.registry import UpstreamServerDefinition


@dataclass(slots=True)
class RouterStateSnapshot:
    upstreams: list[UpstreamServerDefinition]


class RouterStateStore:
    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        self._lock = Lock()

    @property
    def state_path(self) -> Path:
        return self._state_path

    def load(self) -> RouterStateSnapshot:
        with self._lock:
            if not self._state_path.exists():
                return RouterStateSnapshot(upstreams=[])
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        upstreams = [
            UpstreamServerDefinition.from_record(item)
            for item in payload.get("upstreams", [])
        ]
        return RouterStateSnapshot(upstreams=upstreams)

    def save_upstreams(self, upstreams: list[UpstreamServerDefinition]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "updatedAt": datetime.now(UTC).isoformat(),
            "upstreams": [item.to_record() for item in upstreams],
        }
        with self._lock:
            self._state_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def upsert_upstream(self, upstream: UpstreamServerDefinition) -> None:
        snapshot = self.load()
        merged: dict[str, UpstreamServerDefinition] = {
            item.server_id: item for item in snapshot.upstreams
        }
        merged[upstream.server_id] = upstream
        self.save_upstreams(list(merged.values()))

    def delete_upstream(self, server_id: str) -> bool:
        snapshot = self.load()
        merged = {item.server_id: item for item in snapshot.upstreams}
        deleted = merged.pop(server_id, None)
        self.save_upstreams(list(merged.values()))
        return deleted is not None
