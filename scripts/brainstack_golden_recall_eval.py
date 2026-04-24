#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from scripts._brainstack_host_shim import install_host_shim_if_needed  # noqa: E402

install_host_shim_if_needed()

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect  # noqa: E402


PRINCIPAL_SCOPE = "principal:golden-recall"
FIXTURE_SOURCE = "golden_fixture"


@dataclass(frozen=True)
class GoldenScenario:
    scenario_id: str
    question: str
    expected_shelf: str | None
    fixture: str
    expected_stable_key: str = ""
    expected_source: str = FIXTURE_SOURCE
    expected_excerpt: str = ""
    expected_citation_id: str = ""
    max_packet_chars: int = 0
    hard_gate: bool = True
    owner_phase: str = ""
    gap_reason: str = ""
    assertion: str = "selected_evidence"


def _seed_store(store: BrainstackStore, *, fixture: str = "all") -> None:
    include_all = fixture == "all"
    include = {fixture, "all"} if not include_all else {"all"}
    if include_all or "profile" in include:
        _seed_profile(store)
    if include_all or "task" in include:
        _seed_task(store)
    if include_all or "operating" in include:
        _seed_operating(store)
    if include_all or "corpus" in include:
        _seed_corpus(store)
    if include_all or "graph" in include:
        _seed_graph(store)
    if include_all or "continuity" in include:
        _seed_continuity(store)


def _seed_profile(store: BrainstackStore) -> None:
    store.upsert_profile_item(
        stable_key="identity:name",
        category="identity",
        content="LauraTom uses Brainstack as the memory kernel.",
        source=FIXTURE_SOURCE,
        confidence=0.99,
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE,
            "provenance_class": "typed_fixture",
            "authority_class": "profile",
        },
    )
    store.upsert_profile_item(
        stable_key="preference:german-proof",
        category="preference",
        content="Der Nutzer bevorzugt deterministische Speicherbeweise.",
        source=FIXTURE_SOURCE,
        confidence=0.97,
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE,
            "provenance_class": "typed_fixture",
            "authority_class": "profile",
        },
    )
    store.upsert_profile_item(
        stable_key="identity:chinese-memory-kernel",
        category="identity",
        content="用户把 Brainstack 称为 记忆内核。",
        source=FIXTURE_SOURCE,
        confidence=0.97,
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE,
            "provenance_class": "typed_fixture",
            "authority_class": "profile",
        },
    )


def _seed_task(store: BrainstackStore) -> None:
    store.upsert_task_item(
        stable_key="task:phase66:golden-proof",
        principal_scope_key=PRINCIPAL_SCOPE,
        item_type="task",
        title="Run Phase 66 golden recall proof",
        due_date="2026-04-24",
        date_scope="day",
        optional=False,
        status="open",
        owner="brainstack.task_memory",
        source=FIXTURE_SOURCE,
        source_session_id="seed-session",
        source_turn_number=1,
        metadata={
            "provenance_class": "typed_fixture",
            "authority_class": "task",
        },
    )


def _seed_operating(store: BrainstackStore) -> None:
    store.upsert_operating_record(
        stable_key="operating:phase66:active-work",
        principal_scope_key=PRINCIPAL_SCOPE,
        record_type="recent_work_summary",
        content="Active Brainstack work is Phase 66 golden recall eval harness.",
        owner="brainstack.operating_truth",
        source=FIXTURE_SOURCE,
        source_session_id="seed-session",
        source_turn_number=2,
        metadata={
            "provenance_class": "typed_fixture",
            "authority_class": "operating",
        },
    )


