"""Append-only, hash-chained audit log.

Each entry commits to the previous entry's hash, so any edit or deletion of
history is detectable by `verify()`. In production the same chain lives in an
append-only Postgres table (see migrations/001_init.sql) with UPDATE/DELETE revoked.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

GENESIS = "0" * 64


@dataclass(frozen=True, slots=True)
class AuditEntry:
    seq: int
    at: str
    actor: str
    entity_id: str
    action: str
    data: dict[str, Any]
    prev_hash: str
    hash: str


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class AuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self, *, actor: str, entity_id: str, action: str, at: datetime, data: dict[str, Any] | None = None
    ) -> AuditEntry:
        prev = self._entries[-1].hash if self._entries else GENESIS
        body: dict[str, Any] = {
            "seq": len(self._entries),
            "at": at.isoformat(),
            "actor": actor,
            "entity_id": entity_id,
            "action": action,
            "data": data or {},
            "prev_hash": prev,
        }
        entry = AuditEntry(**body, hash=_digest(body))
        self._entries.append(entry)
        return entry

    def for_entity(self, entity_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.entity_id == entity_id]

    def verify(self) -> bool:
        prev = GENESIS
        for i, e in enumerate(self._entries):
            body = {k: v for k, v in asdict(e).items() if k != "hash"}
            if e.seq != i or e.prev_hash != prev or _digest(body) != e.hash:
                return False
            prev = e.hash
        return True

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)
