#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider
from brainstack.active_preference_contract import (
    DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION,
    DELIVERY_REASON_SESSION_START,
)
from brainstack.retrieval import build_system_prompt_projection
from brainstack.style_contract import STYLE_CONTRACT_SLOT, list_style_contract_rules


REPORT_SCHEMA = "brainstack.behavior_card_destructive_proof.v1"


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "behavior-card-destructive-proof",
        platform="test",
        user_id="public-user",
        agent_identity="agent-behavior-card-proof",
        agent_workspace="workspace",
    )
    if provider._store is None:
        raise RuntimeError("Brainstack store did not initialize")
    return provider


def _rules(prefix: str, count: int) -> list[str]:
    return [f"{prefix} rule {index:02d} must stay explicit and public-safe." for index in range(1, count + 1)]


def _contract_text(title: str, rules: list[str]) -> str:
    return title + "\n\nRules:\n" + "\n".join(f"- {line}" for line in rules)


def _remember(provider: BrainstackMemoryProvider, *, stable_key: str, category: str, content: str) -> dict[str, Any]:
    return json.loads(
        provider.handle_tool_call(
            "brainstack_remember",
            {
                "shelf": "profile",
                "stable_key": stable_key,
                "category": category,
                "content": content,
                "source_role": "user",
                "authority_class": "profile",
                "confidence": 0.99,
                "metadata": {"target_slot": stable_key},
            },
        )
    )


def _canonical(provider: BrainstackMemoryProvider) -> dict[str, Any]:
    if provider._store is None:
        raise RuntimeError("Brainstack store unavailable")
    row = provider._store.get_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        principal_scope_key=provider._principal_scope_key,
    )
    if not isinstance(row, dict):
        raise AssertionError("canonical style contract missing")
    return row


def _rule_count(row: Mapping[str, Any]) -> int:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    return len(list_style_contract_rules(raw_text=row.get("content"), metadata=metadata))


def _delivery_trace(provider: BrainstackMemoryProvider) -> dict[str, Any]:
    return provider.behavior_policy_trace()["system_prompt_block"]["active_preference_contract_delivery"]


def _assert_lines_in_block(block: str, lines: list[str], issues: list[str], prefix: str) -> None:
    if "# Brainstack Active User Preference Contract" not in block:
        issues.append(f"{prefix}:missing_active_contract_section")
    for line in lines:
        if line not in block:
            issues.append(f"{prefix}:missing_rule:{line}")


