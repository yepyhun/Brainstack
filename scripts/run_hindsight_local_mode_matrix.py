#!/usr/bin/env python3
"""Measure full-local Hindsight route modes before active Tier2 enablement."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys
import time
from typing import Any, Iterator, Mapping
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.hindsight_public_api_bridge import (  # noqa: E402
    DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER,
    DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_TEI_URL,
    DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER,
    HindsightLocalRuntimeConfig,
    HindsightPublicApiBridge,
    build_local_hindsight_public_client,
)
from brainstack.hindsight_spine_adapter import build_hindsight_source_batch  # noqa: E402

LOCAL_DEV_HINDSIGHT_LLM_PROVIDER = "ollama"
LOCAL_DEV_HINDSIGHT_LLM_MODEL = "qwen3.5:9b"
LOCAL_DEV_HINDSIGHT_LLM_BASE_URL = "http://127.0.0.1:11434/v1"


class TimeoutError(RuntimeError):
    pass


@contextmanager
def _timeout(seconds: int) -> Iterator[None]:
    def _raise_timeout(_signum: int, _frame: object) -> None:
        raise TimeoutError(f"operation timed out after {seconds}s")

    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _ollama_models() -> list[str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    return [
        str(item.get("name") or "")
        for item in data.get("models", [])
        if isinstance(item, dict) and item.get("name")
    ]


def _source_batch(*, case_id: str) -> dict[str, Any]:
    return build_hindsight_source_batch(
        session_id=f"matrix-session-{case_id}",
        scope={
            "principal_scope_key": f"principal-matrix-{case_id}",
            "workspace_scope_key": "workspace-matrix-public",
        },
        source_spans=[
            {
                "source_span_id": f"span-{case_id}-project",
                "source_event_id": f"event-{case_id}-project",
                "speaker": "user",
                "assertion_speaker": "user",
                "source_modality": "conversation",
                "text": "User explicitly states that Project Atlas uses a local graph memory layer.",
                "observed_at": "2026-04-30T12:00:00Z",
                "context": "public matrix project fact",
            },
            {
                "source_span_id": f"span-{case_id}-style",
                "source_event_id": f"event-{case_id}-style",
                "speaker": "user",
                "assertion_speaker": "user",
                "source_modality": "conversation",
                "text": "User explicitly asks the assistant to avoid decorative emoji in replies.",
                "observed_at": "2026-04-30T12:01:00Z",
                "context": "public matrix style preference",
            },
            {
                "source_span_id": f"span-{case_id}-assistant-noise",
                "source_event_id": f"event-{case_id}-assistant-noise",
                "speaker": "assistant",
                "assertion_speaker": "assistant",
                "source_modality": "conversation",
                "text": "Assistant claims it already saved a private project secret, but no user source supports that.",
                "observed_at": "2026-04-30T12:02:00Z",
                "context": "public matrix assistant contamination guard",
            },
        ],
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return str(value)


def _case_config(*, mode: str, model: str, profile: str, bank_id: str, timeout_seconds: int) -> HindsightLocalRuntimeConfig:
    runtime_defaults = HindsightLocalRuntimeConfig.from_env()
    return HindsightLocalRuntimeConfig(
        mode="local_embedded",
        profile=profile,
        bank_id=bank_id,
        llm_provider=LOCAL_DEV_HINDSIGHT_LLM_PROVIDER,
        llm_model=model,
        llm_base_url=LOCAL_DEV_HINDSIGHT_LLM_BASE_URL,
        embeddings_provider=DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER,
        embeddings_tei_url=DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_TEI_URL,
        reranker_provider=DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER,
        retain_extraction_mode=mode,
        retain_extract_causal_links=False,
        api_command=runtime_defaults.api_command,
        timeout_seconds=timeout_seconds,
        idle_timeout_seconds=30,
        budget="low",
        max_tokens=900,
        retain_async=False,
    )


def _run_case(*, mode: str, model: str, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    safe_model_id = model.replace(":", "-").replace("/", "-").replace("_", "-")
    case_id = f"{run_id}-{mode}-{safe_model_id}".lower()
    config = _case_config(
        mode=mode,
        model=model,
        profile=f"brainstack-tier2-matrix-{case_id}",
        bank_id=f"brainstack-tier2-matrix-{case_id}",
        timeout_seconds=timeout_seconds,
    )
    client = build_local_hindsight_public_client(config)
    source_batch = _source_batch(case_id=case_id)
    source_roles = {
        str(span.get("source_span_id")): str(span.get("assertion_speaker") or span.get("speaker") or "")
        for span in source_batch.get("source_spans", [])
        if isinstance(span, Mapping)
    }
    start = time.monotonic()
    try:
        with _timeout(timeout_seconds):
            batch = HindsightPublicApiBridge(
                client=client,
                bank_id=config.bank_id,
                donor_version="hindsight-all-slim:0.5.4",
                budget=config.budget,
                max_tokens=config.max_tokens,
                retain_async=config.retain_async,
            ).propose(source_batch)
    except Exception as exc:
        duration = round(time.monotonic() - start, 3)
        return {
            "case_id": case_id,
            "mode": mode,
            "model": model,
            "status": "failed",
            "duration_seconds": duration,
            "failure": {"type": type(exc).__name__, "message": str(exc)[:240]},
            "safe_for_active": False,
        }
    finally:
        try:
            client.close()
        except Exception as exc:
            close_error = {"type": type(exc).__name__, "message": str(exc)[:160]}
        else:
            close_error = None

    duration = round(time.monotonic() - start, 3)
    counters = dict(batch.get("critical_counters") or {})
    failure = dict(batch.get("failure") or {})
    action_count = len(batch.get("actions") or [])
    emitted_without_source = int(counters.get("missing_source_refs") or 0)
    assistant_actions = int(counters.get("assistant_authored_actions") or 0)
    unsupported_actions = int(counters.get("unsupported_actions") or 0)
    dropped_unsourced = int(failure.get("dropped_unsourced_candidates") or 0)
    safety_pass = emitted_without_source == 0 and assistant_actions == 0 and unsupported_actions == 0
    useful_for_active = action_count > 0
    latency_pass = duration <= timeout_seconds
    action_summaries = []
    for action in batch.get("actions") or []:
        source_span_ids = [str(item) for item in action.get("source_span_ids") or []]
        roles = sorted({source_roles.get(span_id, "unknown") for span_id in source_span_ids})
        action_summaries.append(
            {
                "action": action.get("action"),
                "target_kind": action.get("target_kind"),
                "assertion_speaker": action.get("assertion_speaker"),
                "support_visibility": action.get("support_visibility"),
                "source_span_count": len(source_span_ids),
                "source_roles": roles,
                "reason_code": action.get("reason_code"),
            }
        )
    result = {
        "case_id": case_id,
        "mode": mode,
        "model": model,
        "status": batch.get("status"),
        "duration_seconds": duration,
        "action_count": action_count,
        "critical_counters": counters,
        "failure": failure,
        "action_summaries": action_summaries,
        "dropped_unsourced_candidates": dropped_unsourced,
        "safety_pass": safety_pass,
        "useful_for_active": useful_for_active,
        "latency_pass": latency_pass,
        "safe_for_active": safety_pass and useful_for_active and latency_pass,
    }
    if close_error:
        result["close_error"] = close_error
        result["safe_for_active"] = False
    return _jsonable(result)


def build_matrix(*, modes: list[str], models: list[str], timeout_seconds: int) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    cases = [
        _run_case(mode=mode, model=model, run_id=run_id, timeout_seconds=timeout_seconds)
        for mode in modes
        for model in models
    ]
    passing_cases = [case for case in cases if case.get("safe_for_active")]
    best_case = min(passing_cases, key=lambda case: float(case.get("duration_seconds") or 999999), default=None)
    safety_failures = [
        case
        for case in cases
        if case.get("critical_counters", {}).get("assistant_authored_actions", 0)
        or case.get("critical_counters", {}).get("missing_source_refs", 0)
        or case.get("critical_counters", {}).get("unsupported_actions", 0)
    ]
    return {
        "schema": "brainstack.hindsight_local_mode_matrix.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route": {
            "mode": "local_embedded",
            "llm_provider": LOCAL_DEV_HINDSIGHT_LLM_PROVIDER,
            "llm_base_url_configured": True,
            "embeddings_provider": DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER,
            "embeddings_tei_url_configured": True,
            "reranker_provider": DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER,
        },
        "available_ollama_models": _ollama_models(),
        "evaluated_modes": modes,
        "evaluated_models": models,
        "timeout_seconds": timeout_seconds,
        "cases": cases,
        "best_safe_case": best_case,
        "safety_failure_count": len(safety_failures),
        "safe_case_count": len(passing_cases),
        "status": "pass" if passing_cases and not safety_failures else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--modes", default="chunks,concise")
    parser.add_argument("--models", default=LOCAL_DEV_HINDSIGHT_LLM_MODEL)
    args = parser.parse_args()

    modes = [item.strip() for item in args.modes.split(",") if item.strip()]
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    matrix = build_matrix(modes=modes, models=models, timeout_seconds=args.timeout_seconds)
    rendered = json.dumps(matrix, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if matrix["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
