"""Hermes proactive control helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brainstack.db import BrainstackStore


def list_items(*, db_path: Path, principal_scope_key: str = "", state: str = "", limit: int = 50) -> dict[str, Any]:
    store = BrainstackStore(str(db_path))
    store.open()
    try:
        return {"schema": "hermes_proactive.control.v1", "items": store.list_proactive_items(principal_scope_key=principal_scope_key, state=state, limit=limit)}
    finally:
        store.close()


def inspect_item(*, db_path: Path, event_id: str) -> dict[str, Any]:
    store = BrainstackStore(str(db_path))
    store.open()
    try:
        return store.inspect_proactive_item(event_id=event_id)
    finally:
        store.close()


def set_item_state(*, db_path: Path, event_id: str, state: str, reason_code: str, actor: str = "operator") -> dict[str, Any]:
    store = BrainstackStore(str(db_path))
    store.open()
    try:
        return store.set_proactive_item_state(event_id=event_id, state=state, reason_code=reason_code, actor=actor)
    finally:
        store.close()
