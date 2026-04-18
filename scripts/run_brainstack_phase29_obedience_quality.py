#!/usr/bin/env python3
"""Phase 29 answer-level obedience harness for deployed Brainstack behavior policy.

This script exercises ordinary replies through the real Hermes + Brainstack path
while isolating memory writes inside a temporary HERMES_HOME. Unlike the earlier
live-quality scripts, the primary gate here is behavior-policy obedience on the
final assistant answer, not packet-only success.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _env_path(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return Path(value).expanduser()
    return None


DEFAULT_HERMES_ROOT = _env_path("BRAINSTACK_HERMES_ROOT", "HERMES_ROOT")
DEFAULT_REPORT = REPO_ROOT / "reports" / "phase29" / "brainstack-29-behavior-obedience-live-eval.json"
DEFAULT_MATRIX = REPO_ROOT / "reports" / "phase29" / "brainstack-29-behavior-obedience-scenarios.json"
DEFAULT_DOCKER_CONTAINER = os.environ.get("BRAINSTACK_DOCKER_CONTAINER", "").strip() or None
STYLE_CONTRACT_DEFAULT_TITLE = "User style contract"

_HUNGARIAN_MARKERS = (
    " szia ",
    " szervusz ",
    " helló ",
    " hello ",
    " vagy ",
    " vagyok",
    " most ",
    " neked",
    " nekem",
    " segítek",
    " rendben",
    " itt ",
    " ma ",
    " és ",
    " hogy ",
    " nem ",
    " rövid",
    " tip",
    " javaslat",
    " pihen",
)
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
_DASH_PUNCTUATION_RE = re.compile(r"[—–]|(^|\s)-(?=\s|\S)")
_BOLDFACE_RE = re.compile(r"\*\*.+?\*\*")

_RULE_PACK = f"""{STYLE_CONTRACT_DEFAULT_TITLE}

Tartalmi minták:
- Konkrét tények, nem jelentőségfelfújás.
- Egy konkrét forrás, nem homályos hivatkozások.

Nyelvi minták:
- Mindig magyarul válaszolj.
- Ne használj emojikat.
- Ne használj dash írásjelet a válaszaidban.
- Minden új gondolat külön sorba kerüljön.
- Boldface csak kivételesen, ne alapból.

