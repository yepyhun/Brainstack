from __future__ import annotations

from typing import Any, Dict, Mapping


OUTPUT_ENFORCEMENT_MODE_ORDINARY_REPLY = "ordinary_reply"
OUTPUT_ENFORCEMENT_MODE_STRICT = "strict_contract"


def build_output_contract(compiled_policy: Mapping[str, Any] | None) -> Dict[str, Any]:
    del compiled_policy
    return {
        "active": False,
        "sources": [],
    }


def validate_output_against_contract(
    *,
    content: str,
    compiled_policy: Mapping[str, Any] | None,
    enforcement_mode: str = OUTPUT_ENFORCEMENT_MODE_ORDINARY_REPLY,
) -> Dict[str, Any]:
    del compiled_policy
    return {
        "content": str(content or ""),
        "changed": False,
        "applied": False,
        "status": "inactive",
        "blocked": False,
        "can_ship": True,
        "block_reason": "",
        "contract": build_output_contract(None),
        "enforcement_mode": enforcement_mode,
        "repairs": [],
        "remaining_violations": [],
    }
