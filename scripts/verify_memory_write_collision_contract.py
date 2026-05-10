#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.memory_write_collision import (  # noqa: E402
    COLLISION_SOURCE_INTEGRITY_VIOLATION,
    COLLISION_UNSAFE_AUTHORITY_SHRINK,
    attach_write_collision_if_any,
    build_memory_write_collision,
)
from brainstack.style_contract import STYLE_CONTRACT_SLOT, list_style_contract_rules  # noqa: E402


def _contract(lines: list[str]) -> str:
    return "Public behavior contract\n\nRules:\n" + "\n".join(f"- {line}" for line in lines)


def _remember(provider: BrainstackMemoryProvider, *, stable_key: str, content: str) -> dict[str, Any]:
    return json.loads(
        provider.handle_tool_call(
            "brainstack_remember",
            {
                "shelf": "profile",
                "stable_key": stable_key,
                "category": "style_preference",
                "content": content,
                "source_role": "user",
                "authority_class": "profile",
                "confidence": 0.99,
                "metadata": {"target_slot": stable_key},
            },
        )
    )


def build_report() -> dict[str, Any]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-write-collision-") as temp:
        tmp = Path(temp)
        provider = BrainstackMemoryProvider(
            {
                "db_path": str(tmp / "brainstack.db"),
                "graph_backend": "sqlite",
                "corpus_backend": "sqlite",
            }
        )
        provider.initialize(
            "collision-proof",
            platform="test",
            user_id="user-public",
            agent_identity="collision-agent",
            agent_workspace="workspace",
        )
        try:
            full = _remember(
                provider,
                stable_key="preference.fixture_full_style",
                content=_contract([f"Rule {index:02d} survives." for index in range(1, 6)]),
            )
            small = _remember(
                provider,
                stable_key="preference.fixture_tiny_style",
                content=_contract(["Tiny replacement must not shrink active card."]),
            )
            assert provider._store is not None
            active = provider._store.get_profile_item(stable_key=STYLE_CONTRACT_SLOT, principal_scope_key=provider._principal_scope_key)
            active_rules = list_style_contract_rules(raw_text=active.get("content"), metadata=active.get("metadata")) if active else []
            source_violation = build_memory_write_collision(
                code=COLLISION_SOURCE_INTEGRITY_VIOLATION,
                reason="Source fingerprint changed before write.",
                affected_authority="current_truth",
                mutation_status="blocked_no_mutation",
                next_safe_action="re_admit_from_updated_source",
            )
            duplicate_like = attach_write_collision_if_any({"status": "committed", "schema": "fixture"})
            proof = {
                "initial_style_contract_materialized": full["style_contract_materialization"]["status"] == "materialized",
                "unsafe_shrink_gets_structured_collision": small.get("write_collision", {}).get("code")
                == COLLISION_UNSAFE_AUTHORITY_SHRINK,
                "unsafe_shrink_is_not_final_success": small.get("final_state_success") is False,
                "active_card_preserved_after_small_write": len(active_rules) >= 5,
                "source_integrity_collision_has_next_action": source_violation["next_safe_action"]
                == "re_admit_from_updated_source",
                "non_collision_receipt_keeps_success_semantics": duplicate_like.get("final_state_success") is True,
            }
            issues = [key for key, value in proof.items() if value is not True]
            return {
                "schema": "brainstack.memory_write_collision_contract_verifier.v1",
                "status": "pass" if not issues else "fail",
                "public_safe": True,
                "llm_calls_performed": False,
                "issues": issues,
                "proof": proof,
                "collision_codes": [
                    small.get("write_collision", {}).get("code", ""),
                    source_violation["code"],
                ],
            }
        finally:
            provider.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "status", "issues")}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
