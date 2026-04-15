#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import types
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from brainstack.executive_retrieval import (  # noqa: E402
        _default_route_resolver,
        _llm_route_resolver,
        _should_attempt_route_hint,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by script sanity path
    if exc.name != "agent.memory_provider":
        raise
    sys.modules.setdefault("agent", types.ModuleType("agent"))
    fake_memory_provider = types.ModuleType("agent.memory_provider")
    fake_memory_provider.MemoryProvider = object
    sys.modules["agent.memory_provider"] = fake_memory_provider
    from brainstack.executive_retrieval import (  # noqa: E402
        _default_route_resolver,
        _llm_route_resolver,
        _should_attempt_route_hint,
    )


DEFAULT_DATASET = Path("/home/lauratom/LongMemEval/data/longmemeval_s_cleaned.json")
DEFAULT_REPORT_PATH = Path("/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase20/brainstack-route-hint-20.8-audit.json")
FIXED_CANARY_QUESTION_IDS = [
    "c8c3f81d",
    "5d3d2817",
    "e9327a54",
    "gpt4_7f6b06db",
    "6c49646a",
]
EXTRA_ROUTE_AUDIT_QUESTION_IDS = [
    "f523d9fe",
]


def _load_entries_from_report(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "question_id": str(row.get("question_id") or ""),
            "question": str(row.get("question") or ""),
            "question_type": str(row.get("question_type") or ""),
        }
        for row in list(payload.get("results") or [])
        if str(row.get("question_id") or "").strip() and str(row.get("question") or "").strip()
    ]


def _load_entries_from_dataset(path: Path, *, sample_size: int, seed: int, question_ids: List[str]) -> List[Dict[str, Any]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if question_ids:
        selected = [entry for entry in entries if str(entry.get("question_id") or "") in set(question_ids)]
    else:
        selected = random.Random(seed).sample(entries, sample_size)
    return [
        {
            "question_id": str(entry.get("question_id") or ""),
            "question": str(entry.get("question") or ""),
            "question_type": str(entry.get("question_type") or ""),
        }
        for entry in selected
    ]


def _load_all_entries_from_dataset(path: Path) -> List[Dict[str, Any]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "question_id": str(entry.get("question_id") or ""),
            "question": str(entry.get("question") or ""),
            "question_type": str(entry.get("question_type") or ""),
        }
        for entry in entries
    ]


def _write_report(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _select_entries(
    entries: List[Dict[str, Any]],
    *,
    sample_size: int,
    seed: int,
    question_ids: List[str],
    canary: bool,
    include_extra_route_audit_cases: bool,
) -> List[Dict[str, Any]]:
    selected_ids = list(question_ids or [])
    if canary:
        selected_ids = list(FIXED_CANARY_QUESTION_IDS)
    if include_extra_route_audit_cases:
        for qid in EXTRA_ROUTE_AUDIT_QUESTION_IDS:
            if qid not in selected_ids:
                selected_ids.append(qid)
    if selected_ids:
        by_id = {str(entry.get("question_id") or ""): entry for entry in entries}
        return [by_id[qid] for qid in selected_ids if qid in by_id]
    return random.Random(seed).sample(entries, sample_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Brainstack route-hint behavior on a bounded question set.")
    parser.add_argument("--report-input", type=Path, default=None)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--sample-size", type=int, default=15)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--include-extra-route-audit-cases", action="store_true")
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument("--include-llm", action="store_true")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    if args.report_input is not None:
        entries = _load_entries_from_report(args.report_input)
    else:
        entries = _load_all_entries_from_dataset(args.dataset)

    entries = _select_entries(
        entries,
        sample_size=args.sample_size,
        seed=args.seed,
        question_ids=list(args.question_id or []),
        canary=bool(args.canary),
        include_extra_route_audit_cases=bool(args.include_extra_route_audit_cases),
    )

    if not entries:
        raise SystemExit("No questions selected for route-hint audit.")

    include_llm = bool(args.include_llm)
    if include_llm and not (os.getenv("COMET_API_KEY") or os.getenv("COMETAPI_API_KEY")):
        raise SystemExit("LLM route audit requested but no COMET_API_KEY / COMETAPI_API_KEY is set.")

    results: List[Dict[str, Any]] = []
    llm_valid = 0
    deterministic_non_fact = 0
    llm_non_fact = 0
    llm_reason_counts: Dict[str, int] = {}

    for entry in entries:
        question = str(entry["question"] or "")
        should_attempt = _should_attempt_route_hint(question)
        deterministic = _default_route_resolver(question)
        if str(deterministic.get("mode") or "") in {"temporal", "aggregate"}:
            deterministic_non_fact += 1
        row = {
            "question_id": entry["question_id"],
            "question_type": entry["question_type"],
            "question": question,
            "should_attempt_route_hint": should_attempt,
            "deterministic": deterministic,
        }
        if include_llm:
            llm_payload = _llm_route_resolver(question)
            llm_mode = str(llm_payload.get("mode") or "")
            llm_valid += 1 if llm_mode in {"fact", "temporal", "aggregate"} else 0
            llm_non_fact += 1 if llm_mode in {"temporal", "aggregate"} else 0
            reason = str(llm_payload.get("reason") or "").strip() or "<empty>"
            llm_reason_counts[reason] = llm_reason_counts.get(reason, 0) + 1
            row["llm"] = llm_payload
        results.append(row)

    summary: Dict[str, Any] = {
        "sample_size": len(results),
        "report_input": str(args.report_input) if args.report_input is not None else "",
        "deterministic_non_fact": deterministic_non_fact,
        "deterministic_fact": len(results) - deterministic_non_fact,
        "selection_mode": "canary" if args.canary else ("question_ids" if args.question_id else "sample"),
        "selected_question_ids": [str(row.get("question_id") or "") for row in results],
        "extra_route_audit_question_ids": list(EXTRA_ROUTE_AUDIT_QUESTION_IDS) if args.include_extra_route_audit_cases else [],
    }
    if include_llm:
        summary["llm_valid_mode_count"] = llm_valid
        summary["llm_non_fact"] = llm_non_fact
        summary["llm_invalid_or_empty"] = len(results) - llm_valid
        summary["llm_unique_reasons"] = [
            {"count": count, "reason": reason}
            for reason, count in sorted(llm_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    payload = {"summary": summary, "results": results}
    _write_report(args.report_path, payload)
    print(json.dumps({"summary": summary, "report_path": str(args.report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
