#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


from scripts._brainstack_host_shim import install_host_shim_if_needed  # noqa: E402

install_host_shim_if_needed()

from brainstack.modality_contract import (  # noqa: E402
    MODALITY_EVIDENCE_SCHEMA_VERSION,
    modality_evidence_contract,
    validate_modality_evidence_payload,
)
from scripts.brainstack_golden_recall_eval import run_golden_recall_eval  # noqa: E402


REQUIRED_SCENARIOS = {
    "english": ["profile.exact_identity", "corpus.exact_document_section"],
    "hungarian": ["corpus.multilingual_hungarian"],
    "german": ["profile.german_preference", "corpus.german_document"],
    "non_latin": ["profile.chinese_identity", "graph.chinese_relation"],
}


def _modality_probe() -> dict[str, Any]:
    accepted = []
    for modality in ("image", "file", "audio", "extracted_document"):
        receipt = validate_modality_evidence_payload(
            {
                "schema": MODALITY_EVIDENCE_SCHEMA_VERSION,
                "modality": modality,
                "source_ref": f"fixture://{modality}/sample",
                "content_hash": f"sha256:{modality}-hash",
                "mime_type": "application/octet-stream",
            }
        )
        accepted.append(receipt)
    rejected_raw = validate_modality_evidence_payload(
        {
            "schema": MODALITY_EVIDENCE_SCHEMA_VERSION,
            "modality": "image",
            "source_ref": "fixture://image/raw",
            "content_hash": "sha256:raw",
            "content_base64": "not-allowed",
        }
    )
    return {
        "contract": modality_evidence_contract(),
        "accepted": accepted,
        "rejected_raw": rejected_raw,
        "passed": all(row.get("status") == "accepted" for row in accepted)
        and rejected_raw.get("status") == "rejected"
        and rejected_raw.get("reason") == "raw_payload_not_allowed",
    }


def run_multilingual_multimodal_gate() -> dict[str, Any]:
    started = perf_counter()
    golden = run_golden_recall_eval()
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    scenarios = {row["id"]: row for row in golden.get("scenarios", [])}
    language_results: dict[str, Any] = {}
    for language, scenario_ids in REQUIRED_SCENARIOS.items():
        rows = [scenarios.get(scenario_id) for scenario_id in scenario_ids]
        language_results[language] = {
            "scenario_ids": scenario_ids,
            "passed": all(row and row.get("passed") for row in rows),
        }
    modality = _modality_probe()
    max_packet_chars = max(
        [int((row.get("packet") or {}).get("char_count") or 0) for row in golden.get("scenarios", [])] or [0]
    )
    scorecard = {
        "brainstack": {
            "text_memory": "proven",
            "multilingual_text_recall": "proven_by_local_golden_cases",
            "typed_non_text_contract": "proven_shape_only",
            "full_multimodal_extraction": "deferred_not_claimed",
        },
        "mnemosyne": "comparison_deferred_without_local_evidence",
        "cerebrocortex": "procedure/session ideas adopted only as bounded read-model patterns",
        "neural_memory": "spreading activation adopted only as bounded graph expansion",
        "defaultmodeAGENT": "rerank idea adopted only as inspectable retrieval ranking",
    }
    verdict = (
        "pass"
        if golden.get("verdict") == "pass"
        and all(row["passed"] for row in language_results.values())
        and modality["passed"]
        and elapsed_ms < 10_000
        else "fail"
    )
    return {
        "schema": "brainstack.multilingual_multimodal_gate.v1",
        "verdict": verdict,
        "latency_ms": elapsed_ms,
        "max_packet_chars": max_packet_chars,
        "golden_hard_gate": golden.get("hard_gate"),
        "language_results": language_results,
        "modality_contract": modality,
        "quality_order": "accuracy > token_efficiency > speed",
        "scorecard": scorecard,
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(f"schema={report['schema']}")
    print(f"verdict={report['verdict']}")
    print(f"latency_ms={report['latency_ms']}")
    print(f"max_packet_chars={report['max_packet_chars']}")
    print(
        "languages="
        + ",".join(
            f"{language}:{'pass' if row['passed'] else 'fail'}"
            for language, row in report["language_results"].items()
        )
    )
    print(f"modality_contract={'pass' if report['modality_contract']['passed'] else 'fail'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Brainstack multilingual/multimodal proof gate.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args(argv)
    report = run_multilingual_multimodal_gate()
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        _print_summary(report)
    return 1 if report["verdict"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
