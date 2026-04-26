"""Memory scope contracts.

Brainstack scope metadata describes evidence boundaries. It does not schedule,
approve, or execute runtime work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .ids import ScopeKey


class ScopeKind(StrEnum):
    PRINCIPAL = "principal"
    WORKSPACE = "workspace"
    SESSION = "session"
    WORKSTREAM = "workstream"
    CANARY = "canary"


@dataclass(frozen=True, slots=True)
class MemoryScope:
    principal_scope_key: ScopeKey
    workspace_scope: str | None = None
    session_id: str | None = None
    workstream_id: str | None = None
    canary_run_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "principal_scope_key": str(self.principal_scope_key),
            "workspace_scope": self.workspace_scope,
            "session_id": self.session_id,
            "workstream_id": self.workstream_id,
            "canary_run_id": self.canary_run_id,
        }