def build_report() -> dict[str, Any]:
    issues: list[str] = []
    details: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="brainstack_behavior_card_destructive_") as tmp:
        provider = _provider(Path(tmp))
        try:
            original_rules = _rules("Original", 25)
            original_receipt = _remember(
                provider,
                stable_key="preference.public_fixture_original_behavior_rules",
                category="communication_style",
                content=_contract_text("Public fixture original style contract", original_rules),
            )
            original_materialization = original_receipt.get("style_contract_materialization", {})
            if original_materialization.get("status") != "materialized":
                issues.append("original_card_not_materialized")
            if int(original_materialization.get("rule_count") or 0) != 25:
                issues.append("original_card_rule_count_not_25")

            collapsed_summary = (
                "User response style rules: start directly, answer yes or no first, avoid decorative symbols, "
                "avoid inflated claims, keep terms stable, use simple verbs, state confidence, and apply all prior "
                "public fixture rules as one compressed summary."
            )
            collapsed_receipt = _remember(
                provider,
                stable_key="preference.public_fixture_collapsed_behavior_summary",
                category="style_preference",
                content=collapsed_summary,
            )
            collapsed_materialization = collapsed_receipt.get("style_contract_materialization", {})
            if collapsed_materialization.get("status") != "skipped":
                issues.append("collapsed_summary_materialized")
            if collapsed_materialization.get("active_card_mutated") is not False:
                issues.append("collapsed_summary_mutated_card")

            one_rule_receipt = _remember(
                provider,
                stable_key="preference.public_fixture_one_rule_addition",
                category="style_preference",
                content="User style contract rule-pack addition:\n- Use direct nontechnical wording.",
            )
            one_rule_materialization = one_rule_receipt.get("style_contract_materialization", {})
            if one_rule_materialization.get("reason_code") != "would_shrink_existing_style_contract":
                issues.append("one_rule_addition_not_blocked_by_shrink_guard")
            if one_rule_materialization.get("active_card_mutated") is not False:
                issues.append("one_rule_addition_mutated_card")

            non_behavior_receipt = _remember(
                provider,
                stable_key="work_context.public_fixture_rule_like_context",
                category="work_context",
                content=_contract_text("Public fixture non-behavior note", _rules("Non behavior", 5)),
            )
            non_behavior_materialization = non_behavior_receipt.get("style_contract_materialization", {})
            if non_behavior_materialization.get("reason_code") != "not_behavior_style_profile_capture":
                issues.append("non_behavior_profile_not_rejected")

            canonical_after_blocks = _canonical(provider)
            if _rule_count(canonical_after_blocks) != 25:
                issues.append("canonical_rule_count_changed_after_blocked_writes")
            canonical_content = str(canonical_after_blocks.get("content") or "")
            if "Use direct nontechnical wording." in canonical_content:
                issues.append("blocked_one_rule_appeared_in_canonical_card")
            if collapsed_summary in canonical_content:
                issues.append("collapsed_summary_appeared_in_canonical_card")
            for line in original_rules:
                if line not in canonical_content:
                    issues.append("original_rule_missing_after_blocked_writes")
                    break

            replacement_rules = _rules("Replacement", 25)
            replacement_receipt = _remember(
                provider,
                stable_key="preference.public_fixture_full_replacement_behavior_rules",
                category="communication_style",
                content=_contract_text("Public fixture replacement style contract", replacement_rules),
            )
            replacement_materialization = replacement_receipt.get("style_contract_materialization", {})
            if replacement_materialization.get("status") != "materialized":
                issues.append("full_structured_replacement_not_materialized")
            if int(replacement_materialization.get("rule_count") or 0) != 25:
                issues.append("full_structured_replacement_rule_count_not_25")
            canonical_after_replace = _canonical(provider)
            replacement_content = str(canonical_after_replace.get("content") or "")
            for line in replacement_rules:
                if line not in replacement_content:
                    issues.append("replacement_rule_missing_from_canonical_card")
                    break
            if original_rules[0] in replacement_content:
                issues.append("old_rule_survived_full_replacement")

            block = provider.system_prompt_block()
            _assert_lines_in_block(block, replacement_rules, issues, "session_start")
            if collapsed_summary in block or "Use direct nontechnical wording." in block:
                issues.append("blocked_source_material_rendered_in_prompt")
            trace = _delivery_trace(provider)
            if trace.get("delivery_reason") != DELIVERY_REASON_SESSION_START:
                issues.append("session_start_delivery_reason_wrong")
            if trace.get("generic_profile_fallback_status") != "supplemental_source_profile_suppressed":
                issues.append("source_profile_not_suppressed_after_replacement")

            provider.on_turn_start(4, "Public fixture turn before compression.")
            provider.on_pre_compress(
                [
                    {"role": "user", "content": "Start public fixture conversation."},
                    {"role": "assistant", "content": "Public fixture response."},
                    {"role": "user", "content": "Compress public fixture context."},
                ]
            )
            compressed_block = provider.system_prompt_block()
            _assert_lines_in_block(compressed_block, replacement_rules, issues, "compression")
            compressed_trace = _delivery_trace(provider)
            if compressed_trace.get("delivery_reason") != DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION:
                issues.append("compression_delivery_reason_wrong")

            large_rules = [
                (
                    f"Large card rule {index:02d} keeps a bounded public-safe behavior instruction with enough "
                    "words to exercise warning thresholds without private data."
                )
                for index in range(1, 85)
            ]
            large_receipt = _remember(
                provider,
                stable_key="preference.public_fixture_large_behavior_rules",
                category="communication_style",
                content=_contract_text("Public fixture large style contract", large_rules),
            )
            if large_receipt.get("style_contract_materialization", {}).get("status") != "materialized":
                issues.append("large_card_not_materialized")
            projection = build_system_prompt_projection(
                provider._store,
                profile_limit=6,
                principal_scope_key=provider._principal_scope_key,
                session_id="behavior-card-destructive-proof",
                behavior_contract_char_budget=24000,
            )
            warning = projection["active_preference_delivery_inspect"]["active_card_size_warning"]
            if warning.get("status") != "warn" or warning.get("should_warn_user") is not True:
                issues.append("large_card_warning_missing")
            if str(warning.get("agent_safe_warning") or "") in str(projection.get("block") or ""):
                issues.append("large_card_warning_spammed_into_prompt")

            details = {
                "original_materialization_status": original_materialization.get("status"),
                "collapsed_status": collapsed_materialization.get("status"),
                "collapsed_reason": collapsed_materialization.get("reason_code"),
                "one_rule_status": one_rule_materialization.get("status"),
                "one_rule_reason": one_rule_materialization.get("reason_code"),
                "one_rule_agent_safe_status": one_rule_materialization.get("agent_safe_status"),
                "non_behavior_reason": non_behavior_materialization.get("reason_code"),
                "replacement_status": replacement_materialization.get("status"),
                "replacement_rule_count": int(replacement_materialization.get("rule_count") or 0),
                "session_delivery_status": trace.get("delivery_status"),
                "compression_delivery_status": compressed_trace.get("delivery_status"),
                "source_profile_fallback_status": trace.get("generic_profile_fallback_status"),
                "large_card_warning_status": warning.get("status"),
                "large_card_should_warn_user": bool(warning.get("should_warn_user")),
            }
        finally:
            provider.shutdown()

    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "public_safe": True,
        "proof": {
            "dirty_live_shaped_fixture": True,
            "small_write_cannot_shrink_active_card": "one_rule_addition_not_blocked_by_shrink_guard" not in issues
            and "one_rule_addition_mutated_card" not in issues,
            "collapsed_summary_cannot_patch_card": "collapsed_summary_materialized" not in issues
            and "collapsed_summary_mutated_card" not in issues,
            "non_behavior_profile_cannot_materialize_card": "non_behavior_profile_not_rejected" not in issues,
            "full_structured_replacement_final_state": "full_structured_replacement_not_materialized" not in issues
            and "replacement_rule_missing_from_canonical_card" not in issues,
            "session_start_delivery_uses_canonical_card": not any(issue.startswith("session_start:") for issue in issues),
            "compression_delivery_uses_same_card": not any(issue.startswith("compression:") for issue in issues),
            "source_profile_not_prompt_authority": "blocked_source_material_rendered_in_prompt" not in issues,
            "large_card_warning_not_prompt_spam": "large_card_warning_missing" not in issues
            and "large_card_warning_spammed_into_prompt" not in issues,
        },
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack behavior-card destructive invariants.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
