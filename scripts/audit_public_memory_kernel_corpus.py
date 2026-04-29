#!/usr/bin/env python3
"""Audit the public-safe memory-kernel fixture corpus."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


SECRET_PATTERNS = {
    "discord_bot_or_user_token": re.compile(
        r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b"
    ),
    "openai_style_secret_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_personal_access_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
}

STATIC_MARKER_PATTERNS = {
    "local_absolute_home_path": re.compile(r"/home/[A-Za-z0-9_.-]+"),
    "discord_channel_url": re.compile(r"https?://discord\.com/channels/\d+/\d+"),
    "private_runtime_container_name": re.compile(r"\bhermes-[A-Za-z0-9_.-]*live\b"),
    "private_repository_owner_literal": re.compile(r"\b[A-Za-z0-9_.-]+-AI/[A-Za-z0-9_.-]+\b"),
}


REQUIRED_INDEX_SCENARIO_FIELDS = {
    "scenario_id",
    "fixture",
    "represents_private_failure_class",
    "invariant",
    "forbidden_regression",
    "required_trace_reason_code",
    "expected_oracle",
    "does_not_contain_private_data",
}


FORBIDDEN_EXPECTED_PROSE_KEYS = {
    "expected_answer",
    "expected_response",
    "final_answer_text",
    "response_text",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _scenario_ids(fixture_dir: Path) -> set[str]:
    output: set[str] = set()
    for path in sorted((fixture_dir / "conversations").glob("*.json")):
        data = _load_json(path)
        output.add(str(data.get("scenario_id") or ""))
    return output


def _negative_ids(fixture_dir: Path) -> set[str]:
    output: set[str] = set()
    for path in sorted((fixture_dir / "negative").glob("*.json")):
        data = _load_json(path)
        output.add(str(data.get("negative_id") or path.stem))
    return output


def _scan_static_leaks(fixture_dir: Path, index: Mapping[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    blocked_pattern_names = set(
        (index.get("private_data_policy") or {}).get("blocked_static_marker_patterns") or []
    )
    for path in sorted(fixture_dir.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(errors="ignore")
        rel = str(path.relative_to(fixture_dir))
        for marker in sorted(blocked_pattern_names):
            pattern = STATIC_MARKER_PATTERNS.get(marker)
            if pattern and pattern.search(text):
                findings.append(
                    {
                        "file": rel,
                        "kind": "blocked_static_marker_pattern",
                        "marker": marker,
                    }
                )
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(
                    {
                        "file": rel,
                        "kind": "blocked_secret_pattern",
                        "marker": name,
                    }
                )
    return findings


def audit_public_corpus(fixture_dir: Path) -> dict[str, Any]:
    fixture_dir = fixture_dir.resolve()
    issues: list[dict[str, Any]] = []
    index_path = fixture_dir / "scenario_index.json"
    equivalence_path = fixture_dir / "equivalence_map.json"
    if not index_path.exists():
        issues.append({"kind": "missing_scenario_index", "file": "scenario_index.json"})
        index: dict[str, Any] = {}
    else:
        index = _load_json(index_path)

    if not equivalence_path.exists():
        issues.append({"kind": "missing_equivalence_map", "file": "equivalence_map.json"})
        equivalence: list[dict[str, Any]] = []
    else:
        equivalence = _load_json(equivalence_path)

    scenario_ids = _scenario_ids(fixture_dir)
    negative_ids = _negative_ids(fixture_dir)
    index_scenarios = index.get("scenarios") or []
    index_negatives = index.get("negative_fixtures") or []
    index_ids = {str(item.get("scenario_id") or "") for item in index_scenarios}
    index_negative_ids = {str(item.get("negative_id") or "") for item in index_negatives}
    equivalence_ids = {str(item.get("public_scenario_id") or "") for item in equivalence}

    if scenario_ids != index_ids:
        issues.append(
            {
                "kind": "scenario_index_mismatch",
                "missing_from_index": sorted(scenario_ids - index_ids),
                "extra_in_index": sorted(index_ids - scenario_ids),
            }
        )
    if scenario_ids != equivalence_ids:
        issues.append(
            {
                "kind": "equivalence_map_mismatch",
                "missing_from_equivalence": sorted(scenario_ids - equivalence_ids),
                "extra_in_equivalence": sorted(equivalence_ids - scenario_ids),
            }
        )
    if negative_ids != index_negative_ids:
        issues.append(
            {
                "kind": "negative_index_mismatch",
                "missing_from_index": sorted(negative_ids - index_negative_ids),
                "extra_in_index": sorted(index_negative_ids - negative_ids),
            }
        )

    for item in index_scenarios:
        missing = sorted(REQUIRED_INDEX_SCENARIO_FIELDS - set(item))
        if missing:
            issues.append(
                {
                    "kind": "scenario_index_missing_fields",
                    "scenario_id": item.get("scenario_id"),
                    "missing": missing,
                }
            )
        if item.get("expected_oracle") != "contract_and_trace":
            issues.append(
                {
                    "kind": "scenario_oracle_not_contract_trace",
                    "scenario_id": item.get("scenario_id"),
                    "expected_oracle": item.get("expected_oracle"),
                }
            )
        if item.get("does_not_contain_private_data") is not True:
            issues.append(
                {
                    "kind": "scenario_private_data_not_explicitly_blocked",
                    "scenario_id": item.get("scenario_id"),
                }
            )

    for path in sorted((fixture_dir / "conversations").glob("*.json")):
        data = _load_json(path)
        expected = data.get("expected") or {}
        prose_keys = sorted(FORBIDDEN_EXPECTED_PROSE_KEYS & set(expected))
        if prose_keys:
            issues.append(
                {
                    "kind": "expected_output_prose_oracle",
                    "file": str(path.relative_to(fixture_dir)),
                    "keys": prose_keys,
                }
            )
        if "required_trace_reason_codes" not in expected:
            issues.append(
                {
                    "kind": "expected_missing_trace_reason_codes",
                    "file": str(path.relative_to(fixture_dir)),
                }
            )

    for item in index_negatives:
        if not item.get("negative_id") or not item.get("fixture") or not item.get("expected_error"):
            issues.append(
                {
                    "kind": "negative_index_missing_fields",
                    "negative_id": item.get("negative_id"),
                }
            )

    leak_findings = _scan_static_leaks(fixture_dir, index)
    issues.extend(leak_findings)

    return {
        "schema": "brainstack.public_memory_kernel_corpus_audit.v1",
        "fixture_dir": str(fixture_dir),
        "status": "pass" if not issues else "fail",
        "scenario_count": len(scenario_ids),
        "negative_count": len(negative_ids),
        "scenario_index_count": len(index_ids),
        "equivalence_count": len(equivalence_ids),
        "leak_findings": leak_findings,
        "issues": issues,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/public_memory_kernel"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = audit_public_corpus(args.fixtures)
    if args.out:
        _write_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