def _seed_corpus(store: BrainstackStore) -> None:
    metadata = {
        "principal_scope_key": PRINCIPAL_SCOPE,
        "provenance_class": "typed_fixture",
        "authority_class": "corpus",
    }
    store.ingest_corpus_source(
        {
            "source_adapter": "golden_fixture",
            "source_id": "phase66-golden-recall",
            "stable_key": "doc:phase66:golden-recall",
            "title": "Phase 66 Golden Recall Notes",
            "doc_kind": "project_note",
            "source_uri": FIXTURE_SOURCE,
            "sections": [
                {
                    "heading": "Golden recall target",
                    "content": "The golden recall harness must assert evidence ids and shelves, not answer text only.",
                }
            ],
            "metadata": metadata,
        }
    )
    store.ingest_corpus_source(
        {
            "source_adapter": "golden_fixture",
            "source_id": "phase76-hungarian",
            "stable_key": "doc:phase76:hungarian",
            "title": "Phase 76 Hungarian Corpus Note",
            "doc_kind": "project_note",
            "source_uri": FIXTURE_SOURCE,
            "sections": [
                {
                    "heading": "Kanonikus allapot",
                    "content": "A Brainstack korpusz kanonikus allapotot es idezetazonositot tarol nagy tudaskeszletekhez.",
                }
            ],
            "metadata": metadata,
        }
    )
    store.ingest_corpus_source(
        {
            "source_adapter": "golden_fixture",
            "source_id": "phase77-german",
            "stable_key": "doc:phase77:german",
            "title": "Phase 77 German Corpus Note",
            "doc_kind": "project_note",
            "source_uri": FIXTURE_SOURCE,
            "sections": [
                {
                    "heading": "Deutscher Nachweis",
                    "content": "Brainstack speichert mehrsprachige Evidenz mit Zitaten und begrenztem Abruf.",
                }
            ],
            "metadata": metadata,
        }
    )
    store.ingest_corpus_source(
        {
            "source_adapter": "golden_fixture",
            "source_id": "phase76-large-doc",
            "stable_key": "doc:phase76:large-doc",
            "title": "Phase 76 Large Corpus Note",
            "doc_kind": "project_note",
            "source_uri": FIXTURE_SOURCE,
            "sections": [
                {
                    "heading": "Noise",
                    "content": "Noise paragraph. " * 240,
                },
                {
                    "heading": "Target",
                    "content": "Needle76 answer is stored in one bounded cited section.",
                },
            ],
            "metadata": metadata,
        }
    )


def _seed_graph(store: BrainstackStore) -> None:
    metadata = {
        "principal_scope_key": PRINCIPAL_SCOPE,
        "provenance_class": "typed_fixture",
        "authority_class": "graph",
    }
    store.upsert_graph_state(
        subject_name="Phase 66 Harness",
        attribute="status",
        value_text="implemented as deterministic eval",
        source=FIXTURE_SOURCE,
        metadata={
            **metadata,
            "semantic_terms": ["relationship memory substrate"],
        },
    )
    store.upsert_graph_relation(
        subject_name="Meridian",
        predicate="project_code_for",
        object_name="Aurora",
        source=FIXTURE_SOURCE,
        metadata=metadata,
    )
    store.upsert_graph_relation(
        subject_name="项目龙",
        predicate="依赖",
        object_name="知识库",
        source=FIXTURE_SOURCE,
        metadata=metadata,
    )
    store.upsert_graph_state(
        subject_name="Aurora",
        attribute="deployment",
        value_text="green",
        source=FIXTURE_SOURCE,
        metadata={
            **metadata,
            "context_id": "readiness",
        },
    )


def _seed_continuity(store: BrainstackStore) -> None:
    store.add_continuity_event(
        session_id="seed-session",
        turn_number=3,
        kind="summary",
        content="Cross-session continuity says the old session chose query inspect proof first.",
        source=FIXTURE_SOURCE,
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE,
            "provenance_class": "typed_fixture",
            "authority_class": "continuity",
        },
    )


