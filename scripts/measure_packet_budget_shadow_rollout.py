#!/usr/bin/env python3
"""Measure packet-budget shadow telemetry on public-safe Brainstack packet paths."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402


def _packet_defaults() -> dict[str, object]:
    return {
        "profile_match_limit": 5,
        "continuity_recent_limit": 8,
        "continuity_match_limit": 8,
        "transcript_match_limit": 8,
        "transcript_char_budget": 2200,
        "evidence_item_budget": 12,
        "graph_limit": 4,
        "corpus_limit": 2,
        "corpus_char_budget": 420,
        "operating_match_limit": 4,
        "record_retrievals": False,
    }


def _seed_continuity_noise(
    store: BrainstackStore,
    *,
    scope: str,
    session: str,
    prefix: str,
    count: int,
    start: int = 1,
) -> None:
    for index in range(count):
        store.add_continuity_event(
            session_id=session,
            turn_number=start + index,
            kind="user",
            content=(
                f"{prefix}_{index} support-only repeated context. "
                "This sentence is intentionally public-safe filler for packet budget measurement."
            ),
            source="phase201_public_measurement",
            metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
        )


def _seed_profile_identity(store: BrainstackStore, *, scope: str, session: str) -> None:
    store.upsert_profile_item(
        stable_key="identity:preferred_name",
        category="identity",
        content="The user's preferred name is Alex.",
        source="phase201_public_measurement",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": True,
        },
    )
    _seed_continuity_noise(store, scope=scope, session=session, prefix="IDENTITY_NOISE", count=10)


def _seed_task_operating(store: BrainstackStore, *, scope: str, session: str) -> None:
    store.upsert_task_item(
        stable_key="task:quarterly-review",
        principal_scope_key=scope,
        item_type="current_assignment",
        title="Prepare the quarterly memory-kernel review.",
        due_date="2026-05-15",
        date_scope="explicit",
        optional=False,
        status="open",
        owner="Alex",
        source="phase201_public_measurement",
        source_session_id=session,
        source_turn_number=1,
        metadata={"truth_eligible": True},
    )
    store.upsert_operating_record(
        stable_key="operating:style-no-emoji",
        principal_scope_key=scope,
        record_type="style_preference",
        content="Use plain Hungarian style without emoji.",
        owner="Alex",
        source="phase201_public_measurement",
        source_session_id=session,
        source_turn_number=2,
        metadata={"truth_eligible": True},
    )
    _seed_continuity_noise(store, scope=scope, session=session, prefix="TASK_NOISE", count=12, start=3)


def _seed_project_graph(store: BrainstackStore, *, scope: str, session: str) -> None:
    store.upsert_graph_state(
        subject_name="Project Orion",
        attribute="creator",
        value_text="Alex",
        source="phase201_public_measurement",
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    store.upsert_graph_relation(
        subject_name="LibGraph",
        predicate="inspired_component",
        object_name="Project Orion graph layer",
        source="phase201_public_measurement",
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    _seed_continuity_noise(store, scope=scope, session=session, prefix="GRAPH_NOISE", count=14)


def _seed_reference_url(store: BrainstackStore, *, scope: str, session: str) -> None:
    store.upsert_profile_item(
        stable_key="reference:repository_url:example-lib",
        category="reference",
        content="example-lib repository URL: https://example.com/example-lib",
        source="phase201_public_measurement",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "reference.repository_url",
            "label": "example-lib",
            "truth_eligible": True,
            "fetch_on_write": False,
        },
    )
    _seed_continuity_noise(store, scope=scope, session=session, prefix="URL_NOISE", count=9)


def _scenario_specs() -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": "profile_identity_with_support_noise",
            "query": "What is my preferred name?",
            "seed": _seed_profile_identity,
        },
        {
            "scenario_id": "task_operating_with_support_noise",
            "query": "What is my current assignment and style preference?",
            "seed": _seed_task_operating,
        },
        {
            "scenario_id": "project_graph_with_support_noise",
            "query": "Who created Project Orion and what inspired its graph layer?",
            "seed": _seed_project_graph,
        },
        {
            "scenario_id": "reference_url_with_support_noise",
            "query": "What is the saved example-lib repository URL?",
            "seed": _seed_reference_url,
        },
    ]


def _packet_budget_summary(packet_budget: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mode": packet_budget.get("mode"),
        "status": packet_budget.get("status"),
        "applied_to_output": bool(packet_budget.get("applied_to_output")),
        "estimated_tokens_before": int(packet_budget.get("estimated_tokens_before") or 0),
        "selected_candidate_tokens": int(packet_budget.get("selected_candidate_tokens") or 0),
        "dropped_candidate_tokens": int(packet_budget.get("dropped_candidate_tokens") or 0),
        "fail_closed": bool(packet_budget.get("fail_closed")),
        "answer_evidence_preserved": bool(packet_budget.get("answer_evidence_preserved", True)),
        "receipt_coverage_preserved": bool(packet_budget.get("receipt_coverage_preserved", True)),
        "authority_fields_preserved": bool(packet_budget.get("authority_fields_preserved", True)),
        "scope_fields_preserved": bool(packet_budget.get("scope_fields_preserved", True)),
        "budget_decision_count": len(packet_budget.get("budget_decisions") or []),
    }


def _protected_drop_attempts(packet_budget: Mapping[str, Any]) -> int:
    if not bool(packet_budget.get("answer_evidence_preserved", True)):
        return 1
    if not bool(packet_budget.get("receipt_coverage_preserved", True)):
        return 1
    if not bool(packet_budget.get("authority_fields_preserved", True)):
        return 1
    if not bool(packet_budget.get("scope_fields_preserved", True)):
        return 1
    return 0


def measure_runtime_shadow(*, max_candidate_tokens: int) -> dict[str, Any]:
    scenario_reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-phase201-") as tmp:
        root = Path(tmp)
        for offset, spec in enumerate(_scenario_specs(), start=1):
            store = BrainstackStore(str(root / f"{spec['scenario_id']}.sqlite3"))
            store.open()
            scope = f"principal:phase201:{offset}"
            session = f"session:phase201:{offset}"
            try:
                spec["seed"](store, scope=scope, session=session)
                base = build_working_memory_packet(
                    store,
                    query=spec["query"],
                    session_id=session,
                    principal_scope_key=scope,
                    **_packet_defaults(),
                )
                shadow = build_working_memory_packet(
                    store,
                    query=spec["query"],
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="shadow",
                    packet_budget_max_candidate_tokens=max_candidate_tokens,
                    **_packet_defaults(),
                )
                packet_budget = shadow.get("packet_budget") or {}
                scenario_reports.append(
                    {
                        "scenario_id": spec["scenario_id"],
                        "output_changed_in_shadow": base.get("block") != shadow.get("block"),
                        "base_block_chars": len(str(base.get("block") or "")),
                        "shadow_block_chars": len(str(shadow.get("block") or "")),
                        "packet_budget": _packet_budget_summary(packet_budget),
                        "protected_truth_drop_attempts": _protected_drop_attempts(packet_budget),
                    }
                )
            finally:
                store.close()

    baseline = sum(item["packet_budget"]["estimated_tokens_before"] for item in scenario_reports)
    budgeted = sum(item["packet_budget"]["selected_candidate_tokens"] for item in scenario_reports)
    delta = baseline - budgeted
    protected_drops = sum(item["protected_truth_drop_attempts"] for item in scenario_reports)
    fail_closed = sum(1 for item in scenario_reports if item["packet_budget"]["fail_closed"])
    output_changed = any(item["output_changed_in_shadow"] for item in scenario_reports)
    return {
        "schema": "brainstack.phase201.packet_budget_shadow_rollout.v1",
        "runtime_equivalent": True,
        "scenario_count": len(scenario_reports),
        "baseline_candidate_tokens": baseline,
        "shadow_budget_candidate_tokens": budgeted,
        "estimated_delta_tokens": delta,
        "estimated_delta_percent": round((delta / baseline * 100.0), 2) if baseline else 0.0,
        "protected_truth_drop_attempts": protected_drops,
        "fail_closed_count": fail_closed,
        "output_changed_in_shadow": output_changed,
        "production_savings_claim": False,
        "max_candidate_tokens": max_candidate_tokens,
        "scenarios": scenario_reports,
    }


def _load_public_fixture_measurement(root: Path):
    script = root / "scripts" / "measure_public_memory_token_cost.py"
    spec = importlib.util.spec_from_file_location("measure_public_memory_token_cost", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot_load_public_fixture_measurement")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.measure_fixture_directory


def measure_public_fixtures(
    *,
    root: Path,
    fixture_dir: Path,
    max_candidate_tokens: int,
) -> dict[str, Any]:
    measure_fixture_directory = _load_public_fixture_measurement(root)
    return measure_fixture_directory(
        fixture_dir,
        budget_max_candidate_tokens=max_candidate_tokens,
    )


def build_report(
    *,
    root: Path,
    fixture_dir: Path,
    max_candidate_tokens: int,
    include_public_fixtures: bool,
) -> dict[str, Any]:
    runtime_shadow = measure_runtime_shadow(max_candidate_tokens=max_candidate_tokens)
    fail_closed_probe = measure_runtime_shadow(max_candidate_tokens=1)
    public_fixtures: dict[str, Any] | None = None
    if include_public_fixtures:
        public_fixtures = measure_public_fixtures(
            root=root,
            fixture_dir=fixture_dir,
            max_candidate_tokens=max_candidate_tokens,
        )
    public_aggregate = (public_fixtures or {}).get("aggregate") or {}
    public_budget = (public_fixtures or {}).get("budget_simulation") or {}
    required_metrics = {
        "scenario_count": runtime_shadow["scenario_count"] + int(public_budget.get("scenario_count") or 0),
        "baseline_candidate_tokens": runtime_shadow["baseline_candidate_tokens"]
        + int(public_aggregate.get("total_candidate_tokens") or 0),
        "shadow_budget_candidate_tokens": runtime_shadow["shadow_budget_candidate_tokens"]
        + int(public_aggregate.get("selected_candidate_tokens") or 0),
        "estimated_delta_tokens": runtime_shadow["estimated_delta_tokens"]
        + int(public_budget.get("estimated_candidate_token_delta") or 0),
        "estimated_delta_percent": 0.0,
        "protected_truth_drop_attempts": runtime_shadow["protected_truth_drop_attempts"],
        "fail_closed_count": runtime_shadow["fail_closed_count"]
        + int(public_budget.get("fail_closed_count") or 0),
        "output_changed_in_shadow": runtime_shadow["output_changed_in_shadow"],
        "production_savings_claim": False,
    }
    if required_metrics["baseline_candidate_tokens"]:
        required_metrics["estimated_delta_percent"] = round(
            required_metrics["estimated_delta_tokens"]
            / required_metrics["baseline_candidate_tokens"]
            * 100.0,
            2,
        )
    return {
        "schema": "brainstack.phase201.packet_budget_shadow_report.v1",
        "measurement_only": True,
        "production_optimization_enabled": False,
        "production_savings_claim": False,
        "activation_decision": {
            "status": "not_activated",
            "active_default_justified": False,
            "reason": "shadow telemetry is promising, but production rollout needs a separate activation phase with live-packet telemetry",
        },
        "required_metrics": required_metrics,
        "fail_closed_probe": {
            "max_candidate_tokens": 1,
            "fail_closed_count": fail_closed_probe["fail_closed_count"],
            "output_changed_in_shadow": fail_closed_probe["output_changed_in_shadow"],
            "production_savings_claim": False,
        },
        "shadow_output_changed": runtime_shadow["output_changed_in_shadow"],
        "runtime_shadow": runtime_shadow,
        "public_fixture_measurement": public_fixtures,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--budget-max-candidate-tokens",
        type=int,
        default=120,
        help="Candidate token cap used for shadow estimation.",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures/public_memory_kernel"),
        help="Public-safe memory fixture directory.",
    )
    parser.add_argument(
        "--skip-public-fixtures",
        action="store_true",
        help="Measure runtime-equivalent synthetic packets only.",
    )
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    report = build_report(
        root=ROOT,
        fixture_dir=(ROOT / args.fixtures).resolve()
        if not args.fixtures.is_absolute()
        else args.fixtures,
        max_candidate_tokens=args.budget_max_candidate_tokens,
        include_public_fixtures=not args.skip_public_fixtures,
    )
    if args.out:
        _write_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
