#!/usr/bin/env python3
"""Validate GA readiness dashboard."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "brainstack.ga_readiness_dashboard.v1":
        errors.append("bad schema")
    counts = payload.get("counts") or {}
    if payload.get("ready") and (counts.get("open_p0") or counts.get("open_p1")):
        errors.append("ready with open P0/P1")
    if payload.get("ready") and payload.get("manual_only_proof"):
        errors.append("ready with manual-only proof")
    if payload.get("ready") and payload.get("blocking"):
        errors.append("ready with blocking reasons")
    for probe in payload.get("probes") or []:
        if probe.get("observed", {}).get("path_proof_required") and not probe.get("path_proof_ok"):
            errors.append(f"path proof missing: {probe.get('probe_id')}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_ga_dashboard.py <dashboard.json>")
        return 2
    payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    errors = validate(payload)
    if errors:
        print("\n".join(errors))
        return 1
    print("PASS ga dashboard valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