SCENARIOS: tuple[GoldenScenario, ...] = (
    GoldenScenario(
        scenario_id="profile.exact_identity",
        question="Who uses Brainstack as the memory kernel?",
        expected_shelf="profile",
        fixture="profile",
        expected_stable_key="identity:name",
        expected_excerpt="memory kernel",
    ),
    GoldenScenario(
        scenario_id="profile.german_preference",
        question="deterministische Speicherbeweise",
        expected_shelf="profile",
        fixture="profile",
        expected_stable_key="preference:german-proof",
        expected_excerpt="Speicherbeweise",
        owner_phase="77",
    ),
    GoldenScenario(
        scenario_id="profile.chinese_identity",
        question="记忆内核",
        expected_shelf="profile",
        fixture="profile",
        expected_stable_key="identity:chinese-memory-kernel",
        expected_excerpt="记忆内核",
        owner_phase="77",
    ),
    GoldenScenario(
        scenario_id="task.exact_open_task",
        question="Run Phase 66 golden recall proof",
        expected_shelf="task",
        fixture="task",
        expected_stable_key="task:phase66:golden-proof",
        expected_excerpt="golden recall proof",
    ),
    GoldenScenario(
        scenario_id="operating.exact_active_work",
        question="What is the active Brainstack work Phase 66?",
        expected_shelf="operating",
        fixture="operating",
        expected_stable_key="operating:phase66:active-work",
        expected_excerpt="golden recall eval harness",
    ),
    GoldenScenario(
        scenario_id="corpus.exact_document_section",
        question="evidence ids and shelves",
        expected_shelf="corpus",
        fixture="corpus",
        expected_excerpt="evidence ids and shelves",
        expected_citation_id="doc:phase66:golden-recall#s0",
    ),
    GoldenScenario(
        scenario_id="corpus.multilingual_hungarian",
        question="kanonikus allapot idezetazonosito",
        expected_shelf="corpus",
        fixture="corpus",
        expected_excerpt="kanonikus allapot",
        expected_citation_id="doc:phase76:hungarian#s0",
        owner_phase="76",
    ),
    GoldenScenario(
        scenario_id="corpus.german_document",
        question="mehrsprachige Evidenz Zitaten",
        expected_shelf="corpus",
        fixture="corpus",
        expected_excerpt="mehrsprachige Evidenz",
        expected_citation_id="doc:phase77:german#s0",
        owner_phase="77",
    ),
    GoldenScenario(
        scenario_id="corpus.large_doc_token_budget",
        question="Needle76 answer",
        expected_shelf="corpus",
        fixture="corpus",
        expected_excerpt="Needle76 answer",
        expected_citation_id="doc:phase76:large-doc#s1",
        max_packet_chars=3000,
        owner_phase="76",
    ),
    GoldenScenario(
        scenario_id="graph.exact_state",
        question="Phase 66 Harness status deterministic eval",
        expected_shelf="graph",
        fixture="graph",
        expected_excerpt="deterministic eval",
        assertion="packet_preview",
    ),
    GoldenScenario(
        scenario_id="graph.semantic_seed_state",
        question="relationship memory substrate",
        expected_shelf="graph",
        fixture="graph",
        expected_excerpt="deterministic eval",
        assertion="packet_preview",
    ),
    GoldenScenario(
        scenario_id="graph.associative_alias_state",
        question="Meridian readiness",
        expected_shelf="graph",
        fixture="graph",
        expected_excerpt="green",
        assertion="packet_preview",
        owner_phase="75",
    ),
    GoldenScenario(
        scenario_id="graph.chinese_relation",
        question="项目龙 知识库",
        expected_shelf="graph",
        fixture="graph",
        expected_excerpt="知识库",
        assertion="packet_preview",
        owner_phase="77",
    ),
    GoldenScenario(
        scenario_id="continuity.cross_session_match",
        question="old session query inspect proof",
        expected_shelf="continuity_match",
        fixture="continuity",
        expected_excerpt="old session chose query inspect proof",
    ),
    GoldenScenario(
        scenario_id="profile.paraphrase_semantic_gap",
        question="Which persistent recall substrate is LauraTom relying on?",
        expected_shelf="profile",
        fixture="profile",
        expected_stable_key="identity:name",
        expected_excerpt="Brainstack",
        hard_gate=False,
        owner_phase="67",
        gap_reason="Paraphrase recall belongs to the typed semantic evidence index, not to Phase 66.",
    ),
    GoldenScenario(
        scenario_id="negative.unsupported_query_has_no_memory_truth",
        question="unsupported zeta omega no durable memory",
        expected_shelf=None,
        fixture="all",
        hard_gate=False,
        owner_phase="67/75",
        gap_reason="Current packet policy may include generally authoritative evidence for unsupported queries; later ranking/suppression phases own this.",
    ),
)


