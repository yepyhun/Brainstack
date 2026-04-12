#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import re
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from typing import Any, Dict, Iterable, List, Tuple
from unittest.mock import patch

import openai
import yaml


DEFAULT_HERMES_ROOT = Path("/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest")
DEFAULT_CORE2_ROOT = Path("/home/lauratom/Asztal/ai/hermes-agent-core2")
DEFAULT_REPORT_PATH = Path("/home/lauratom/Asztal/ai/atado/Brainstack/reports/longmemeval/brainstack-subset-latest.json")

_YES_NO_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _prepend_sys_path(path: Path) -> str | None:
    path_str = str(path)
    if path_str in sys.path:
        return None
    sys.path.insert(0, path_str)
    return path_str


def _purge_module_prefixes(*prefixes: str) -> None:
    to_delete = []
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            to_delete.append(name)
    for name in to_delete:
        sys.modules.pop(name, None)


def _normalize_answer_text(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def _normalize_judge_text(*parts: str) -> str:
    text = " ".join(str(part or "").strip() for part in parts if str(part or "").strip())
    compact = " ".join(text.split())
    if not compact:
        return ""
    match = _YES_NO_RE.search(compact)
    return str(match.group(1) or "").lower() if match else ""


def _judge_yes_no(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int = 256,
    max_attempts: int = 3,
) -> str:
    client = openai.OpenAI(base_url=base_url, api_key=api_key)
    system_prompts = [
        "Reply with exactly one word: yes or no.",
        "Return only one lowercase word: yes or no. No punctuation. No explanation.",
        "Judge correctness. Output exactly yes or exactly no.",
    ]
    last_raw = ""
    try:
        for attempt in range(max(1, max_attempts)):
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompts[min(attempt, len(system_prompts) - 1)]},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0,
            )
            text = ""
            if response.choices:
                text = str(response.choices[0].message.content or "")
            last_raw = text
            normalized = _normalize_judge_text(text)
            if normalized in {"yes", "no"}:
                return normalized
    finally:
        client.close()
    return _normalize_judge_text(last_raw) or "unknown"


def _iter_entry_sessions(entry: Dict[str, Any], *, oracle_only: bool) -> Iterable[Tuple[int, str, str, List[Dict[str, Any]]]]:
    sessions = list(entry.get("haystack_sessions") or [])
    dates = list(entry.get("haystack_dates") or [])
    ids = list(entry.get("haystack_session_ids") or [])
    oracle_ids = {str(value) for value in list(entry.get("answer_session_ids") or [])}
    for idx, session in enumerate(sessions):
        session_id = str(ids[idx]) if idx < len(ids) else f"s{idx}"
        if oracle_only and oracle_ids and session_id not in oracle_ids:
            continue
        session_date = str(dates[idx]) if idx < len(dates) else ""
        if not isinstance(session, list):
            continue
        yield idx, session_id, session_date, session


def _iter_session_exchange_pairs(session: List[Dict[str, Any]]) -> Iterable[Tuple[str, str]]:
    pending_user = ""
    for item in session:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "")
        if role == "user":
            if pending_user:
                yield pending_user, ""
            pending_user = content
        elif role == "assistant":
            if pending_user:
                yield pending_user, content
                pending_user = ""
            else:
                yield "", content
    if pending_user:
        yield pending_user, ""


def _build_config(home: Path) -> Dict[str, Any]:
    return {
        "model": "benchmark-placeholder",
        "providers": {},
        "toolsets": [],
        "agent": {"max_turns": 4},
        "memory": {
            "provider": "brainstack",
            "memory_enabled": False,
            "user_profile_enabled": False,
        },
        "plugins": {
            "brainstack": {
                "db_path": str(home / "brainstack" / "brainstack.db"),
                "graph_backend": "kuzu",
                "corpus_backend": "chroma",
                "tier2_timeout_seconds": 60,
                "tier2_max_tokens": 400,
            }
        },
    }


def _build_direct_tier2_extractor(*, model: str, base_url: str, api_key: str):
    from plugins.memory.brainstack.tier2_extractor import extract_tier2_candidates

    client = openai.OpenAI(base_url=base_url, api_key=api_key)

    def _llm_caller(*, task: str, messages: list, timeout: float, max_tokens: int):
        del task
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=min(int(max_tokens), 400),
            timeout=max(float(timeout), 60.0),
        )

    def _extractor(transcript_entries, *, session_id: str, turn_number: int, trigger_reason: str):
        del session_id, turn_number, trigger_reason
        return extract_tier2_candidates(
            transcript_entries,
            llm_caller=_llm_caller,
        )

    return _extractor, client


