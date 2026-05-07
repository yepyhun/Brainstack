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
from brainstack.maintenance import STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS  # noqa: E402
from brainstack.retrieval import build_system_prompt_projection  # noqa: E402
from brainstack.style_contract import STYLE_CONTRACT_SLOT  # noqa: E402


REPORT_SCHEMA = "brainstack.style_source_hygiene_repair_proof.v1"


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "style-source-hygiene-proof",
        platform="test",
        user_id="public-user",
        agent_identity="agent-style-source-hygiene-proof",
        agent_workspace="workspace",
    )
    if provider._store is None:
        raise RuntimeError("Brainstack store unavailable")
    return provider


def _contract_text() -> str:
    rules = [f"Public fixture rule {index:02d} remains canonical." for index in range(1, 27)]
    return "Public fixture behavior contract\n\nRules:\n" + "\n".join(f"- {rule}" for rule in rules)


def _seed(provider: BrainstackMemoryProvider) -> None:
    if provider._store is None:
        raise RuntimeError("Brainstack store unavailable")
    scope = provider._principal_scope_key
    provider.handle_tool_call(
        "brainstack_remember",
        {
            "shelf": "profile",
            "stable_key": "preference.public_fixture_rule_pack",
            "category": "style_preference",
            "content": _contract_text(),
            "source_role": "user",
            "authority_class": "profile",
            "confidence": 0.99,
            "metadata": {"target_slot": "preference.public_fixture_rule_pack"},
        },
    )
    for stable_key, category, content in (
        ("identity:public_fixture_user", "identity", "The public fixture user's handle is ExampleUser."),
        ("style_no_decorative_symbols", "style_preference", "Legacy behavior source row one."),
        ("preference.public_fixture_old_style", "communication_style", "Legacy behavior source row two."),
        ("preference:communication_style", "preference", "Legacy behavior source row three."),
    ):
        provider._store.upsert_profile_item(
            stable_key=stable_key,
            category=category,
            content=content,
            source="proof:dirty_live_shape",
            confidence=0.99,
            metadata={"principal_scope_key": scope},
        )


def build_report() -> dict[str, Any]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="brainstack_style_source_hygiene_") as tmp:
        provider = _provider(Path(tmp))
        try:
            _seed(provider)
            if provider._store is None:
                raise RuntimeError("Brainstack store unavailable")
            canonical_before = provider._store.get_profile_item(
                stable_key=STYLE_CONTRACT_SLOT,
                principal_scope_key=provider._principal_scope_key,
            )
            dry_run = json.loads(
                provider.handle_tool_call(
                    "brainstack_consolidate",
                    {"apply": False, "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS},
                )
            )
            rejected = json.loads(
                provider.handle_tool_call(
                    "brainstack_consolidate",
                    {"apply": True, "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS},
                )
            )
            applied = json.loads(
                provider.handle_tool_call(
                    "brainstack_consolidate",
                    {
                        "apply": True,
                        "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS,
                        "explicit_user_request": True,
                    },
                )
            )
            canonical_after = provider._store.get_profile_item(
                stable_key=STYLE_CONTRACT_SLOT,
                principal_scope_key=provider._principal_scope_key,
            )
            projection = build_system_prompt_projection(
                provider._store,
                profile_limit=8,
                principal_scope_key=provider._principal_scope_key,
                session_id="style-source-hygiene-proof",
            )
            block = str(projection["block"])
            result = applied["changes"][0]["result"] if applied.get("changes") else {}
            if rejected.get("status") != "rejected":
                issues.append("apply_without_explicit_user_request_not_rejected")
            if result.get("status") != "applied":
                issues.append("explicit_repair_not_applied")
            if int(result.get("demoted_count") or 0) != 4:
                issues.append("unexpected_demoted_count")
            if int(result.get("remaining_candidate_count") or 0) != 0:
                issues.append("remaining_legacy_behavior_sources")
            if canonical_before != canonical_after:
                issues.append("canonical_card_changed")
            if "Public fixture rule 26 remains canonical." not in block:
                issues.append("agent_facing_card_missing_final_rule")
            if "Legacy behavior source row" in block:
                issues.append("legacy_source_rendered_after_repair")
            if "Legacy behavior source row" in json.dumps(result, ensure_ascii=False):
                issues.append("raw_source_text_leaked_in_report")
            if str(result.get("backup_path") or ""):
                issues.append("model_facing_backup_path_exposed")
            proof = {
                "dirty_live_shaped_fixture": True,
                "dry_run_reports_candidates": any(
                    item.get("maintenance_class") == STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS
                    and int(item.get("candidate_count") or 0) == 4
                    for item in ((dry_run.get("dry_run") or {}).get("candidates") or [])
                ),
                "apply_requires_explicit_user_request": rejected.get("status") == "rejected",
                "canonical_card_unchanged": canonical_before == canonical_after,
                "legacy_sources_demoted": int(result.get("demoted_count") or 0) == 4,
                "agent_facing_card_still_delivered": "Public fixture rule 26 remains canonical." in block,
                "legacy_sources_not_prompt_authority": "Legacy behavior source row" not in block,
                "no_behavior_contract_rows_created": (result.get("final_state_proof") or {}).get("behavior_contract_rows_created") == 0,
                "no_compiled_policy_rows_created": (result.get("final_state_proof") or {}).get("compiled_behavior_policy_rows_created") == 0,
                "public_safe_report": "Legacy behavior source row" not in json.dumps(result, ensure_ascii=False),
                "model_facing_backup_path_not_exposed": not str(result.get("backup_path") or ""),
            }
        finally:
            provider.shutdown()
    status = "pass" if not issues and all(proof.values()) else "fail"
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "issues": issues,
        "public_safe": True,
        "proof": proof,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify style source hygiene repair final-state behavior.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
