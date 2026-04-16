#!/usr/bin/env python3
"""Broader deployed-live quality baseline refresh for Phase 25.

This script runs a broader product-shaped scenario matrix against the real
deployed Bestie provider path while isolating memory writes inside a temporary
HERMES_HOME. It stages only the deployed prompt/auth/config subset, keeps
Brainstack as the durable memory owner, and records packet/state evidence for
important anomalies while comparing the refreshed read against the Phase 23
baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[1]


def _env_path(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return Path(value).expanduser()
    return None


DEFAULT_BESTIE_ROOT = _env_path("BRAINSTACK_BESTIE_ROOT", "BRAINSTACK_HERMES_ROOT", "HERMES_ROOT")
DEFAULT_REPORT = REPO_ROOT / "reports" / "phase25" / "brainstack-25-broader-deployed-live-eval.json"
DEFAULT_MATRIX = REPO_ROOT / "reports" / "phase25" / "brainstack-25-scenario-matrix.json"
DEFAULT_PHASE23_BASELINE = REPO_ROOT / "reports" / "phase23" / "brainstack-23-broader-deployed-live-eval.json"
DEFAULT_DOCKER_CONTAINER = os.environ.get("BRAINSTACK_DOCKER_CONTAINER", "").strip() or None


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("—", "-").replace("–", "-")
    return " ".join(text.split())


def _contains_any(answer: str, options: Sequence[str]) -> bool:
    normalized = _normalize_text(answer)
    return any(_normalize_text(option) in normalized for option in options)


def _positions_in_order(answer: str, groups: Sequence[Sequence[str]]) -> bool:
    normalized = _normalize_text(answer)
    cursor = -1
    for group in groups:
        positions = [
            normalized.find(_normalize_text(option))
            for option in group
            if _normalize_text(option) in normalized
        ]
        positions = [pos for pos in positions if pos >= 0]
        if not positions:
            return False
        next_pos = min(pos for pos in positions if pos > cursor) if any(pos > cursor for pos in positions) else -1
        if next_pos < 0:
            return False
        cursor = next_pos
    return True


def _summarize_selected_rows(prefetch_debug: Dict[str, Any] | None) -> Dict[str, int]:
    selected_rows = dict((prefetch_debug or {}).get("selected_rows") or {})
    summary: Dict[str, int] = {}
    total = 0
    for key in ("profile_items", "matched", "recent", "transcript_rows", "graph_rows", "corpus_rows"):
        count = len(list(selected_rows.get(key) or []))
        summary[key] = count
        total += count
    summary["total_selected_rows"] = total
    return summary


def _extract_provider_auth(auth_payload: Any, provider_name: str) -> Dict[str, str]:
    provider_entry: Any = {}
    if isinstance(auth_payload, dict):
        if isinstance(auth_payload.get("providers"), dict):
            provider_entry = auth_payload.get("providers", {}).get(provider_name) or {}
        else:
            provider_entry = auth_payload.get(provider_name) or {}

    if isinstance(provider_entry, str):
        return {"api_key": provider_entry, "base_url": ""}

    if not isinstance(provider_entry, dict):
        return {"api_key": "", "base_url": ""}

    def _find_key(mapping: Dict[str, Any], candidates: Sequence[str]) -> str:
        for key in candidates:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in mapping.values():
            if isinstance(value, dict):
                nested = _find_key(value, candidates)
                if nested:
                    return nested
        return ""

    return {
        "api_key": _find_key(
            provider_entry,
            ("api_key", "key", "token", "access_token", "agent_key"),
        ),
        "base_url": _find_key(
            provider_entry,
            ("base_url", "url", "inference_base_url"),
        ),
    }


def _extract_runtime_settings(home: Path, bestie_root: Path) -> Dict[str, Any]:
    raw_config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    config: Dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    raw_auth = json.loads((home / "auth.json").read_text(encoding="utf-8"))
    auth: Dict[str, Any] = raw_auth if isinstance(raw_auth, dict) else {}
    raw_model_cfg = config.get("model")
    model_cfg: Dict[str, Any] = raw_model_cfg if isinstance(raw_model_cfg, dict) else {}
    provider = str(
        config.get("provider")
        or model_cfg.get("provider")
        or auth.get("active_provider")
        or ""
    ).strip()
    raw_model = config.get("model")
    model = str(raw_model or "").strip() if isinstance(raw_model, str) else ""
    if not model:
        model = str(model_cfg.get("default") or model_cfg.get("name") or "").strip()
    raw_providers = config.get("providers")
    providers: Dict[str, Any] = raw_providers if isinstance(raw_providers, dict) else {}
    raw_provider_cfg = providers.get(provider)
    provider_cfg: Dict[str, Any] = raw_provider_cfg if isinstance(raw_provider_cfg, dict) else {}
    auth_cfg = _extract_provider_auth(auth, provider)
    if str(bestie_root) not in sys.path:
        sys.path.insert(0, str(bestie_root))
    from hermes_cli.runtime_provider import resolve_runtime_provider  # type: ignore

    runtime = resolve_runtime_provider(requested=provider or None)
    base_url = (
        str(runtime.get("base_url") or "").strip()
        or str(config.get("base_url") or "").strip()
        or str(model_cfg.get("base_url") or "").strip()
        or str(provider_cfg.get("base_url") or "").strip()
        or auth_cfg.get("base_url", "")
    )
    api_key = (
        str(runtime.get("api_key") or "").strip()
        or auth_cfg.get("api_key", "")
    )
    return {
        "provider": str(runtime.get("provider") or provider),
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "credential_pool": runtime.get("credential_pool"),
        "api_mode": runtime.get("api_mode"),
    }


def _copy_from_container(container: str, remote_path: str, local_path: Path, *, optional: bool = False) -> None:
    cmd = ["docker", "cp", f"{container}:{remote_path}", str(local_path)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode == 0:
        return
    if optional:
        return
    raise RuntimeError(f"docker cp failed for {remote_path}: {completed.stderr.strip() or completed.stdout.strip()}")


def _copy_from_home(source_home: Path, relative_path: str, local_path: Path, *, optional: bool = False) -> None:
    source_path = source_home / relative_path
    if not source_path.exists():
        if optional:
            return
        raise FileNotFoundError(source_path)
    if source_path.is_dir():
        shutil.copytree(source_path, local_path, dirs_exist_ok=True)
    else:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, local_path)


def _stage_deployed_subset(*, source_home: Path | None, docker_container: str | None, temp_home: Path) -> None:
    temp_home.mkdir(parents=True, exist_ok=True)
    (temp_home / "brainstack").mkdir(parents=True, exist_ok=True)
    required_files = ("config.yaml", "auth.json")
    optional_files = ("SOUL.md", ".skills_prompt_snapshot.json")

    if source_home is not None:
        for name in required_files:
            _copy_from_home(source_home, name, temp_home / name, optional=False)
        for name in optional_files:
            _copy_from_home(source_home, name, temp_home / name, optional=True)
        _copy_from_home(source_home, "skills", temp_home / "skills", optional=True)
        return

    if not docker_container:
        raise RuntimeError("Either --deployed-home or --docker-container must be provided.")

    for name in required_files:
        _copy_from_container(docker_container, f"/opt/data/{name}", temp_home / name, optional=False)
    for name in optional_files:
        _copy_from_container(docker_container, f"/opt/data/{name}", temp_home / name, optional=True)
    _copy_from_container(docker_container, "/opt/data/skills", temp_home / "skills", optional=True)


@dataclass(frozen=True)
class Scenario:
    name: str
    category: str
    use_reset: bool
    seed_messages: Sequence[str]
    final_question: str
    evaluator: str
    expected: str


SCENARIOS: List[Scenario] = [
    Scenario(
        name="coherent_followthrough",
        category="coherent_continuous_conversation",
        use_reset=False,
        seed_messages=(
            "Friday board-game night reminder: Maya cannot drink caffeine after 6 pm.",
            "And Jon is allergic to peanuts, so snacks have to stay peanut-free.",
        ),
        final_question="Give me a one-line snack and drink reminder for Friday night.",
        evaluator="coherent_followthrough",
        expected="mention no caffeine after 6 pm and peanut-free snacks",
    ),
    Scenario(
        name="correction_carry_forward",
        category="coherent_continuous_conversation",
        use_reset=False,
        seed_messages=(
            "My dentist appointment was supposed to be Tuesday at 4 PM.",
            "Actually it got moved, it's Thursday at 3:30 PM now.",
        ),
        final_question="When is my dentist appointment now?",
        evaluator="dentist_correction",
        expected="Thursday at 3:30 PM",
    ),
    Scenario(
        name="dietary_constraint",
        category="stateful_continuity_after_reset",
        use_reset=True,
        seed_messages=(
            "I'm planning Saturday brunch for friends.",
            "One of the guests is lactose intolerant, so I need to remember lactose-free dishes.",
        ),
        final_question="Before I shop more, what dietary issue did I say I need to remember?",
        evaluator="dietary_constraint",
        expected="lactose intolerance / lactose-free",
    ),
    Scenario(
        name="style_identity_after_reset",
        category="stateful_continuity_after_reset",
        use_reset=True,
        seed_messages=(
            "Call me Tomi.",
            "Your name is Bestie when You talk to me.",
            "Always answer me in Hungarian.",
            "Use a direct Humanizer style and avoid emoji.",
        ),
        final_question="Briefly tell me what name I use for You, what name I asked You to use for me, and what general style I prefer.",
        evaluator="style_identity",
        expected="Bestie, Tomi, Hungarian, direct Humanizer, no emoji",
    ),
    Scenario(
        name="proactive_continuity_after_reset",
        category="proactive_stateful_continuity",
        use_reset=True,
        seed_messages=(
            "I'm planning a birthday dinner for Saturday.",
            "The restaurant is Riverside Kitchen.",
            "Anna needs gluten-free options.",
        ),
        final_question="Can You help me continue that plan without me repeating the details?",
        evaluator="proactive_continuity",
        expected="should bring up the birthday dinner, Riverside Kitchen, and gluten-free need",
    ),
    Scenario(
        name="temporal_order",
        category="long_range_relation_tracking",
        use_reset=True,
        seed_messages=(
            "On Monday I had my dentist checkup.",
            "On Wednesday I replaced the brake pads on my bike.",
            "On Friday I met with my tax accountant.",
        ),
        final_question="Put those three things in order from earliest to latest.",
        evaluator="temporal_order",
        expected="dentist -> brake pads -> tax accountant",
    ),
    Scenario(
        name="aggregate_trip_distance",
        category="long_range_relation_tracking",
        use_reset=True,
        seed_messages=(
            "Last month I drove 120 miles to Debrecen.",
            "Then I drove 210 miles to Szeged.",
            "After that I drove 275 miles back to Budapest.",
        ),
        final_question="What was the total distance I drove altogether?",
        evaluator="aggregate_trip_distance",
        expected="605 miles",
    ),
    Scenario(
        name="corrected_date_resolution",
        category="long_range_relation_tracking",
        use_reset=True,
        seed_messages=(
            "My cat Laura got injured on February 22.",
            "Correction: I mean February 22, 2025, not 2024.",
        ),
        final_question="What exact date did I finally say Laura got injured?",
        evaluator="corrected_date",
        expected="February 22, 2025",
    ),
    Scenario(
        name="relation_tracking_pet_owner",
        category="long_range_relation_tracking",
        use_reset=True,
        seed_messages=(
            "My sister Nora adopted a dog named Pixel.",
            "Nora's partner is Ákos.",
            "Pixel hates rain but loves long walks.",
        ),
        final_question="Who is Pixel relative to Nora?",
        evaluator="pixel_relation",
        expected="Pixel is Nora's dog",
    ),
    Scenario(
        name="larger_knowledge_body",
        category="usable_storage_of_large_knowledge",
        use_reset=True,
        seed_messages=(
            "Workshop note one: the workshop is on May 12.",
            "Workshop note two: the venue is Riverside Hub.",
            "Workshop note three: the projector is in Room C.",
            "Workshop note four: Marta needs a vegan lunch.",
            "Workshop note five: the backup speaker is Levente.",
            "Workshop note six: the printed agenda should use blue covers.",
        ),
        final_question="For the workshop, what room did I mention for the projector and what food note did I mention for Marta?",
        evaluator="larger_knowledge_body",
        expected="Room C and vegan lunch for Marta",
    ),
]


def _evaluate_answer(scenario: Scenario, answer: str) -> Dict[str, Any]:
    normalized = _normalize_text(answer)
    missing: List[str] = []
    required: Dict[str, tuple[str, ...]] = {}
    strong = False

    if scenario.evaluator == "coherent_followthrough":
        required = {
            "caffeine": ("caffeine", "decaf", "6 pm", "6pm"),
            "peanut_free": ("peanut-free", "peanut free", "no peanuts", "peanut allergy"),
        }
        strong = _contains_any(answer, ("maya",)) and _contains_any(answer, ("jon",))
    elif scenario.evaluator == "dentist_correction":
        required = {
            "day": ("thursday", "csutortok"),
            "time": ("3:30", "3.30", "3 30", "harom harminc"),
        }
        strong = _contains_any(answer, ("now", "moved", "updated", "most"))
    elif scenario.evaluator == "dietary_constraint":
        required = {
            "issue": ("lactose", "lactose-free", "laktóz", "tejmentes"),
        }
        strong = _contains_any(answer, ("guest", "dish", "brunch", "vendeg", "etel"))
    elif scenario.evaluator == "style_identity":
        required = {
            "assistant_name": ("bestie",),
            "user_name": ("tomi",),
            "language": ("hungarian", "magyar"),
            "style": ("humanizer", "direct", "direkt", "kozvetlen", "termeszetes", "lenyegretoro"),
        }
        strong = _contains_any(answer, ("style", "stilus", "communication", "kommunikacio"))
    elif scenario.evaluator == "proactive_continuity":
        required = {
            "event": ("birthday dinner", "szuletesnapi vacsora", "birthday"),
            "venue": ("riverside kitchen",),
            "dietary": ("gluten-free", "gluten free", "glutenmentes"),
        }
        strong = _contains_any(answer, ("continue", "folytat", "let's continue", "segitek tovabb"))
    elif scenario.evaluator == "temporal_order":
        required = {
            "order": ("monday", "dentist", "wednesday", "brake", "friday", "tax"),
        }
        strong = _positions_in_order(
            answer,
            (
                ("dentist", "checkup", "fogorvosi", "fogorvos"),
                ("brake pads", "bike", "brake", "fekbetet", "kerekpar"),
                ("tax accountant", "accountant", "tax", "konyvelo", "könyvelő"),
            ),
        )
        if not strong:
            strong = _positions_in_order(
                answer,
                (
                    ("monday", "hetfo", "hétfő"),
                    ("wednesday", "szerda"),
                    ("friday", "pentek", "péntek"),
                ),
            )
        if not strong:
            missing.append("correct chronological order")
        return {
            "passed": strong,
            "quality_class": "strong_pass" if strong else "miss",
            "missing": missing,
        }
    elif scenario.evaluator == "aggregate_trip_distance":
        required = {
            "total": ("605", "605 miles"),
        }
        strong = _contains_any(answer, ("miles", "mile", "altogether", "osszesen"))
    elif scenario.evaluator == "corrected_date":
        required = {
            "year": ("2025",),
            "date": ("february 22", "feb 22", "februar 22", "február 22"),
        }
        strong = not _contains_any(answer, ("2024",))
    elif scenario.evaluator == "pixel_relation":
        required = {
            "nora": ("nora",),
            "dog": ("dog", "kutya"),
        }
        strong = _contains_any(answer, ("pixel",))
    elif scenario.evaluator == "larger_knowledge_body":
        required = {
            "room": ("room c", "c room", "terem c", "szoba c", "c teremben", "c szobaban", "c szobában"),
            "dietary": ("marta",),
            "vegan": ("vegan", "vegán"),
        }
        strong = _contains_any(answer, ("workshop", "muhely", "workshophoz"))
    else:
        raise ValueError(f"Unknown evaluator: {scenario.evaluator}")

    for label, choices in required.items():
        if not _contains_any(normalized, choices):
            missing.append(label)

    passed = not missing
    quality_class = "strong_pass" if passed and strong else ("acceptable_pass" if passed else "miss")
    return {"passed": passed, "quality_class": quality_class, "missing": missing}


def _load_run_agent(bestie_root: Path) -> Any:
    if str(bestie_root) not in sys.path:
        sys.path.insert(0, str(bestie_root))
    import run_agent  # type: ignore

    return run_agent


def _brainstack_provider(memory_manager: Any) -> Any | None:
    for provider in list(getattr(memory_manager, "_providers", []) or []):
        if str(getattr(provider, "name", "") or "") == "brainstack":
            return provider
    return None


def _route_snapshot(provider: Any) -> Dict[str, Any]:
    return {
        "policy": dict(getattr(provider, "_last_prefetch_policy", {}) or {}),
        "routing": dict(getattr(provider, "_last_prefetch_routing", {}) or {}),
        "channels": [dict(item) for item in list(getattr(provider, "_last_prefetch_channels", []) or []) if isinstance(item, dict)],
    }


def _persisted_scope_snapshot(provider: Any) -> Dict[str, Any]:
    store = getattr(provider, "_store", None)
    principal_scope_key = str(getattr(provider, "_principal_scope_key", "") or "").strip()
    if store is None or not principal_scope_key:
        return {"principal_scope_key": principal_scope_key}
    try:
        profile_items = store.list_profile_items(limit=20, principal_scope_key=principal_scope_key)
    except Exception:
        profile_items = []
    try:
        current_states = store.list_current_graph_states(limit=20, principal_scope_key=principal_scope_key)
    except Exception:
        current_states = []
    return {
        "principal_scope_key": principal_scope_key,
        "profile_item_count": len(profile_items),
        "profile_stable_keys": [str(item.get("stable_key") or "") for item in profile_items],
        "profile_items": [
            {
                "stable_key": str(item.get("stable_key") or ""),
                "content": str(item.get("content") or "")[:180],
            }
            for item in profile_items
        ],
        "current_state_count": len(current_states),
        "current_state_pairs": [
            {
                "subject": str(row.get("subject") or ""),
                "predicate": str(row.get("predicate") or ""),
                "object_value": str(row.get("object_value") or ""),
            }
            for row in current_states
        ],
    }


def _make_agent(run_agent: Any, runtime: Dict[str, str], *, session_id: str, user_id: str) -> Any:
    agent = run_agent.AIAgent(
        api_key=runtime["api_key"],
        model=runtime["model"],
        provider=runtime["provider"],
        base_url=runtime["base_url"],
        api_mode=runtime.get("api_mode"),
        credential_pool=runtime.get("credential_pool"),
        quiet_mode=True,
        platform="discord",
        user_id=user_id,
        skip_context_files=False,
        skip_memory=False,
        persist_session=False,
        max_iterations=10,
        session_id=session_id,
    )
    provider = _brainstack_provider(agent._memory_manager)
    if provider is not None:
        setattr(provider, "_capture_candidate_debug", True)
    setattr(agent, "_cleanup_task_resources", lambda task_id: None)
    return agent


def _run_single_scenario(bestie_root: Path, temp_home: Path, runtime: Dict[str, str], scenario: Scenario) -> Dict[str, Any]:
    os.environ["HERMES_HOME"] = str(temp_home)
    run_agent = _load_run_agent(bestie_root)
    user_id = f"phase25:{scenario.name}"

    seed_agent = _make_agent(run_agent, runtime, session_id=f"phase25-{scenario.name}-seed", user_id=user_id)
    history: List[Dict[str, Any]] = []
    seed_replies: List[str] = []
    seed_failures: List[str] = []
    for message in scenario.seed_messages:
        try:
            result = seed_agent.run_conversation(message, conversation_history=history)
            history = list(result.get("messages") or [])
            seed_replies.append(str(result.get("final_response") or ""))
        except Exception as exc:
            seed_failures.append(f"{type(exc).__name__}: {exc}")
            break

    final_result: Dict[str, Any] | None = None
    active_agent = seed_agent
    active_history = history
    reset_reply = None
    if scenario.use_reset and not seed_failures:
        try:
            seed_agent.shutdown_memory_provider(history)
        except Exception:
            pass
        active_agent = _make_agent(run_agent, runtime, session_id=f"phase25-{scenario.name}-reset", user_id=user_id)
        active_history = []
        reset_reply = "simulated_programmatic_reset"

    if seed_failures:
        raise RuntimeError("; ".join(seed_failures))

    final_result = active_agent.run_conversation(scenario.final_question, conversation_history=active_history)
    final_messages = list(final_result.get("messages") or [])
    provider = _brainstack_provider(active_agent._memory_manager)
    prefetch_debug = dict(getattr(provider, "_last_prefetch_debug", {}) or {}) if provider is not None else {}
    route_snapshot = _route_snapshot(provider) if provider is not None else {}
    persisted_scope = _persisted_scope_snapshot(provider) if provider is not None else {}
    tier2_batch_result = dict(getattr(provider, "_last_tier2_batch_result", {}) or {}) if provider is not None else {}
    selected_counts = _summarize_selected_rows(prefetch_debug)
    answer = str(final_result.get("final_response") or "")
    evaluation = _evaluate_answer(scenario, answer)

    try:
        active_agent.shutdown_memory_provider(final_messages)
    except Exception:
        pass

    return {
        "name": scenario.name,
        "category": scenario.category,
        "use_reset": scenario.use_reset,
        "seed_messages": list(scenario.seed_messages),
        "seed_replies": seed_replies,
        "reset_reply": reset_reply,
        "final_question": scenario.final_question,
        "answer": answer,
        "expected": scenario.expected,
        "passed": evaluation["passed"],
        "quality_class": evaluation["quality_class"],
        "missing": evaluation.get("missing", []),
        "packet": {
            "available": bool(prefetch_debug),
            "selected_row_counts": selected_counts,
            "route": route_snapshot,
            "last_prompt_tokens": int(final_result.get("last_prompt_tokens") or 0),
            "input_tokens": int(final_result.get("input_tokens") or 0),
            "output_tokens": int(final_result.get("output_tokens") or 0),
        },
        "tier2_batch_result": tier2_batch_result,
        "persisted_scope": persisted_scope,
    }


def _classify_residuals(results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    residuals: List[Dict[str, Any]] = []
    for result in results:
        if result.get("passed"):
            packet = dict(result.get("packet") or {})
            if not packet.get("available"):
                residuals.append(
                    {
                        "scenario": result["name"],
                        "classification": "acceptable_residual",
                        "reason": "answer passed but packet debug was unavailable for this turn",
                    }
                )
            continue

        answer = str(result.get("answer") or "")
        error_text = str(result.get("error") or "")
        combined = _normalize_text(f"{answer} {error_text}")
        if any(marker in combined for marker in ("rate limit", "usage limit", "timeout", "service unavailable", "connection reset")):
            classification = "provider_variance"
        elif any(marker in combined for marker in ("docker cp failed", "missing runtime setting", "traceback", "stage")):
            classification = "harness_issue"
        else:
            classification = "product_bug"
        residuals.append(
            {
                "scenario": result["name"],
                "classification": classification,
                "reason": ", ".join(result.get("missing") or []) or (error_text or "failed deterministic quality check"),
            }
        )

    scoped_profile_keys = {
        "preference:emoji_usage",
        "preference:communication_style",
        "preference:ai_name",
        "identity:name",
        "preference:response_language",
    }
    bleed_scenarios = []
    for result in results:
        if str(result.get("name") or "") == "style_identity_after_reset":
            continue
        scope = dict(result.get("persisted_scope") or {})
        keys = {str(item) for item in list(scope.get("profile_stable_keys") or [])}
        if keys & scoped_profile_keys:
            bleed_scenarios.append(str(result.get("name") or ""))
    if bleed_scenarios:
        residuals.append(
            {
                "scenario": "cross_principal_profile_bleed",
                "classification": "product_bug",
                "reason": "style/name/language profile items appeared under unrelated principals",
                "evidence": bleed_scenarios,
            }
        )
    return residuals


def _packet_overhead(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    packet_results = [item for item in results if bool(dict(item.get("packet") or {}).get("available"))]
    if not packet_results:
        return {"scenario_count_with_packet": 0}

    def _avg(values: Iterable[int]) -> float:
        data = [int(value) for value in values]
        return round(sum(data) / len(data), 2) if data else 0.0

    return {
        "scenario_count_with_packet": len(packet_results),
        "avg_selected_row_count": _avg(
            dict(item.get("packet") or {}).get("selected_row_counts", {}).get("total_selected_rows", 0)
            for item in packet_results
        ),
        "avg_transcript_rows": _avg(
            dict(item.get("packet") or {}).get("selected_row_counts", {}).get("transcript_rows", 0)
            for item in packet_results
        ),
        "avg_graph_rows": _avg(
            dict(item.get("packet") or {}).get("selected_row_counts", {}).get("graph_rows", 0)
            for item in packet_results
        ),
        "avg_corpus_rows": _avg(
            dict(item.get("packet") or {}).get("selected_row_counts", {}).get("corpus_rows", 0)
            for item in packet_results
        ),
        "avg_prompt_tokens": _avg(int(dict(item.get("packet") or {}).get("last_prompt_tokens", 0)) for item in packet_results),
    }


def _compare_with_baseline(
    results: Sequence[Dict[str, Any]],
    residuals: Sequence[Dict[str, Any]],
    baseline_report: Dict[str, Any],
    *,
    baseline_label: str,
) -> Dict[str, Any]:
    baseline_results = {
        str(item.get("name") or ""): item
        for item in list(baseline_report.get("results") or [])
        if isinstance(item, dict)
    }
    current_accuracy = round(sum(1 for item in results if item.get("passed")) / len(results), 4) if results else 0.0
    current_pass_count = sum(1 for item in results if item.get("passed"))
    scenario_deltas: List[Dict[str, Any]] = []
    for item in results:
        scenario_name = str(item.get("name") or "")
        baseline_item = baseline_results.get(scenario_name)
        if not baseline_item:
            continue
        baseline_passed = bool(baseline_item.get("passed"))
        current_passed = bool(item.get("passed"))
        baseline_quality = str(baseline_item.get("quality_class") or "")
        current_quality = str(item.get("quality_class") or "")
        if baseline_passed != current_passed or baseline_quality != current_quality:
            scenario_deltas.append(
                {
                    "scenario": scenario_name,
                    "baseline_passed": baseline_passed,
                    "current_passed": current_passed,
                    "baseline_quality_class": baseline_quality,
                    "current_quality_class": current_quality,
                }
            )

    baseline_residual_names = {
        str(item.get("scenario") or "")
        for item in list(baseline_report.get("residuals") or [])
        if isinstance(item, dict)
    }
    current_residual_names = {
        str(item.get("scenario") or "")
        for item in residuals
        if isinstance(item, dict)
    }

    baseline_accuracy = float(baseline_report.get("accuracy") or 0.0)
    return {
        "baseline_report": baseline_label,
        "baseline_accuracy": baseline_accuracy,
        "current_accuracy": current_accuracy,
        "accuracy_delta": round(current_accuracy - baseline_accuracy, 4),
        "baseline_pass_count": int(baseline_report.get("pass_count") or 0),
        "current_pass_count": current_pass_count,
        "resolved_residuals": sorted(baseline_residual_names - current_residual_names),
        "persisting_residuals": sorted(baseline_residual_names & current_residual_names),
        "new_residuals": sorted(current_residual_names - baseline_residual_names),
        "scenario_deltas": scenario_deltas,
    }


def _write_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-root", type=Path, default=DEFAULT_BESTIE_ROOT)
    parser.add_argument("--deployed-home", type=Path, default=None)
    parser.add_argument("--docker-container", default=DEFAULT_DOCKER_CONTAINER)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--matrix-output", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--baseline-report", type=Path, default=DEFAULT_PHASE23_BASELINE)
    args = parser.parse_args()

    if args.hermes_root is None:
        raise SystemExit("--hermes-root is required (or set BRAINSTACK_BESTIE_ROOT / BRAINSTACK_HERMES_ROOT / HERMES_ROOT).")

    baseline_report = json.loads(args.baseline_report.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="brainstack-phase25-home-") as tmp_dir:
        temp_home = Path(tmp_dir)
        _stage_deployed_subset(
            source_home=args.deployed_home,
            docker_container=None if args.deployed_home else args.docker_container,
            temp_home=temp_home,
        )
        os.environ["HERMES_HOME"] = str(temp_home)
        runtime = _extract_runtime_settings(temp_home, args.hermes_root)
        missing_runtime = [key for key in ("provider", "model", "api_key") if not runtime.get(key)]
        if missing_runtime:
            raise RuntimeError(f"Missing runtime setting(s): {', '.join(missing_runtime)}")

        scenario_matrix = [
            {
                "name": scenario.name,
                "category": scenario.category,
                "use_reset": scenario.use_reset,
                "seed_messages": list(scenario.seed_messages),
                "final_question": scenario.final_question,
                "expected": scenario.expected,
            }
            for scenario in SCENARIOS
        ]
        _write_json(args.matrix_output, scenario_matrix)

        results: List[Dict[str, Any]] = []
        for scenario in SCENARIOS:
            try:
                results.append(_run_single_scenario(args.hermes_root, temp_home, runtime, scenario))
            except Exception as exc:
                results.append(
                    {
                        "name": scenario.name,
                        "category": scenario.category,
                        "use_reset": scenario.use_reset,
                        "seed_messages": list(scenario.seed_messages),
                        "final_question": scenario.final_question,
                        "expected": scenario.expected,
                        "passed": False,
                        "quality_class": "error",
                        "missing": [],
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                        "packet": {"available": False},
                    }
                )

        by_category: Dict[str, Dict[str, int]] = {}
        for result in results:
            category = str(result["category"])
            bucket = by_category.setdefault(category, {"total": 0, "passed": 0, "strong_pass": 0, "acceptable_pass": 0})
            bucket["total"] += 1
            if result.get("passed"):
                bucket["passed"] += 1
            quality = str(result.get("quality_class") or "")
            if quality in bucket:
                bucket[quality] += 1

        residuals = _classify_residuals(results)
        try:
            baseline_label = str(args.baseline_report.relative_to(REPO_ROOT))
        except ValueError:
            baseline_label = args.baseline_report.name
        baseline_comparison = _compare_with_baseline(
            results,
            residuals,
            baseline_report,
            baseline_label=baseline_label,
        )
        report = {
            "type": "brainstack_phase25_broader_deployed_live_eval",
            "scenario_count": len(results),
            "pass_count": sum(1 for item in results if item.get("passed")),
            "accuracy": round(sum(1 for item in results if item.get("passed")) / len(results), 4) if results else 0.0,
            "by_category": by_category,
            "packet_overhead": _packet_overhead(results),
            "baseline_comparison": baseline_comparison,
            "residuals": residuals,
            "results": results,
        }
        _write_json(args.output, report)
        print(json.dumps({"report": str(args.output), "matrix": str(args.matrix_output), "scenario_count": len(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