Kommunikációs minták:
- Köszönésre ne válts át generikus follow-up kérdésre.
- A megadott asszisztensnéven hivatkozz magadra, ha megnevezed magad.
- Maradj direkt, természetes, alacsony-fluff hangnemben.
"""


def _install_fire_shim() -> None:
    shim = types.ModuleType("fire")

    def _noop_fire(*_args: Any, **_kwargs: Any) -> None:
        return None

    shim.Fire = _noop_fire  # type: ignore[attr-defined]
    sys.modules.setdefault("fire", shim)


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("—", "-").replace("–", "-")
    return " ".join(text.split())


def _contains_any(answer: str, options: Sequence[str]) -> bool:
    normalized = _normalize_text(answer)
    return any(_normalize_text(option) in normalized for option in options)


def _has_emoji(answer: str) -> bool:
    return bool(_EMOJI_RE.search(str(answer or "")))


def _has_dash_punctuation(answer: str) -> bool:
    text = str(answer or "")
    if "—" in text or "–" in text:
        return True
    return bool(re.search(r"(?:^|[^\w])-(?:[^\w]|$)", text))


def _has_boldface(answer: str) -> bool:
    return bool(_BOLDFACE_RE.search(str(answer or "")))


def _is_hungarianish(answer: str) -> bool:
    text = str(answer or "")
    normalized = f" {_normalize_text(text)} "
    if any(ch in text for ch in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ"):
        return True
    if normalized.strip(" !?.") in {"szia", "szervusz", "helló", "hello"}:
        return True
    hits = sum(1 for token in _HUNGARIAN_MARKERS if token in normalized)
    return hits >= 2


def _has_question_mark(answer: str) -> bool:
    return "?" in str(answer or "")


def _has_multiline_structure(answer: str) -> bool:
    return "\n" in str(answer or "").strip()


def _summarize_selected_rows(prefetch_debug: Dict[str, Any] | None) -> Dict[str, int]:
    payload = dict(prefetch_debug or {})
    selected = payload.get("selected_rows")
    if not isinstance(selected, dict):
        return {"total_selected_rows": 0}
    total = 0
    counts: Dict[str, int] = {}
    for key, rows in selected.items():
        count = len(rows) if isinstance(rows, list) else 0
        counts[f"{key}_rows"] = count
        total += count
    counts["total_selected_rows"] = total
    return counts


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


def _extract_runtime_settings(home: Path, hermes_root: Path) -> Dict[str, Any]:
    import yaml  # type: ignore[import-untyped]

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
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
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
    completed = subprocess.run(
        ["docker", "cp", f"{container}:{remote_path}", str(local_path)],
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return
    if optional and "No such container:path" in (completed.stderr or ""):
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
        name="startup_smalltalk_after_reset",
        category="behavior_policy_obedience_after_reset",
        use_reset=True,
        seed_messages=(_RULE_PACK,),
        final_question="Szia!",
        evaluator="startup_smalltalk",
        expected="Hungarian answer, no emoji, no dash punctuation, no generic follow-up question",
    ),
    Scenario(
        name="ordinary_help_after_reset",
        category="behavior_policy_obedience_after_reset",
        use_reset=True,
        seed_messages=(_RULE_PACK,),
        final_question="Adj két rövid tippet a mai délutánra, fáradt vagyok.",
        evaluator="ordinary_help",
        expected="Hungarian, compact, no emoji, no dash punctuation, multiline or clearly separated tips",
    ),
    Scenario(
        name="ordinary_help_same_session",
        category="behavior_policy_immediate_activation",
        use_reset=False,
        seed_messages=(_RULE_PACK,),
        final_question="Adj két rövid tippet a mai délutánra, fáradt vagyok.",
        evaluator="ordinary_help",
        expected="same-session answer already obeys the active behavior policy",
    ),
]


def _evaluate_answer(scenario: Scenario, answer: str) -> Dict[str, Any]:
    missing: List[str] = []
    strong = False

    if not _is_hungarianish(answer):
        missing.append("hungarianish_answer")
    if _has_emoji(answer):
        missing.append("no_emoji")
    if _has_dash_punctuation(answer):
        missing.append("no_dash_punctuation")
    if _has_boldface(answer):
        missing.append("no_default_boldface")

    if scenario.evaluator == "startup_smalltalk":
        if _has_question_mark(answer):
            missing.append("no_generic_followup_question")
        strong = not missing and not _has_question_mark(answer)
    elif scenario.evaluator == "ordinary_help":
        if not _has_multiline_structure(answer):
            missing.append("multiline_structure")
        strong = not missing
    else:
        raise ValueError(f"Unknown evaluator: {scenario.evaluator}")

    passed = not missing
    quality_class = "strong_pass" if strong else ("acceptable_pass" if passed else "miss")
    return {"passed": passed, "quality_class": quality_class, "missing": missing}


def _load_run_agent(hermes_root: Path) -> Any:
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    try:
        import run_agent  # type: ignore
    except ModuleNotFoundError as exc:
        if exc.name != "fire":
            raise
        _install_fire_shim()
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


def _best_effort_snapshot(callable_obj: Any, *, default: Any) -> tuple[Any, str | None]:
    try:
        return callable_obj(), None
    except Exception as exc:  # pragma: no cover - diagnostic surface only
        return default, f"{type(exc).__name__}: {exc}"


def _best_effort_shutdown(agent: Any, messages: Sequence[Dict[str, Any]]) -> str | None:
    try:
        agent.shutdown_memory_provider(list(messages))
    except Exception as exc:  # pragma: no cover - diagnostic surface only
        return f"{type(exc).__name__}: {exc}"
    return None


def _persisted_scope_snapshot(provider: Any) -> Dict[str, Any]:
    store = getattr(provider, "_store", None)
    principal_scope_key = str(getattr(provider, "_principal_scope_key", "") or "").strip()
    if store is None or not principal_scope_key:
        return {"principal_scope_key": principal_scope_key}
    profile_items, profile_error = _best_effort_snapshot(
        lambda: store.list_profile_items(limit=20, principal_scope_key=principal_scope_key),
        default=[],
    )
    current_states, state_error = _best_effort_snapshot(
        lambda: store.list_current_graph_states(limit=20, principal_scope_key=principal_scope_key),
        default=[],
    )
    compiled, compiled_error = _best_effort_snapshot(
        lambda: store.get_compiled_behavior_policy(principal_scope_key=principal_scope_key),
        default=None,
    )
    return {
        "principal_scope_key": principal_scope_key,
        "profile_item_count": len(profile_items),
        "profile_stable_keys": [str(item.get("stable_key") or "") for item in profile_items],
        "current_state_count": len(current_states),
        "compiled_policy_active": bool(compiled and compiled.get("policy")),
        "compiled_policy_hash": str(dict(compiled or {}).get("policy", {}).get("policy_hash") or ""),
        "snapshot_errors": [error for error in (profile_error, state_error, compiled_error) if error],
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


def _scenario_prompt_snapshot(agent: Any, provider: Any) -> Dict[str, Any]:
    cached_system_prompt = str(getattr(agent, "_cached_system_prompt", "") or "")
    system_block = provider.system_prompt_block() if provider is not None else ""
    return {
        "cached_system_has_behavior_contract": "# Brainstack Active Communication Contract" in cached_system_prompt,
        "cached_system_has_title": STYLE_CONTRACT_DEFAULT_TITLE in cached_system_prompt,
        "cached_system_has_raw_section_header": "Tartalmi minták:" in cached_system_prompt,
        "provider_system_has_behavior_contract": "# Brainstack Active Communication Contract" in system_block,
        "provider_system_has_title": STYLE_CONTRACT_DEFAULT_TITLE in system_block,
        "provider_system_has_raw_section_header": "Tartalmi minták:" in system_block,
    }


def _run_single_scenario(hermes_root: Path, temp_home: Path, runtime: Dict[str, str], scenario: Scenario) -> Dict[str, Any]:
    os.environ["HERMES_HOME"] = str(temp_home)
    run_agent = _load_run_agent(hermes_root)
    user_id = f"phase29:{scenario.name}"

    seed_agent = _make_agent(run_agent, runtime, session_id=f"phase29-{scenario.name}-seed", user_id=user_id)
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

    active_agent = seed_agent
    active_history = history
    reset_reply = None
    shutdown_errors: List[str] = []
    if scenario.use_reset and not seed_failures:
        shutdown_error = _best_effort_shutdown(seed_agent, history)
        if shutdown_error:
            shutdown_errors.append(shutdown_error)
        active_agent = _make_agent(run_agent, runtime, session_id=f"phase29-{scenario.name}-reset", user_id=user_id)
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
    prompt_snapshot = _scenario_prompt_snapshot(active_agent, provider) if provider is not None else {}
    tier2_batch_result = dict(getattr(provider, "_last_tier2_batch_result", {}) or {}) if provider is not None else {}
    selected_counts = _summarize_selected_rows(prefetch_debug)
    answer = str(final_result.get("final_response") or "")
    evaluation = _evaluate_answer(scenario, answer)

    shutdown_error = _best_effort_shutdown(active_agent, final_messages)
    if shutdown_error:
        shutdown_errors.append(shutdown_error)

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
        "prompt_snapshot": prompt_snapshot,
        "tier2_batch_result": tier2_batch_result,
        "persisted_scope": persisted_scope,
        "shutdown_errors": shutdown_errors,
    }


def _classify_residuals(results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    residuals: List[Dict[str, Any]] = []
    for result in results:
        if result.get("passed"):
            continue

        answer = str(result.get("answer") or "")
        error_text = str(result.get("error") or "")
        combined = _normalize_text(f"{answer} {error_text}")
        if any(marker in combined for marker in ("rate limit", "usage limit", "timeout", "service unavailable", "connection reset")):
            classification = "provider_variance"
        elif any(
            marker in combined
            for marker in ("docker cp failed", "missing runtime setting", "traceback", "stage", "modulenotfounderror")
        ):
            classification = "harness_issue"
        else:
            classification = "product_bug"
        residuals.append(
            {
                "scenario": result["name"],
                "classification": classification,
                "reason": ", ".join(result.get("missing") or []) or (error_text or "failed obedience check"),
            }
        )

    bleed_scenarios = []
    for result in results:
        scope = dict(result.get("persisted_scope") or {})
        if scope.get("compiled_policy_active"):
            continue
        bleed_scenarios.append(str(result.get("name") or ""))
    if bleed_scenarios:
        residuals.append(
            {
                "scenario": "compiled_policy_missing_after_teach",
                "classification": "product_bug",
                "reason": "behavior policy was not active after teaching in one or more scenarios",
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
        "avg_prompt_tokens": _avg(int(dict(item.get("packet") or {}).get("last_prompt_tokens", 0)) for item in packet_results),
    }


def _write_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-root", type=Path, default=DEFAULT_HERMES_ROOT)
    parser.add_argument("--deployed-home", type=Path, default=None)
    parser.add_argument("--docker-container", default=DEFAULT_DOCKER_CONTAINER)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--matrix-output", type=Path, default=DEFAULT_MATRIX)
    args = parser.parse_args()

    if args.hermes_root is None:
        raise SystemExit("--hermes-root is required (or set BRAINSTACK_HERMES_ROOT / HERMES_ROOT).")

    with tempfile.TemporaryDirectory(prefix="brainstack-phase29-home-") as tmp_dir:
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
        report = {
            "type": "brainstack_phase29_behavior_obedience_live_eval",
            "scenario_count": len(results),
            "pass_count": sum(1 for item in results if item.get("passed")),
            "accuracy": round(sum(1 for item in results if item.get("passed")) / len(results), 4) if results else 0.0,
            "by_category": by_category,
            "packet_overhead": _packet_overhead(results),
            "residuals": residuals,
            "results": results,
        }
        _write_json(args.output, report)
        print(json.dumps({"report": str(args.output), "matrix": str(args.matrix_output), "scenario_count": len(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
