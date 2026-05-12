#!/usr/bin/env python3
"""Verify the Hermes auxiliary compression failure guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.operating_loop import build_compression_failure_guard  # noqa: E402


REPORT_SCHEMA = "brainstack.hermes_auxiliary_compression_guard_proof.v1"


def build_report() -> dict[str, object]:
    incident = build_compression_failure_guard(
        [
            {"session_id": "a", "message": "Preflight compression: ~238,150 tokens >= threshold"},
            {"session_id": "b", "message": "Preflight compression: ~252,972 tokens >= threshold"},
            {"session_id": "a", "message": "Failed to generate context summary: Codex auxiliary Responses stream exceeded 120.0s total timeout"},
            {"session_id": "b", "message": "Failed to generate context summary: [Errno 9] Bad file descriptor"},
        ]
    )
    clean = build_compression_failure_guard(
        [
            {"session_id": "a", "message": "Preflight compression: ~210,000 tokens >= threshold"},
            {"session_id": "a", "message": "context compression done: messages=300->12 tokens=~18000"},
        ]
    )
    proof = {
        "incident_detector_catches_bad_fd": incident["status"] == "fail"
        and "auxiliary_stream_lifecycle_poisoning_suspected" in incident["issues"],
        "owner_classified_as_hermes": incident["owner"] == "hermes_auxiliary_runtime",
        "overlap_timeout_and_bad_fd_are_separate_signals": incident["proof"]["overlapping_compression_detected"] is True
        and incident["proof"]["timeout_detected"] is True
        and incident["proof"]["bad_file_descriptor_detected"] is True,
        "clean_compression_passes": clean["status"] == "pass" and clean["issues"] == [],
        "read_only_public_safe": incident["read_only"] is True and clean["read_only"] is True and incident["public_safe"] is True,
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "side_effect_free": True,
        "issues": issues,
        "proof": proof,
        "incident_guard_status": incident["status"],
        "clean_guard_status": clean["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hermes auxiliary compression guard.")
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