def _seed_brainstack_kernel(
    hermes_root: Path,
    home: Path,
    entry: Dict[str, Any],
    *,
    oracle_only: bool,
    model: str,
    base_url: str,
    api_key: str,
) -> Dict[str, int]:
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    from plugins.memory import load_memory_provider

    provider = load_memory_provider("brainstack")
    if provider is None:
        raise RuntimeError("Brainstack memory provider is unavailable in target Hermes checkout.")
    session_id = f"seed-{entry.get('question_id')}"
    provider.initialize(session_id, hermes_home=str(home), platform="cli")
    direct_tier2_extractor, direct_tier2_client = _build_direct_tier2_extractor(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
    if hasattr(provider, "_config") and isinstance(getattr(provider, "_config"), dict):
        provider._config["_tier2_extractor"] = direct_tier2_extractor
    if hasattr(provider, "_tier2_batch_turn_limit"):
        provider._tier2_batch_turn_limit = 1000000
    if hasattr(provider, "_tier2_idle_window_seconds"):
        provider._tier2_idle_window_seconds = 1000000
    if hasattr(provider, "_tier2_timeout_seconds"):
        provider._tier2_timeout_seconds = 60.0
    if hasattr(provider, "_tier2_max_tokens"):
        provider._tier2_max_tokens = 400

    total_sessions = 0
    total_turns = 0
    messages: List[Dict[str, Any]] = []
    try:
        benchmark_session_id = f"longmemeval:{entry.get('question_id')}:seed"
        for idx, upstream_session_id, session_date, session in _iter_entry_sessions(entry, oracle_only=oracle_only):
            total_sessions += 1
            for user_message, assistant_response in _iter_session_exchange_pairs(session):
                if user_message:
                    messages.append({"role": "user", "content": user_message})
                if assistant_response:
                    messages.append({"role": "assistant", "content": assistant_response})
                provider.sync_turn(
                    user_message,
                    assistant_response,
                    session_id=benchmark_session_id,
                    event_time=session_date or None,
                )
                total_turns += 1
        if total_turns and hasattr(provider, "_run_tier2_batch"):
            provider._run_tier2_batch(
                session_id=benchmark_session_id,
                turn_number=getattr(provider, "_turn_counter", 0),
                trigger_reason="benchmark_seed_flush",
            )
            if hasattr(provider, "_pending_tier2_turns"):
                provider._pending_tier2_turns = 0
        provider.on_session_end(messages)
    finally:
        try:
            direct_tier2_client.close()
        except Exception:
            pass
        try:
            provider.shutdown()
        except Exception:
            pass
    return {"seeded_sessions": total_sessions, "seeded_turns": total_turns}


def _run_brainstack_generation(
    *,
    hermes_root: Path,
    donor_module: ModuleType,
    entry: Dict[str, Any],
    model: str,
    base_url: str,
    api_key: str,
    provider: str,
    judge_model: str,
    oracle_seed: bool,
    max_iterations: int,
) -> Dict[str, Any]:
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    import run_agent
    from agent.memory_manager import MemoryManager

    with TemporaryDirectory(prefix="brainstack-longmemeval-") as tmp_dir:
        total_started = time.perf_counter()
        home = Path(tmp_dir)
        (home / "brainstack").mkdir(parents=True, exist_ok=True)
        config = _build_config(home)
        (home / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        auxiliary_env = {
            "AUXILIARY_FLUSH_MEMORIES_BASE_URL": base_url,
            "AUXILIARY_FLUSH_MEMORIES_API_KEY": api_key,
            "AUXILIARY_FLUSH_MEMORIES_PROVIDER": "custom",
            "AUXILIARY_FLUSH_MEMORIES_MODEL": model,
            "CONTEXT_FLUSH_MEMORIES_BASE_URL": base_url,
            "CONTEXT_FLUSH_MEMORIES_API_KEY": api_key,
            "CONTEXT_FLUSH_MEMORIES_PROVIDER": "custom",
            "CONTEXT_FLUSH_MEMORIES_MODEL": model,
        }

        seed_started = time.perf_counter()
        with patch.dict(os.environ, auxiliary_env, clear=False):
            seed_counts = _seed_brainstack_kernel(
                hermes_root,
                home,
                entry,
                oracle_only=oracle_seed,
                model=model,
                base_url=base_url,
                api_key=api_key,
            )
        seed_seconds = time.perf_counter() - seed_started

        captured: Dict[str, Any] = {}
        api_seconds = 0.0
        tool_seconds = 0.0
        tool_events: List[Dict[str, Any]] = []

        original_interruptible = run_agent.AIAgent._interruptible_api_call
        original_streaming = getattr(run_agent.AIAgent, "_interruptible_streaming_api_call", None)
        original_memory_handle = MemoryManager.handle_tool_call

        def _capture_then_call(agent_self, api_kwargs: Dict[str, Any]):
            nonlocal api_seconds
            messages = list(api_kwargs.get("messages") or [])
            captured["prompt"] = "\n\n".join(str(message.get("content") or "") for message in messages)
            started = time.perf_counter()
            try:
                return original_interruptible(agent_self, api_kwargs)
            finally:
                api_seconds += time.perf_counter() - started

        def _capture_then_stream(agent_self, api_kwargs: Dict[str, Any], on_first_delta=None):
            nonlocal api_seconds
            messages = list(api_kwargs.get("messages") or [])
            captured["prompt"] = "\n\n".join(str(message.get("content") or "") for message in messages)
            started = time.perf_counter()
            try:
                return original_streaming(agent_self, api_kwargs, on_first_delta=on_first_delta)
            finally:
                api_seconds += time.perf_counter() - started

        def _timed_memory_tool(self, tool_name: str, args: Dict[str, Any], **kwargs):
            nonlocal tool_seconds
            started = time.perf_counter()
            result = original_memory_handle(self, tool_name, args, **kwargs)
            duration = time.perf_counter() - started
            tool_seconds += duration
            tool_events.append(
                {
                    "tool_name": tool_name,
                    "duration_seconds": round(duration, 6),
                }
            )
            return result

        patchers = [
            patch.dict(os.environ, {"HERMES_HOME": str(home)}),
            patch("run_agent._hermes_home", home),
            patch("run_agent.get_tool_definitions", return_value=[]),
            patch("run_agent.check_toolset_requirements", return_value={}),
            patch("hermes_cli.config.load_config", return_value=config),
            patch.object(run_agent.AIAgent, "_interruptible_api_call", _capture_then_call),
            patch.object(MemoryManager, "handle_tool_call", _timed_memory_tool),
        ]
        patchers.append(patch.dict(os.environ, auxiliary_env, clear=False))
        if original_streaming is not None:
            patchers.append(patch.object(run_agent.AIAgent, "_interruptible_streaming_api_call", _capture_then_stream))

        with ExitStack() as stack:
            for patcher in patchers:
                stack.enter_context(patcher)
            agent = run_agent.AIAgent(
                api_key=api_key,
                model=model,
                provider=provider,
                base_url=base_url,
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=False,
                session_id=f"brainstack-longmemeval-{entry['question_id']}",
                persist_session=False,
                max_iterations=max_iterations,
            )
            agent._cleanup_task_resources = lambda task_id: None
            agent._persist_session = lambda messages, history=None: None
            agent._save_trajectory = lambda messages, user_message, completed: None
            agent._save_session_log = lambda messages: None
            conversation_started = time.perf_counter()
            raw_result = agent.run_conversation(str(entry["question"]))
            conversation_seconds = time.perf_counter() - conversation_started
            result = dict(raw_result) if isinstance(raw_result, dict) else {"final_response": str(raw_result or "")}
            try:
                agent._memory_manager.shutdown_all()
            except Exception:
                pass

        hypothesis = str(result.get("final_response") or "").strip()
        answer = str(entry.get("answer") or "")
        if _normalize_answer_text(hypothesis) == _normalize_answer_text(answer):
            judge = "yes_exact_match"
            judge_seconds = 0.0
        elif _normalize_answer_text(answer) and _normalize_answer_text(answer) in _normalize_answer_text(hypothesis):
            judge = "yes_answer_contained"
            judge_seconds = 0.0
        else:
            judge_started = time.perf_counter()
            judge = _judge_yes_no(
                base_url=base_url,
                api_key=api_key,
                model=judge_model,
                prompt=donor_module.get_anscheck_prompt(
                    str(entry.get("question_type") or ""),
                    str(entry.get("question") or ""),
                    answer,
                    hypothesis,
                    abstention="_abs" in str(entry.get("question_id") or ""),
                ),
            )
            judge_seconds = time.perf_counter() - judge_started

        return {
            "question_id": str(entry.get("question_id") or ""),
            "question_type": str(entry.get("question_type") or ""),
            "question": str(entry.get("question") or ""),
            "answer": answer,
            "hypothesis": hypothesis,
            "judge": judge,
            "passed": str(judge).startswith("yes"),
            "provider": provider,
            "model": model,
            "seeded_sessions": seed_counts["seeded_sessions"],
            "seeded_turns": seed_counts["seeded_turns"],
            "seed_seconds": round(seed_seconds, 3),
            "conversation_seconds": round(conversation_seconds, 3),
            "api_seconds": round(api_seconds, 3),
            "tool_seconds": round(tool_seconds, 3),
            "judge_seconds": round(judge_seconds, 3),
            "total_seconds": round(time.perf_counter() - total_started, 3),
            "tool_events": tool_events,
            "captured_prompt": captured.get("prompt", ""),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Brainstack-backed LongMemEval subset through the real Hermes path.")
    parser.add_argument("--hermes-root", type=Path, default=DEFAULT_HERMES_ROOT)
    parser.add_argument("--core2-root", type=Path, default=DEFAULT_CORE2_ROOT)
    parser.add_argument("--sample-size", type=int, default=15)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--model", type=str, default="")
    parser.add_argument("--base-url", type=str, default="")
    parser.add_argument("--provider", type=str, default="")
    parser.add_argument("--judge-model", type=str, default="")
    parser.add_argument("--api-key", type=str, default="")
    parser.add_argument("--oracle-seed", action="store_true")
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-iterations", type=int, default=4)
    args = parser.parse_args()

    inserted_paths: List[str] = []
    prepended = _prepend_sys_path(args.core2_root)
    if prepended:
        inserted_paths.append(prepended)
    try:
        donor_module = _load_module(
            "brainstack_core2_longmemeval_donor",
            args.core2_root / "agent" / "core2_longmemeval_benchmark.py",
        )
    finally:
        for path_str in reversed(inserted_paths):
            try:
                sys.path.remove(path_str)
            except ValueError:
                pass
        inserted_paths.clear()
        _purge_module_prefixes("agent")
    api_key = str(args.api_key or os.getenv("COMET_API_KEY") or os.getenv("COMETAPI_API_KEY") or "").strip()
    if not api_key:
        parser.error("an API key is required via --api-key or COMET_API_KEY / COMETAPI_API_KEY")

    dataset_path = Path(donor_module.DEFAULT_DATASET)
    entries = json.loads(dataset_path.read_text(encoding="utf-8"))
    question_ids = list(args.question_id or [])
    if question_ids:
        chosen = [entry for entry in entries if str(entry.get("question_id") or "") in set(question_ids)]
    else:
        chooser = getattr(donor_module, "stratified_sample", None)
        chosen = chooser(entries, args.sample_size, seed=args.seed) if callable(chooser) else random.Random(args.seed).sample(entries, args.sample_size)

    model = str(args.model or donor_module.DEFAULT_BENCHMARK_MODEL)
    base_url = str(args.base_url or donor_module.DEFAULT_BENCHMARK_BASE_URL)
    provider = str(args.provider or donor_module.DEFAULT_BENCHMARK_PROVIDER)
    judge_model = str(args.judge_model or getattr(donor_module, "DEFAULT_JUDGE_MODEL", donor_module.DEFAULT_BENCHMARK_MODEL))

    results: List[Dict[str, Any]] = []
    started = time.perf_counter()
    for entry in chosen:
        payload = _run_brainstack_generation(
            hermes_root=args.hermes_root,
            donor_module=donor_module,
            entry=entry,
            model=model,
            base_url=base_url,
            api_key=api_key,
            provider=provider,
            judge_model=judge_model,
            oracle_seed=bool(args.oracle_seed),
            max_iterations=args.max_iterations,
        )
        results.append(payload)
        print(json.dumps(payload, ensure_ascii=False))

    passed = sum(1 for item in results if item["passed"])
    summary = {
        "mode": "brainstack",
        "sample_size": len(results),
        "passed": passed,
        "accuracy": round(passed / len(results), 4) if results else 0.0,
        "provider": provider,
        "model": model,
        "judge_model": judge_model,
        "dataset": str(dataset_path),
        "oracle_seed": bool(args.oracle_seed),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    report = {"summary": summary, "results": results}
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "report_path": str(args.report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