def _selected_items(report: dict[str, Any], shelf: str) -> list[dict[str, Any]]:
    selected = report.get("selected_evidence") if isinstance(report.get("selected_evidence"), dict) else {}
    rows = selected.get(shelf) if isinstance(selected, dict) else []
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def _all_selected_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    selected = report.get("selected_evidence") if isinstance(report.get("selected_evidence"), dict) else {}
    rows: list[dict[str, Any]] = []
    if not isinstance(selected, dict):
        return rows
    for shelf_rows in selected.values():
        rows.extend(dict(row) for row in shelf_rows or [] if isinstance(row, dict))
    return rows


def _matches_expected_item(scenario: GoldenScenario, report: dict[str, Any]) -> tuple[bool, str, list[dict[str, Any]]]:
    if scenario.expected_shelf is None:
        rows = _all_selected_items(report)
        if rows:
            return False, "unsupported query selected memory evidence", rows
        return True, "no memory evidence selected", []

    rows = _selected_items(report, scenario.expected_shelf)
    if not rows:
        return False, f"no selected evidence for shelf {scenario.expected_shelf}", []

    preview = str(report.get("final_packet", {}).get("preview") or "")
    for row in rows:
        stable_key_ok = not scenario.expected_stable_key or row.get("stable_key") == scenario.expected_stable_key
        source_ok = not scenario.expected_source or row.get("source") == scenario.expected_source
        citation_ok = not scenario.expected_citation_id or row.get("citation_id") == scenario.expected_citation_id
        excerpt = str(row.get("excerpt") or "")
        excerpt_ok = not scenario.expected_excerpt or scenario.expected_excerpt in excerpt or scenario.expected_excerpt in preview
        if stable_key_ok and source_ok and citation_ok and excerpt_ok:
            return True, "selected expected evidence", rows
    return False, "selected shelf exists but expected attribution did not match", rows


def _status_for(scenario: GoldenScenario, passed: bool) -> str:
    if scenario.hard_gate:
        return "pass" if passed else "fail"
    return "baseline_pass" if passed else "expected_red"


def _scenario_db_path(base_dir: Path, scenario_id: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in scenario_id)
    return base_dir / f"{safe_name}.sqlite3"


def _run_one_scenario(scenario: GoldenScenario, db_path: Path) -> dict[str, Any]:
    store = _open_store(db_path)
    try:
        _seed_store(store, fixture=scenario.fixture)
        store.close()

        # Reopen the same DB to prove durable recall, not in-memory state.
        store = _open_store(db_path)
        report = build_query_inspect(
            store,
            query=scenario.question,
            session_id="recall-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=5,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=2,
            transcript_char_budget=640,
            evidence_item_budget=10,
            graph_limit=6,
            corpus_limit=6,
            corpus_char_budget=900,
            operating_match_limit=4,
        )
    finally:
        store.close()

    passed, reason, rows = _matches_expected_item(scenario, report)
    if passed and scenario.max_packet_chars:
        char_count = int(report.get("final_packet", {}).get("char_count") or 0)
        if char_count > scenario.max_packet_chars:
            passed = False
            reason = f"packet exceeded max char budget {scenario.max_packet_chars}"
    return {
        "id": scenario.scenario_id,
        "question": scenario.question,
        "fixture": scenario.fixture,
        "hard_gate": scenario.hard_gate,
        "status": _status_for(scenario, passed),
        "passed": passed,
        "reason": reason,
        "expected_shelf": scenario.expected_shelf,
        "expected_stable_key": scenario.expected_stable_key,
        "owner_phase": scenario.owner_phase,
        "gap_reason": scenario.gap_reason,
        "selected_count": len(_all_selected_items(report)),
        "matched_rows": rows[:4],
        "packet": {
            "sections": list(report.get("final_packet", {}).get("sections") or []),
            "char_count": int(report.get("final_packet", {}).get("char_count") or 0),
        },
        "routing": dict(report.get("routing") or {}),
    }


