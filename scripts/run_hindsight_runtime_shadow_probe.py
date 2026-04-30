#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import signal
from typing import Any
import urllib.error
import urllib.request

from brainstack.hindsight_public_api_bridge import (
    HindsightLocalRuntimeConfig,
    HindsightPublicApiBridge,
    build_local_hindsight_public_client,
)
from brainstack.hindsight_spine_adapter import build_hindsight_source_batch


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return str(value)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return "unavailable"


def _donor_version(packages: dict[str, str]) -> str:
    if packages.get("hindsight-all") != "unavailable":
        return f"hindsight-all:{packages['hindsight-all']}"
    if packages.get("hindsight-all-slim") != "unavailable":
        return f"hindsight-all-slim:{packages['hindsight-all-slim']}"
    return "hindsight:unavailable"


def _ollama_status() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"status": "fail", "reason": type(exc).__name__}
    models = [
        str(item.get("name") or "")
        for item in data.get("models", [])
        if isinstance(item, dict) and item.get("name")
    ]
    return {"status": "pass", "models": models}


def _safe_source_batch() -> dict[str, Any]:
    return build_hindsight_source_batch(
        session_id="shadow-session-public",
        scope={
            "principal_scope_key": "principal-public-shadow",
            "workspace_scope_key": "workspace-public-shadow",
        },
        source_spans=[
            {
                "source_span_id": "span-public-shadow-project",
                "source_event_id": "event-public-shadow-project",
                "speaker": "user",
                "assertion_speaker": "user",
                "source_modality": "conversation",
                "text": "User explicitly states that Project Atlas uses a local graph memory layer.",
                "observed_at": "2026-04-30T12:00:00Z",
                "context": "public shadow probe",
            }
        ],
    )


@contextmanager
def _operation_timeout(seconds: int):
    def _raise_timeout(_signum, _frame):
        raise TimeoutError(f"shadow probe exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(max(1, int(seconds)))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def run_probe() -> dict[str, Any]:
    config = HindsightLocalRuntimeConfig.from_env()
    report: dict[str, Any] = {
        "schema": "brainstack.hindsight_runtime_shadow_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route": {
            "mode": config.mode,
            "profile": config.profile,
            "bank_id": config.bank_id,
            "llm_provider": config.llm_provider,
            "llm_model": config.llm_model,
            "llm_base_url_configured": bool(config.llm_base_url),
            "llm_api_key_configured": bool(config.llm_api_key),
            "embeddings_provider": config.embeddings_provider,
            "embeddings_tei_url_configured": bool(config.embeddings_tei_url),
            "reranker_provider": config.reranker_provider,
            "retain_extraction_mode": config.retain_extraction_mode,
            "retain_extract_causal_links": config.retain_extract_causal_links,
            "api_command_configured": bool(config.api_command),
            "budget": config.budget,
            "retain_async": config.retain_async,
        },
        "packages": {
            "hindsight-all": _package_version("hindsight-all"),
            "hindsight-all-slim": _package_version("hindsight-all-slim"),
            "hindsight-api-slim": _package_version("hindsight-api-slim"),
            "hindsight-client": _package_version("hindsight-client"),
            "pg0-embedded": _package_version("pg0-embedded"),
        },
        "ollama": _ollama_status() if config.llm_provider == "ollama" else {"status": "skipped"},
        "proposal_batch": None,
        "critical_counters": {},
        "status": "fail",
        "blockers": [],
    }
    if config.mode not in {"local", "local_embedded"}:
        report["blockers"].append("non_local_hindsight_mode")
    if config.llm_provider == "ollama":
        models = set(report["ollama"].get("models") or [])
        if report["ollama"].get("status") != "pass":
            report["blockers"].append("ollama_unavailable")
        elif config.llm_model not in models:
            report["blockers"].append("ollama_model_missing")
    if report["blockers"]:
        return report

    client = build_local_hindsight_public_client(config)
    try:
        try:
            with _operation_timeout(config.timeout_seconds):
                batch = HindsightPublicApiBridge(
                    client=client,
                    bank_id=config.bank_id,
                    donor_version=_donor_version(report["packages"]),
                    budget=config.budget,
                    max_tokens=config.max_tokens,
                    retain_async=config.retain_async,
                ).propose(_safe_source_batch())
        except Exception as exc:
            report["blockers"].append(f"shadow_probe_exception:{type(exc).__name__}")
            report["proposal_batch"] = {
                "status": "unavailable",
                "failure": str(exc)[:240],
            }
            return report
    finally:
        client.close()

    report["proposal_batch"] = _jsonable(
        {
            "schema": batch.get("schema"),
            "status": batch.get("status"),
            "donor": batch.get("donor"),
            "donor_version": batch.get("donor_version"),
            "adapter_version": batch.get("adapter_version"),
            "action_count": len(batch.get("actions") or []),
            "failure": batch.get("failure"),
        }
    )
    report["critical_counters"] = dict(batch.get("critical_counters") or {})
    counters = report["critical_counters"]
    if batch.get("status") == "unavailable":
        report["blockers"].append("proposal_batch_unavailable")
    if counters.get("assistant_authored_actions", 0):
        report["blockers"].append("assistant_authored_actions")
    if counters.get("unsupported_actions", 0):
        report["blockers"].append("unsupported_actions")
    if counters.get("missing_source_refs", 0):
        report["blockers"].append("missing_source_refs")
    report["status"] = "pass" if not report["blockers"] else "fail"
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = run_probe()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
