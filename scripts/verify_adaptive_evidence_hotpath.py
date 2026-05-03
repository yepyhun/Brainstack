#!/usr/bin/env python3
"""Verify the M007 S01 adaptive evidence hot-path baseline.

The verifier builds public-safe representative fixtures, exercises the real
Brainstack working-memory packet entrypoint, and emits only structural metrics.
It runs packet-budget in shadow mode for measurement and compares the rendered
packet block to an unbudgeted baseline to prove the measurement path is read-only
with respect to runtime output.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.adaptive_evidence_hotpath import (  # noqa: E402
    build_hotpath_report,
    summarize_hotpath_case,
    validate_hotpath_report,
)
from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.persistent_bloat import build_persistent_bloat_report  # noqa: E402


@dataclass(frozen=True)
class HotpathCaseSpec:
    case_id: str
    query_class: str
    query: str
    seeder: Callable[[BrainstackStore, str, str], None]
    route_mode: str = "fact"


def _packet_defaults() -> dict[str, object]:
    return {
        "profile_match_limit": 5,
        "continuity_recent_limit": 8,
        "continuity_match_limit": 8,
        "transcript_match_limit": 8,
        "transcript_char_budget": 2400,
        "evidence_item_budget": 12,
        "graph_limit": 4,
        "corpus_limit": 3,
        "corpus_char_budget": 520,
        "operating_match_limit": 4,
        "record_retrievals": False,
    }


def _route_resolver(mode: str) -> Callable[[str], dict[str, str]]:
    normalized = str(mode or "fact").strip() or "fact"

    def resolve(_query: str) -> dict[str, str]:
        return {
            "mode": normalized,
            "reason": f"m007_s01_public_fixture_{normalized}",
            "source": "m007_s01_fixture",
        }

    return resolve


def _snapshot_table_counts(store: BrainstackStore) -> dict[str, int]:
    rows = store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row["name"])
        try:
            count_row = store.conn.execute(f'SELECT COUNT(*) AS count FROM "{name}"').fetchone()
            counts[name] = int(count_row["count"] if count_row is not None else 0)
        except Exception:
            counts[name] = -1
    return counts


def _storage_mutation_count(before: Mapping[str, int], after: Mapping[str, int]) -> int:
    keys = set(before) | set(after)
    return sum(1 for key in keys if int(before.get(key, -999999)) != int(after.get(key, -999999)))


def _noise(store: BrainstackStore, *, scope: str, session: str, prefix: str, count: int, start: int = 1) -> None:
    for index in range(count):
        store.add_continuity_event(
            session_id=session,
            turn_number=start + index,
            kind="user",
            content=(
                f"{prefix}_{index} public fixture support-only continuity. "
                "This simulates ordinary chat pressure without private data."
            ),
            source="m007_s01_hotpath_fixture",
            metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
        )


def _seed_no_memory(_store: BrainstackStore, _scope: str, _session: str) -> None:
    return None


def _seed_profile_current_truth(store: BrainstackStore, scope: str, session: str) -> None:
    store.upsert_profile_item(
        stable_key="identity:preferred_name:m007_s01",
        category="identity",
        content="The user's preferred name is PublicSampleUser.",
        source="m007_s01_hotpath_fixture",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": True,
        },
    )
    _noise(store, scope=scope, session=session, prefix="PROFILE_PRESSURE", count=4)


def _seed_temporal_graph(store: BrainstackStore, scope: str, session: str) -> None:
    store.upsert_graph_state(
        subject_name="Public Project M007",
        attribute="status",
        value_text="baseline measurement ready",
        source="m007_s01_hotpath_fixture",
        metadata={"principal_scope_key": scope, "truth_eligible": True, "temporal_status": "current"},
    )
    store.upsert_graph_relation(
        subject_name="Public Project M007",
        predicate="depends_on",
        object_name="Packet budget proof",
        source="m007_s01_hotpath_fixture",
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    _noise(store, scope=scope, session=session, prefix="TEMPORAL_PRESSURE", count=5)


def _seed_corpus(store: BrainstackStore, scope: str, session: str) -> None:
    document_id = store.upsert_corpus_document(
        stable_key="doc:m007:s01:public-corpus",
        title="M007 public corpus fixture",
        doc_kind="public_fixture",
        source="m007_s01_hotpath_fixture",
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    store.replace_corpus_sections(
        document_id=document_id,
        title="M007 public corpus fixture",
        sections=[
            {
                "heading": "Adaptive evidence",
                "content": "Adaptive evidence compares candidate shelves with public-safe structural metrics.",
                "token_estimate": 18,
                "metadata": {"principal_scope_key": scope},
            },
            {
                "heading": "Packet budget",
                "content": "Packet budget telemetry must stay inspectable and preserve protected truth.",
                "token_estimate": 18,
                "metadata": {"principal_scope_key": scope},
            },
        ],
    )
    _noise(store, scope=scope, session=session, prefix="CORPUS_PRESSURE", count=4)


def _seed_continuity(store: BrainstackStore, scope: str, session: str) -> None:
    for index, content in enumerate(
        [
            "We discussed a public baseline for hot-path memory measurement.",
            "The next public step was proving read-only packet diagnostics.",
            "The public continuity fixture should remain support-only unless selected by retrieval.",
        ],
        start=1,
    ):
        store.add_continuity_event(
            session_id=session,
            turn_number=index,
            kind="user",
            content=content,
            source="m007_s01_hotpath_fixture",
            metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
        )


def _seed_noisy_high_fanout(store: BrainstackStore, scope: str, session: str) -> None:
    _seed_profile_current_truth(store, scope, session)
    _seed_temporal_graph(store, scope, session)
    _seed_corpus(store, scope, session)
    store.upsert_task_item(
        stable_key="task:m007:s01:public-review",
        principal_scope_key=scope,
        item_type="current_assignment",
        title="Review public adaptive evidence baseline.",
        due_date="2026-05-15",
        date_scope="explicit",
        optional=False,
        status="open",
        owner="PublicSampleUser",
        source="m007_s01_hotpath_fixture",
        source_session_id=session,
        source_turn_number=1,
        metadata={"truth_eligible": True},
    )
    store.upsert_operating_record(
        stable_key="operating:m007:s01:public-policy",
        principal_scope_key=scope,
        record_type="canonical_policy",
        content="Use public-safe structural diagnostics for adaptive evidence baseline work.",
        owner="PublicSampleUser",
        source="m007_s01_hotpath_fixture",
        source_session_id=session,
        source_turn_number=2,
        metadata={"truth_eligible": True},
    )
    _noise(store, scope=scope, session=session, prefix="HIGH_FANOUT_PRESSURE", count=24, start=20)


CASES: tuple[HotpathCaseSpec, ...] = (
    HotpathCaseSpec(
        case_id="case_no_memory_minimal",
        query_class="no_memory_minimal",
        query="Public no-memory baseline probe.",
        seeder=_seed_no_memory,
    ),
    HotpathCaseSpec(
        case_id="case_profile_current_truth",
        query_class="profile_current_truth",
        query="What is my preferred name?",
        seeder=_seed_profile_current_truth,
    ),
    HotpathCaseSpec(
        case_id="case_temporal_graph",
        query_class="temporal_graph",
        query="What changed in Public Project M007 over time?",
        seeder=_seed_temporal_graph,
        route_mode="temporal",
    ),
    HotpathCaseSpec(
        case_id="case_corpus",
        query_class="corpus",
        query="What does the adaptive evidence corpus fixture say about packet budget?",
        seeder=_seed_corpus,
    ),
    HotpathCaseSpec(
        case_id="case_continuity",
        query_class="continuity",
        query="What did we discuss about the public hot-path baseline?",
        seeder=_seed_continuity,
    ),
    HotpathCaseSpec(
        case_id="case_noisy_high_fanout",
        query_class="noisy_high_fanout",
        query="Summarize all public M007 S01 memory signals and pressure.",
        seeder=_seed_noisy_high_fanout,
        route_mode="aggregate",
    ),
)


def _elapsed_ms(start: float) -> float:
    return max(0.0, (time.perf_counter() - start) * 1000.0)


def _build_packet(
    store: BrainstackStore,
    *,
    spec: HotpathCaseSpec,
    scope: str,
    session: str,
    packet_budget_mode: str,
) -> dict[str, Any]:
    return build_working_memory_packet(
        store,
        query=spec.query,
        session_id=session,
        principal_scope_key=scope,
        route_resolver=_route_resolver(spec.route_mode),
        packet_budget_mode=packet_budget_mode,
        packet_budget_max_candidate_tokens=120,
        **_packet_defaults(),
    )


def run_hotpath_baseline(*, out_path: Path | None = None) -> dict[str, Any]:
    case_reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-m007-s01-hotpath-") as tmp:
        root = Path(tmp)
        for index, spec in enumerate(CASES):
            store = BrainstackStore(str(root / f"{spec.case_id}.sqlite3"))
            store.open()
            scope = f"principal:m007:s01:{index}:{spec.query_class}"
            session = f"session:m007:s01:{index}:{spec.query_class}"
            try:
                spec.seeder(store, scope, session)
                before_counts = _snapshot_table_counts(store)
                unbudgeted = _build_packet(
                    store,
                    spec=spec,
                    scope=scope,
                    session=session,
                    packet_budget_mode="off",
                )
                start = time.perf_counter()
                measured = _build_packet(
                    store,
                    spec=spec,
                    scope=scope,
                    session=session,
                    packet_budget_mode="shadow",
                )
                latency_ms = _elapsed_ms(start)
                bloat_report = build_persistent_bloat_report(store, principal_scope_key=scope)
                after_counts = _snapshot_table_counts(store)
                mutation_count = _storage_mutation_count(before_counts, after_counts)
                case_reports.append(
                    summarize_hotpath_case(
                        case_id=spec.case_id,
                        query_class=spec.query_class,
                        query_text=spec.query,
                        packet=measured,
                        latency_ms=latency_ms,
                        bloat_report=bloat_report,
                        behavior_changed_from_unbudgeted=unbudgeted.get("block") != measured.get("block"),
                        storage_mutation_count=mutation_count,
                    )
                )
            finally:
                store.close()
    report = build_hotpath_report(cases=case_reports)
    errors = validate_hotpath_report(report)
    if errors:
        report["public_safe"] = False
        report["validation_errors"] = errors
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify public-safe M007 S01 adaptive evidence hot-path baseline.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = run_hotpath_baseline(out_path=args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if validate_hotpath_report(report) == [] and report.get("public_safe") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