def _run_scenarios(base_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        results.append(_run_one_scenario(scenario, _scenario_db_path(base_dir, scenario.scenario_id)))
    return results


def _open_store(db_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(db_path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _doctor_for_full_fixture(db_path: Path) -> dict[str, Any]:
    store = _open_store(db_path)
    try:
        _seed_store(store, fixture="all")
        store.close()
        store = _open_store(db_path)
        return build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )
    finally:
        store.close()


def run_golden_recall_eval(db_path: Path | None = None) -> dict[str, Any]:
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if db_path is None:
        temp_dir = tempfile.TemporaryDirectory()
        base_dir = Path(temp_dir.name)
    else:
        base_dir = Path(db_path)
        if base_dir.suffix:
            base_dir = base_dir.with_suffix("")
        base_dir.mkdir(parents=True, exist_ok=True)

    doctor = _doctor_for_full_fixture(base_dir / "full-fixture-doctor.sqlite3")
    scenarios = _run_scenarios(base_dir)
    if temp_dir is not None:
        temp_dir.cleanup()

    hard_failures = [row for row in scenarios if row["hard_gate"] and not row["passed"]]
    hard_passes = [row for row in scenarios if row["hard_gate"] and row["passed"]]
    baselines = [row for row in scenarios if not row["hard_gate"]]
    return {
        "schema": "brainstack.golden_recall_eval.v1",
        "verdict": "fail" if hard_failures else "pass",
        "db_path": str(base_dir),
        "doctor": {
            "verdict": doctor.get("verdict"),
            "capabilities": doctor.get("capabilities"),
            "row_counts": doctor.get("row_counts"),
        },
        "hard_gate": {
            "passed": len(hard_passes),
            "failed": len(hard_failures),
            "failed_ids": [row["id"] for row in hard_failures],
        },
        "baseline": {
            "count": len(baselines),
            "expected_red_ids": [row["id"] for row in baselines if row["status"] == "expected_red"],
            "baseline_pass_ids": [row["id"] for row in baselines if row["status"] == "baseline_pass"],
        },
        "scenarios": scenarios,
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(f"schema={report['schema']}")
    print(f"verdict={report['verdict']}")
    print(
        "hard_gate="
        f"{report['hard_gate']['passed']} passed, "
        f"{report['hard_gate']['failed']} failed"
    )
    print(
        "baseline="
        f"{report['baseline']['count']} scenarios, "
        f"expected_red={','.join(report['baseline']['expected_red_ids']) or '-'}"
    )
    for scenario in report["scenarios"]:
        print(
            f"{scenario['status']}: {scenario['id']} "
            f"shelf={scenario['expected_shelf'] or '-'} "
            f"selected={scenario['selected_count']} "
            f"reason={scenario['reason']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Brainstack golden recall evals.")
    parser.add_argument("--db-path", type=Path, default=None, help="Optional persistent eval DB path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args(argv)

    report = run_golden_recall_eval(db_path=args.db_path)
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        _print_summary(report)
    return 1 if report["verdict"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
