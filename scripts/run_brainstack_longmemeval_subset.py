#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import re
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Tuple
from unittest.mock import patch

import openai
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HERMES_ROOT = Path("/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest")
DEFAULT_CORE2_ROOT = Path("/home/lauratom/Asztal/ai/hermes-agent-core2")
DEFAULT_REPORT_PATH = Path("/home/lauratom/Asztal/ai/atado/Brainstack/reports/longmemeval/brainstack-subset-latest.json")
FIXED_CANARY_QUESTION_IDS = [
    "c8c3f81d",
    "5d3d2817",
    "e9327a54",
    "gpt4_7f6b06db",
    "6c49646a",
]

_YES_NO_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)
_ROUTE_MODE_RE = re.compile(r"\b(fact|temporal|aggregate)\b", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[0-9A-Za-z]+")
_TIME_COLON_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_TIME_WORD_RE = re.compile(r"\b(\d{1,2})\s*(?:minutes?|mins?)\s*(?:and\s*)?(\d{1,2})\s*(?:seconds?|secs?)\b", re.IGNORECASE)

_ROUTE_FILLER_TOKENS = {"a", "an", "at", "in", "of", "on", "the"}
BENCHMARK_TIER2_TRANSCRIPT_LIMIT = 192
BENCHMARK_TIER2_FLUSH_TURN_INTERVAL = 96


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_payload_files(root: Path) -> List[Path]:
    files: List[Path] = []
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
            files.append(path)
    return files


def _verify_runtime_sync(hermes_root: Path) -> Dict[str, Any]:
    source_plugin = REPO_ROOT / "brainstack"
    target_plugin = hermes_root / "plugins" / "memory" / "brainstack"
    source_rtk = REPO_ROOT / "rtk_sidecar.py"
    target_rtk = hermes_root / "agent" / "rtk_sidecar.py"
    source_host_payload = REPO_ROOT / "host_payload"
    mismatches: List[Dict[str, Any]] = []
    compared_files = 0

    for src_file in _iter_payload_files(source_plugin):
        rel = src_file.relative_to(source_plugin)
        dst_file = target_plugin / rel
        compared_files += 1
        if not dst_file.exists():
            mismatches.append(
                {
                    "reason": "missing_target",
                    "source": str(src_file.relative_to(REPO_ROOT)),
                    "target": str(dst_file),
                }
            )
            continue
        src_hash = _hash_file(src_file)
        dst_hash = _hash_file(dst_file)
        if src_hash != dst_hash:
            mismatches.append(
                {
                    "reason": "hash_mismatch",
                    "source": str(src_file.relative_to(REPO_ROOT)),
                    "target": str(dst_file),
                    "source_sha256": src_hash,
                    "target_sha256": dst_hash,
                }
            )

    if source_rtk.exists():
        compared_files += 1
        if not target_rtk.exists():
            mismatches.append(
                {
                    "reason": "missing_target",
                    "source": str(source_rtk.relative_to(REPO_ROOT)),
                    "target": str(target_rtk),
                }
            )
        else:
            src_hash = _hash_file(source_rtk)
            dst_hash = _hash_file(target_rtk)
            if src_hash != dst_hash:
                mismatches.append(
                    {
                        "reason": "hash_mismatch",
                        "source": str(source_rtk.relative_to(REPO_ROOT)),
                        "target": str(target_rtk),
                        "source_sha256": src_hash,
                        "target_sha256": dst_hash,
                    }
                )

    for src_file in _iter_payload_files(source_host_payload):
        rel = src_file.relative_to(source_host_payload)
        dst_file = hermes_root / rel
        compared_files += 1
        if not dst_file.exists():
            mismatches.append(
                {
                    "reason": "missing_target",
                    "source": str(src_file.relative_to(REPO_ROOT)),
                    "target": str(dst_file),
                }
            )
            continue
        src_hash = _hash_file(src_file)
        dst_hash = _hash_file(dst_file)
        if src_hash != dst_hash:
            mismatches.append(
                {
                    "reason": "hash_mismatch",
                    "source": str(src_file.relative_to(REPO_ROOT)),
                    "target": str(dst_file),
                    "source_sha256": src_hash,
                    "target_sha256": dst_hash,
                }
            )

    return {
        "ok": not mismatches,
        "compared_files": compared_files,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


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


def _extract_memory_context(prompt: str) -> str:
    text = str(prompt or "")
    start = text.find("<memory-context>")
    end = text.find("</memory-context>")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start + len("<memory-context>") : end].strip()


def _extract_json_object_text(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_route_hint_payload_text(text: str) -> Dict[str, Any]:
    payload = _extract_json_object_text(text)
    if payload:
        return payload
    raw = str(text or "").strip()
    if not raw:
        return {}
    lowered = raw.lower()
    if lowered in {"fact", "temporal", "aggregate"}:
        return {"mode": lowered, "reason": raw}
    matches = [str(match.group(1) or "").strip().lower() for match in _ROUTE_MODE_RE.finditer(raw)]
    if not matches:
        return {}
    if len(set(matches)) != 1:
        return {}
    return {
        "mode": matches[-1],
        "reason": raw,
    }


def _extract_route_hint_response_text(response: Any) -> str:
    choices = list(getattr(response, "choices", []) or [])
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = str(getattr(message, "content", "") or "").strip()
    if content:
        return content
    return str(getattr(message, "reasoning_content", "") or "").strip()


def _parse_fixed_now(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid --fixed-now timestamp: {raw}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _answer_tokens(text: str) -> set[str]:
    return {
        str(match.group(0) or "").casefold()
        for match in _TOKEN_RE.finditer(str(text or ""))
        if str(match.group(0) or "").strip()
    }


def _significant_answer_tokens(text: str) -> set[str]:
    return {
        token
        for token in _answer_tokens(text)
        if token not in _ROUTE_FILLER_TOKENS and (len(token) > 1 or token.isdigit())
    }


def _extract_time_variants(text: str) -> set[str]:
    raw = str(text or "")
    values: set[str] = set()
    for match in _TIME_COLON_RE.finditer(raw):
        minutes = int(match.group(1) or 0)
        seconds = int(match.group(2) or 0)
        values.add(f"{minutes:02d}:{seconds:02d}")
    for match in _TIME_WORD_RE.finditer(raw):
        minutes = int(match.group(1) or 0)
        seconds = int(match.group(2) or 0)
        values.add(f"{minutes:02d}:{seconds:02d}")
    return values


def _direct_retrieval_evidence_kind(*, answer: str, memory_context: str) -> str:
    normalized_answer = _normalize_answer_text(answer)
    normalized_context = _normalize_answer_text(memory_context)
    if normalized_answer and normalized_answer in normalized_context:
        return "yes_answer_found_verbatim"

    answer_times = _extract_time_variants(answer)
    if answer_times and answer_times.intersection(_extract_time_variants(memory_context)):
        return "yes_answer_found_time_equivalent"

    answer_tokens = _significant_answer_tokens(answer)
    if len(answer_tokens) >= 3 and answer_tokens.issubset(_answer_tokens(memory_context)):
        return "yes_answer_supported_by_named_tokens"

    return ""


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


def _judge_retrieval_support(
    *,
    base_url: str,
    api_key: str,
    model: str,
    question: str,
    answer: str,
    captured_prompt: str,
) -> str:
    memory_context = _extract_memory_context(captured_prompt)
    direct_evidence = _direct_retrieval_evidence_kind(answer=answer, memory_context=memory_context)
    if direct_evidence:
        return direct_evidence
    prompt = (
        "Question:\n"
        f"{question}\n\n"
        "Gold answer:\n"
        f"{answer}\n\n"
        "Recalled memory context:\n"
        f"{memory_context}\n\n"
        "Answer yes only if the recalled memory context directly supports the gold answer. "
        "Count direct support when the answer is stated verbatim, expressed with an obvious formatting variant, "
        "or the same named entity is explicitly identified in context. "
        "Answer no if correctness would require arithmetic, combining multiple separate facts, "
        "knowledge-update integration, or outside world knowledge. Reply yes or no."
    )
    return _judge_yes_no(
        base_url=base_url,
        api_key=api_key,
        model=model,
        prompt=prompt,
        max_tokens=128,
        max_attempts=3,
    )


def _classify_failure_layer(*, answer_correct: bool, retrieval_correct: bool) -> str:
    if answer_correct and retrieval_correct:
        return "none"
    if answer_correct and not retrieval_correct:
        return "answer_recovered_despite_retrieval_gap"
    if not answer_correct and retrieval_correct:
        return "llm_answer"
    return "retrieval"


def _answer_judge_mode(judge: str) -> str:
    normalized = str(judge or "")
    if normalized == "yes_exact_match":
        return "exact_match"
    if normalized == "yes_answer_contained":
        return "answer_contained"
    return "llm_judge"


def _retrieval_judge_mode(judge: str) -> str:
    normalized = str(judge or "")
    if normalized.startswith("yes_answer_found_") or normalized == "yes_answer_supported_by_named_tokens":
        return "direct_evidence"
    if normalized in {"yes", "no", "unknown"}:
        return "llm_judge"
    return "heuristic"


def _provider_route_snapshot(provider: Any) -> Dict[str, Any]:
    route = dict(getattr(provider, "_last_prefetch_routing", {}) or {})
    channels = list(getattr(provider, "_last_prefetch_channels", []) or [])
    if not route and not channels:
        return {}
    normalized_channels: List[Dict[str, Any]] = []
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        normalized_channels.append(
            {
                "name": str(channel.get("name") or ""),
                "status": str(channel.get("status") or ""),
                "reason": str(channel.get("reason") or ""),
                "candidate_count": int(channel.get("candidate_count") or 0),
            }
        )
    return {
        "requested_mode": str(route.get("requested_mode") or ""),
        "applied_mode": str(route.get("applied_mode") or ""),
        "source": str(route.get("source") or ""),
        "reason": str(route.get("reason") or ""),
        "fallback_used": bool(route.get("fallback_used")),
        "bounds": dict(route.get("bounds") or {}),
        "channels": normalized_channels,
    }


def _provider_candidate_debug_snapshot(provider: Any) -> Dict[str, Any]:
    debug = dict(getattr(provider, "_last_prefetch_debug", {}) or {})
    if not debug:
        return {}
    fused_candidates: List[Dict[str, Any]] = []
    for item in list(debug.get("fused_candidates") or []):
        if not isinstance(item, dict):
            continue
        fused_candidates.append(
            {
                "key": str(item.get("key") or ""),
                "shelf": str(item.get("shelf") or ""),
                "rrf_score": float(item.get("rrf_score") or 0.0),
                "priority_bonus": float(item.get("priority_bonus") or 0.0),
                "channel_ranks": dict(item.get("channel_ranks") or {}),
                "id": int(item.get("id") or 0),
                "row_id": int(item.get("row_id") or 0),
                "turn_number": int(item.get("turn_number") or 0),
                "document_id": int(item.get("document_id") or 0),
                "section_index": int(item.get("section_index") or 0),
                "created_at": str(item.get("created_at") or ""),
                "overlap_count": int(item.get("overlap_count") or 0),
                "semantic_score": float(item.get("semantic_score") or 0.0),
                "same_session": bool(item.get("same_session")),
                "content_excerpt": str(item.get("content_excerpt") or ""),
            }
        )
    selected_rows: Dict[str, List[Dict[str, Any]]] = {}
    for name, rows in dict(debug.get("selected_rows") or {}).items():
        normalized_rows: List[Dict[str, Any]] = []
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            normalized_rows.append(
                {
                    "id": int(row.get("id") or 0),
                    "session_id": str(row.get("session_id") or ""),
                    "turn_number": int(row.get("turn_number") or 0),
                    "stable_key": str(row.get("stable_key") or ""),
                    "row_type": str(row.get("row_type") or ""),
                    "document_id": int(row.get("document_id") or 0),
                    "section_index": int(row.get("section_index") or 0),
                    "created_at": str(row.get("created_at") or ""),
                    "overlap_count": int(row.get("overlap_count") or 0),
                    "semantic_score": float(row.get("semantic_score") or 0.0),
                    "channels": list(row.get("channels") or []),
                    "channel_ranks": dict(row.get("channel_ranks") or {}),
                    "rrf_score": float(row.get("rrf_score") or 0.0),
                    "content_excerpt": str(row.get("content_excerpt") or ""),
                }
            )
        selected_rows[str(name)] = normalized_rows
    return {
        "fused_candidates": fused_candidates,
        "selected_rows": selected_rows,
    }


def _kuzu_scalar_count(conn: Any, query: str) -> int:
    rows = conn.execute(query)
    if not hasattr(rows, "has_next") or not hasattr(rows, "get_next"):
        return 0
    if not rows.has_next():
        return 0
    row = rows.get_next()
    return int(row[0] or 0)


def _sqlite_scalar_count(conn: Any, table_name: str) -> int:
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _backend_population_snapshot(provider: Any) -> Dict[str, Any]:
    store = getattr(provider, "_store", None)
    snapshot = {
        "sqlite_graph_error": "",
        "sqlite_graph_counts": {},
        "graph_backend": "",
        "graph_error": "",
        "graph_counts": {},
        "corpus_backend": "",
        "corpus_error": "",
        "corpus_counts": {},
    }
    if store is None:
        return snapshot

    sqlite_conn = getattr(store, "conn", None)
    if sqlite_conn is not None:
        try:
            snapshot["sqlite_graph_counts"] = {
                "entity_count": _sqlite_scalar_count(sqlite_conn, "graph_entities"),
                "state_count": _sqlite_scalar_count(sqlite_conn, "graph_states"),
                "conflict_count": _sqlite_scalar_count(sqlite_conn, "graph_conflicts"),
                "relation_count": _sqlite_scalar_count(sqlite_conn, "graph_relations"),
                "inferred_relation_count": _sqlite_scalar_count(sqlite_conn, "graph_inferred_relations"),
            }
        except Exception as exc:
            snapshot["sqlite_graph_error"] = str(exc)

    snapshot["graph_backend"] = str(getattr(store, "_graph_backend_name", "") or "")
    snapshot["graph_error"] = str(getattr(store, "_graph_backend_error", "") or "")
    graph_backend = getattr(store, "_graph_backend", None)
    if graph_backend is not None:
        try:
            conn = graph_backend.conn
            snapshot["graph_counts"] = {
                "entity_count": _kuzu_scalar_count(conn, "MATCH (e:Entity) RETURN count(e) AS count"),
                "state_count": _kuzu_scalar_count(conn, "MATCH (s:State) RETURN count(s) AS count"),
                "conflict_count": _kuzu_scalar_count(conn, "MATCH (c:Conflict) RETURN count(c) AS count"),
                "relation_count": _kuzu_scalar_count(
                    conn,
                    "MATCH (:Entity)-[r:RELATES_TO]->(:Entity) RETURN count(r) AS count",
                ),
                "inferred_relation_count": _kuzu_scalar_count(
                    conn,
                    "MATCH (:Entity)-[r:INFERRED_RELATES_TO]->(:Entity) RETURN count(r) AS count",
                ),
            }
        except Exception as exc:
            snapshot["graph_error"] = str(exc)

    snapshot["corpus_backend"] = str(getattr(store, "_corpus_backend_name", "") or "")
    snapshot["corpus_error"] = str(getattr(store, "_corpus_backend_error", "") or "")
    corpus_backend = getattr(store, "_corpus_backend", None)
    if corpus_backend is not None:
        try:
            collection = corpus_backend.collection
            section_count = int(collection.count() or 0)
            corpus_counts: Dict[str, Any] = {"section_count": section_count}
            payload = collection.get(include=["metadatas"])
            stable_keys = {
                str(metadata.get("stable_key") or "")
                for metadata in list(payload.get("metadatas") or [])
                if isinstance(metadata, dict) and str(metadata.get("stable_key") or "")
            }
            corpus_counts["stable_key_count"] = len(stable_keys)
            snapshot["corpus_counts"] = corpus_counts
        except Exception as exc:
            snapshot["corpus_error"] = str(exc)
    return snapshot


def _memory_manager_route_snapshot(memory_manager: Any) -> Dict[str, Any]:
    for provider in list(getattr(memory_manager, "_providers", []) or []):
        if str(getattr(provider, "name", "") or "") != "brainstack":
            continue
        snapshot = _provider_route_snapshot(provider)
        if snapshot:
            return snapshot
    return {}


def _select_entries(
    entries: List[Dict[str, Any]],
    *,
    donor_module: ModuleType,
    sample_size: int,
    seed: int,
    question_ids: List[str],
    canary: bool,
) -> List[Dict[str, Any]]:
    selected_ids = list(question_ids or [])
    if canary:
        selected_ids = list(FIXED_CANARY_QUESTION_IDS)
    if selected_ids:
        by_id = {str(entry.get("question_id") or ""): entry for entry in entries}
        return [by_id[qid] for qid in selected_ids if qid in by_id]
    chooser = getattr(donor_module, "stratified_sample", None)
    if callable(chooser):
        return chooser(entries, sample_size, seed=seed)
    return random.Random(seed).sample(entries, sample_size)


def _build_memory_context_prompt(*, system_prompt_block: str, prefetch_block: str) -> str:
    sections: List[str] = []
    if str(system_prompt_block or "").strip():
        sections.append(str(system_prompt_block).strip())
    sections.append(f"<memory-context>\n{str(prefetch_block or '').strip()}\n</memory-context>")
    return "\n\n".join(section for section in sections if section.strip())


def _build_direct_route_resolver(*, model: str, base_url: str, api_key: str) -> Tuple[Callable[[str], Dict[str, Any]], openai.OpenAI]:
    client = openai.OpenAI(base_url=base_url, api_key=api_key)

    def _resolver(query: str) -> Dict[str, Any]:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You classify Brainstack memory retrieval questions into one of three modes.\n"
                        "Use temporal when the user needs ordering, first/last, before/after comparison, date difference, or change over time.\n"
                        "Use aggregate when the user needs totals, counts across multiple events, exhaustive collection, or a cross-event sum even if the question text has no digits.\n"
                        "Use fact for ordinary fact lookup or if uncertain.\n"
                        "Reply with exactly one lowercase word: fact, temporal, or aggregate. No JSON. No explanation."
                    ),
                },
                {"role": "user", "content": str(query or "")},
            ],
            temperature=0.0,
            max_tokens=8,
            timeout=12.0,
        )
        text = _extract_route_hint_response_text(response)
        payload = _extract_route_hint_payload_text(text)
        return {
            "mode": str(payload.get("mode") or "").strip().lower(),
            "reason": str(payload.get("reason") or text).strip(),
            "source": "direct_benchmark_route_hint",
        }

    return _resolver, client


def _install_brainstack_route_resolver(memory_manager: Any, route_resolver: Callable[[str], Dict[str, Any]]) -> bool:
    installed = False
    for provider in list(getattr(memory_manager, "_providers", []) or []):
        if str(getattr(provider, "name", "") or "") != "brainstack":
            continue
        setattr(provider, "_route_resolver_override", route_resolver)
        config = getattr(provider, "_config", None)
        if isinstance(config, dict):
            config["_route_resolver"] = route_resolver
        installed = True
    return installed


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
                "tier2_max_tokens": 900,
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
            max_tokens=min(int(max_tokens), 900),
            timeout=max(float(timeout), 60.0),
        )

    def _extractor(transcript_entries, *, session_id: str, turn_number: int, trigger_reason: str):
        try:
            return extract_tier2_candidates(
                transcript_entries,
                llm_caller=_llm_caller,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "event": "tier2_fallback",
                        "session_id": session_id,
                        "turn_number": turn_number,
                        "trigger_reason": trigger_reason,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return {
                "profile_items": [],
                "states": [],
                "continuity_rows": [],
                "relations": [],
                "inferred_relations": [],
                "typed_entities": [],
                "temporal_events": [],
                "continuity_summary": "",
                "decisions": [],
                "_meta": {
                    "json_parse_status": "exception",
                    "trigger_reason": trigger_reason,
                    "error": str(exc),
                },
            }

    return _extractor, client


def _flush_benchmark_tier2(
    provider: Any,
    *,
    session_id: str,
    trigger_reason: str,
    transcript_limit_override: int | None = None,
) -> Dict[str, Any]:
    if not hasattr(provider, "_run_tier2_batch"):
        return {}
    original_transcript_limit = None
    if transcript_limit_override is not None and hasattr(provider, "_tier2_transcript_limit"):
        original_transcript_limit = int(getattr(provider, "_tier2_transcript_limit", 0) or 0)
        provider._tier2_transcript_limit = max(1, int(transcript_limit_override))
    try:
        result = provider._run_tier2_batch(
            session_id=session_id,
            turn_number=getattr(provider, "_turn_counter", 0),
            trigger_reason=trigger_reason,
        )
    finally:
        if original_transcript_limit is not None and hasattr(provider, "_tier2_transcript_limit"):
            provider._tier2_transcript_limit = original_transcript_limit
    if hasattr(provider, "_pending_tier2_turns"):
        provider._pending_tier2_turns = 0
    return dict(result or getattr(provider, "_last_tier2_batch_result", {}) or {})


def _summarize_tier2_batch_results(batch_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    parse_status_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    total_writes = 0
    batches_with_writes = 0
    failure_batches: List[Dict[str, Any]] = []
    success_batches: List[Dict[str, Any]] = []
    for item in batch_results:
        parse_status = str(item.get("json_parse_status") or "unknown")
        parse_status_counts[parse_status] = parse_status_counts.get(parse_status, 0) + 1
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        writes = int(item.get("writes_performed") or 0)
        total_writes += writes
        if writes > 0:
            batches_with_writes += 1
            if parse_status in {"json_object", "json_snippet", "json_repaired"} and status == "ok":
                success_batches.append(
                    {
                        "trigger_reason": str(item.get("trigger_reason") or ""),
                        "status": status,
                        "json_parse_status": parse_status,
                        "writes_performed": writes,
                        "transcript_turn_numbers": list(item.get("transcript_turn_numbers") or []),
                        "extracted_counts": dict(item.get("extracted_counts") or {}),
                        "temporal_event_samples": list(item.get("temporal_event_samples") or []),
                        "typed_entity_samples": list(item.get("typed_entity_samples") or []),
                        "raw_payload_preview": str(item.get("raw_payload_preview") or ""),
                        "raw_payload_tail": str(item.get("raw_payload_tail") or ""),
                        "raw_payload_length": int(item.get("raw_payload_length") or 0),
                    }
                )
        if parse_status not in {"json_object", "json_snippet", "json_repaired", "empty_batch"} or status != "ok" or writes == 0:
            failure_batches.append(
                {
                    "trigger_reason": str(item.get("trigger_reason") or ""),
                    "status": status,
                    "json_parse_status": parse_status,
                    "writes_performed": writes,
                    "transcript_turn_numbers": list(item.get("transcript_turn_numbers") or []),
                    "extracted_counts": dict(item.get("extracted_counts") or {}),
                    "temporal_event_samples": list(item.get("temporal_event_samples") or []),
                    "typed_entity_samples": list(item.get("typed_entity_samples") or []),
                    "raw_payload_preview": str(item.get("raw_payload_preview") or ""),
                    "raw_payload_tail": str(item.get("raw_payload_tail") or ""),
                    "raw_payload_length": int(item.get("raw_payload_length") or 0),
                }
            )
    return {
        "batch_count": len(batch_results),
        "parse_status_counts": parse_status_counts,
        "status_counts": status_counts,
        "batches_with_writes": batches_with_writes,
        "total_writes": total_writes,
        "success_batches": success_batches[:20],
        "failure_batches": failure_batches[:20],
    }


def _seed_brainstack_kernel(
    hermes_root: Path,
    home: Path,
    entry: Dict[str, Any],
    *,
    oracle_only: bool,
    model: str,
    base_url: str,
    api_key: str,
    benchmark_tier2_transcript_limit: int = BENCHMARK_TIER2_TRANSCRIPT_LIMIT,
    benchmark_tier2_flush_turn_interval: int = BENCHMARK_TIER2_FLUSH_TURN_INTERVAL,
    benchmark_tier2_max_tokens: int = 400,
    benchmark_tier2_flush_mode: str = "turn_interval",
) -> Dict[str, Any]:
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
        provider._tier2_max_tokens = int(benchmark_tier2_max_tokens)
    if hasattr(provider, "_tier2_transcript_limit"):
        provider._tier2_transcript_limit = max(
            int(getattr(provider, "_tier2_transcript_limit", 0) or 0),
            int(benchmark_tier2_transcript_limit),
        )

    total_sessions = 0
    total_turns = 0
    pending_tier2_turns = 0
    backend_population: Dict[str, Any] = {}
    tier2_batch_results: List[Dict[str, Any]] = []
    messages: List[Dict[str, Any]] = []
    try:
        benchmark_session_id = f"longmemeval:{entry.get('question_id')}:seed"
        for idx, upstream_session_id, session_date, session in _iter_entry_sessions(entry, oracle_only=oracle_only):
            total_sessions += 1
            session_turns = 0
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
                pending_tier2_turns += 1
                session_turns += 1
                if (
                    benchmark_tier2_flush_mode == "turn_interval"
                    and pending_tier2_turns >= int(benchmark_tier2_flush_turn_interval)
                ):
                    flush_result = _flush_benchmark_tier2(
                        provider,
                        session_id=benchmark_session_id,
                        trigger_reason=f"benchmark_turn_flush:{upstream_session_id or idx}",
                    )
                    if flush_result:
                        tier2_batch_results.append(flush_result)
                    pending_tier2_turns = 0
            if benchmark_tier2_flush_mode == "session_boundary" and session_turns > 0:
                flush_result = _flush_benchmark_tier2(
                    provider,
                    session_id=benchmark_session_id,
                    trigger_reason=f"benchmark_session_flush:{upstream_session_id or idx}",
                    transcript_limit_override=session_turns,
                )
                if flush_result:
                    tier2_batch_results.append(flush_result)
                pending_tier2_turns = 0
        if total_turns and benchmark_tier2_flush_mode == "turn_interval":
            flush_result = _flush_benchmark_tier2(
                provider,
                session_id=benchmark_session_id,
                trigger_reason="benchmark_seed_flush",
            )
            if flush_result:
                tier2_batch_results.append(flush_result)
        provider.on_session_end(messages)
        backend_population = _backend_population_snapshot(provider)
    finally:
        try:
            direct_tier2_client.close()
        except Exception:
            pass
        try:
            provider.shutdown()
        except Exception:
            pass
    return {
        "seeded_sessions": total_sessions,
        "seeded_turns": total_turns,
        "backend_population": backend_population,
        "tier2_batch_telemetry": _summarize_tier2_batch_results(tier2_batch_results),
    }


def _load_initialized_brainstack_provider(hermes_root: Path, home: Path, *, session_id: str):
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    from plugins.memory import load_memory_provider

    provider = load_memory_provider("brainstack")
    if provider is None:
        raise RuntimeError("Brainstack memory provider is unavailable in target Hermes checkout.")
    provider.initialize(session_id, hermes_home=str(home), platform="cli")
    return provider


def _run_brainstack_retrieval_harness(
    *,
    hermes_root: Path,
    entry: Dict[str, Any],
    model: str,
    base_url: str,
    api_key: str,
    oracle_seed: bool,
    benchmark_tier2_transcript_limit: int = BENCHMARK_TIER2_TRANSCRIPT_LIMIT,
    benchmark_tier2_flush_turn_interval: int = BENCHMARK_TIER2_FLUSH_TURN_INTERVAL,
    benchmark_tier2_max_tokens: int = 400,
    benchmark_tier2_flush_mode: str = "turn_interval",
    inject_direct_route_resolver: bool = False,
    candidate_debug: bool = False,
    progress_label: str = "",
) -> Dict[str, Any]:
    with TemporaryDirectory(prefix="brainstack-longmemeval-") as tmp_dir:
        total_started = time.perf_counter()
        if progress_label:
            print(
                json.dumps(
                    {
                        "event": "question_start",
                        "label": progress_label,
                        "question_id": entry.get("question_id"),
                        "mode": "retrieval_only",
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
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
                benchmark_tier2_transcript_limit=benchmark_tier2_transcript_limit,
                benchmark_tier2_flush_turn_interval=benchmark_tier2_flush_turn_interval,
                benchmark_tier2_max_tokens=benchmark_tier2_max_tokens,
                benchmark_tier2_flush_mode=benchmark_tier2_flush_mode,
            )
        seed_seconds = time.perf_counter() - seed_started

        provider = _load_initialized_brainstack_provider(
            hermes_root,
            home,
            session_id=f"brainstack-retrieval-harness-{entry.get('question_id')}",
        )
        if candidate_debug:
            setattr(provider, "_capture_candidate_debug", True)
        direct_route_client = None
        if inject_direct_route_resolver:
            direct_route_resolver, direct_route_client = _build_direct_route_resolver(
                model=model,
                base_url=base_url,
                api_key=api_key,
            )
            setattr(provider, "_route_resolver_override", direct_route_resolver)

        try:
            retrieval_started = time.perf_counter()
            system_prompt_block = provider.system_prompt_block()
            prefetch_block = provider.prefetch(
                str(entry.get("question") or ""),
                session_id=f"brainstack-retrieval-harness-{entry.get('question_id')}",
            )
            retrieval_seconds = time.perf_counter() - retrieval_started
            route_snapshot = _provider_route_snapshot(provider)
            candidate_debug_snapshot = _provider_candidate_debug_snapshot(provider)
            backend_population = _backend_population_snapshot(provider)
        finally:
            if direct_route_client is not None:
                try:
                    direct_route_client.close()
                except Exception:
                    pass
            try:
                provider.shutdown()
            except Exception:
                pass

        captured_prompt = _build_memory_context_prompt(
            system_prompt_block=system_prompt_block,
            prefetch_block=prefetch_block,
        )
        payload = {
            "question_id": str(entry.get("question_id") or ""),
            "question_type": str(entry.get("question_type") or ""),
            "question": str(entry.get("question") or ""),
            "answer": str(entry.get("answer") or ""),
            "provider": "retrieval_harness",
            "model": model,
            "route_resolver_injected": bool(inject_direct_route_resolver),
            "seeded_sessions": seed_counts["seeded_sessions"],
            "seeded_turns": seed_counts["seeded_turns"],
            "backend_population": dict(seed_counts.get("backend_population") or {}),
            "tier2_batch_telemetry": dict(seed_counts.get("tier2_batch_telemetry") or {}),
            "backend_population_after_prefetch": dict(backend_population or {}),
            "seed_seconds": round(seed_seconds, 3),
            "retrieval_seconds": round(retrieval_seconds, 3),
            "total_seconds": round(time.perf_counter() - total_started, 3),
            "requested_mode": str(route_snapshot.get("requested_mode") or ""),
            "applied_mode": str(route_snapshot.get("applied_mode") or ""),
            "route_source": str(route_snapshot.get("source") or ""),
            "route_reason": str(route_snapshot.get("reason") or ""),
            "route_fallback_used": bool(route_snapshot.get("fallback_used")),
            "route_bounds": dict(route_snapshot.get("bounds") or {}),
            "route_channels": list(route_snapshot.get("channels") or []),
            "route_channel_counts": {
                str(channel.get("name") or ""): int(channel.get("candidate_count") or 0)
                for channel in list(route_snapshot.get("channels") or [])
                if isinstance(channel, dict)
            },
            "memory_context_present": bool(str(prefetch_block or "").strip()),
            "captured_memory_context": str(prefetch_block or "").strip(),
            "captured_system_prompt": str(system_prompt_block or "").strip(),
            "captured_prompt": captured_prompt,
        }
        if candidate_debug_snapshot:
            payload["candidate_debug"] = candidate_debug_snapshot
        if progress_label:
            print(
                json.dumps(
                    {
                        "event": "question_done",
                        "label": progress_label,
                        "question_id": payload["question_id"],
                        "mode": "retrieval_only",
                        "total_seconds": payload["total_seconds"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        return payload


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
    fixed_now: datetime | None,
    answer_only: bool,
    benchmark_tier2_transcript_limit: int = BENCHMARK_TIER2_TRANSCRIPT_LIMIT,
    benchmark_tier2_flush_turn_interval: int = BENCHMARK_TIER2_FLUSH_TURN_INTERVAL,
    benchmark_tier2_max_tokens: int = 400,
    benchmark_tier2_flush_mode: str = "turn_interval",
    retrieval_only: bool = False,
    inject_direct_route_resolver: bool = False,
    progress_label: str = "",
) -> Dict[str, Any]:
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    import run_agent
    from agent.memory_manager import MemoryManager

    with TemporaryDirectory(prefix="brainstack-longmemeval-") as tmp_dir:
        total_started = time.perf_counter()
        if progress_label:
            print(
                json.dumps(
                    {
                        "event": "question_start",
                        "label": progress_label,
                        "question_id": entry.get("question_id"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
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
                benchmark_tier2_transcript_limit=benchmark_tier2_transcript_limit,
                benchmark_tier2_flush_turn_interval=benchmark_tier2_flush_turn_interval,
                benchmark_tier2_max_tokens=benchmark_tier2_max_tokens,
                benchmark_tier2_flush_mode=benchmark_tier2_flush_mode,
            )
        seed_seconds = time.perf_counter() - seed_started
        if progress_label:
            print(
                json.dumps(
                    {
                        "event": "question_seeded",
                        "label": progress_label,
                        "question_id": entry.get("question_id"),
                        "seeded_sessions": seed_counts.get("seeded_sessions"),
                        "seeded_turns": seed_counts.get("seeded_turns"),
                        "backend_population": seed_counts.get("backend_population", {}),
                        "tier2_batch_telemetry": seed_counts.get("tier2_batch_telemetry", {}),
                        "seed_seconds": round(seed_seconds, 3),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        captured: Dict[str, Any] = {}
        api_seconds = 0.0
        tool_seconds = 0.0
        tool_events: List[Dict[str, Any]] = []
        direct_route_resolver = None
        direct_route_client = None
        if inject_direct_route_resolver:
            direct_route_resolver, direct_route_client = _build_direct_route_resolver(
                model=judge_model,
                base_url=base_url,
                api_key=api_key,
            )

        original_interruptible = run_agent.AIAgent._interruptible_api_call
        original_streaming = getattr(run_agent.AIAgent, "_interruptible_streaming_api_call", None)
        original_memory_handle = MemoryManager.handle_tool_call

        def _capture_then_call(agent_self, api_kwargs: Dict[str, Any]):
            nonlocal api_seconds
            messages = list(api_kwargs.get("messages") or [])
            captured["prompt"] = "\n\n".join(str(message.get("content") or "") for message in messages)
            if retrieval_only:
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="retrieval-only stub", tool_calls=[]),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                    model="retrieval-only-stub",
                )
            started = time.perf_counter()
            try:
                return original_interruptible(agent_self, api_kwargs)
            finally:
                api_seconds += time.perf_counter() - started

        def _capture_then_stream(agent_self, api_kwargs: Dict[str, Any], on_first_delta=None):
            nonlocal api_seconds
            messages = list(api_kwargs.get("messages") or [])
            captured["prompt"] = "\n\n".join(str(message.get("content") or "") for message in messages)
            if retrieval_only:
                if on_first_delta is not None:
                    try:
                        on_first_delta()
                    except Exception:
                        pass
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="retrieval-only stub", tool_calls=[]),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                    model="retrieval-only-stub",
                )
            started = time.perf_counter()
            try:
                return original_streaming(agent_self, api_kwargs, on_first_delta=on_first_delta)
            finally:
                api_seconds += time.perf_counter() - started

        def _timed_memory_tool(self, tool_name: str, args: Dict[str, Any], **kwargs):
            nonlocal tool_seconds
            started = time.perf_counter()
            provider_obj = getattr(self, "_tool_to_provider", {}).get(tool_name)
            result = original_memory_handle(self, tool_name, args, **kwargs)
            duration = time.perf_counter() - started
            route_snapshot = _provider_route_snapshot(provider_obj) if provider_obj is not None else {}
            tool_seconds += duration
            event = {
                "tool_name": tool_name,
                "duration_seconds": round(duration, 6),
            }
            if route_snapshot:
                event["route"] = route_snapshot
                captured.setdefault("route_events", []).append(route_snapshot)
            tool_events.append(event)
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
        if fixed_now is not None:
            patchers.append(patch("hermes_time.now", lambda: fixed_now))
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
            route_resolver_injected = (
                _install_brainstack_route_resolver(agent._memory_manager, direct_route_resolver)
                if direct_route_resolver is not None
                else False
            )
            agent._cleanup_task_resources = lambda task_id: None
            agent._persist_session = lambda messages, history=None: None
            agent._save_trajectory = lambda messages, user_message, completed: None
            agent._save_session_log = lambda messages: None
            conversation_started = time.perf_counter()
            raw_result = agent.run_conversation(str(entry["question"]))
            conversation_seconds = time.perf_counter() - conversation_started
            result = dict(raw_result) if isinstance(raw_result, dict) else {"final_response": str(raw_result or "")}
            manager_route = _memory_manager_route_snapshot(agent._memory_manager)
            if manager_route:
                captured.setdefault("route_events", []).append(manager_route)
            try:
                agent._memory_manager.shutdown_all()
            except Exception:
                pass
        if direct_route_client is not None:
            try:
                direct_route_client.close()
            except Exception:
                pass

        hypothesis = str(result.get("final_response") or "").strip()
        answer = str(entry.get("answer") or "")
        answer_judge_mode = "llm_judge"
        if _normalize_answer_text(hypothesis) == _normalize_answer_text(answer):
            judge = "yes_exact_match"
            judge_seconds = 0.0
            answer_judge_mode = "exact_match"
        elif _normalize_answer_text(answer) and _normalize_answer_text(answer) in _normalize_answer_text(hypothesis):
            judge = "yes_answer_contained"
            judge_seconds = 0.0
            answer_judge_mode = "answer_contained"
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

        captured_memory_context = _extract_memory_context(captured.get("prompt", ""))
        memory_context_present = bool(captured_memory_context.strip())
        retrieval_judge = "skipped_answer_only" if answer_only else "unknown"
        retrieval_judge_mode = "skipped_answer_only" if answer_only else "unknown"
        retrieval_judge_seconds = 0.0
        answer_correct = str(judge).startswith("yes")
        retrieval_correct = False
        failure_layer = "answer_only"
        if not answer_only:
            retrieval_judge_started = time.perf_counter()
            retrieval_judge = _judge_retrieval_support(
                base_url=base_url,
                api_key=api_key,
                model=judge_model,
                question=str(entry.get("question") or ""),
                answer=answer,
                captured_prompt=captured.get("prompt", ""),
            )
            retrieval_judge_seconds = time.perf_counter() - retrieval_judge_started
            retrieval_correct = str(retrieval_judge).startswith("yes")
            retrieval_judge_mode = _retrieval_judge_mode(retrieval_judge)
            failure_layer = _classify_failure_layer(
                answer_correct=answer_correct,
                retrieval_correct=retrieval_correct,
            )
        route_events = list(captured.get("route_events") or [])
        last_route = dict(route_events[-1] or {}) if route_events else {}
        route_channels = list(last_route.get("channels") or [])
        suspicious_answer_judge_pass = (
            answer_correct
            and answer_judge_mode == "llm_judge"
            and (answer_only or not retrieval_correct)
        )

        payload = {
            "question_id": str(entry.get("question_id") or ""),
            "question_type": str(entry.get("question_type") or ""),
            "question": str(entry.get("question") or ""),
            "answer": answer,
            "hypothesis": hypothesis,
            "judge": judge,
            "answer_judge_mode": answer_judge_mode,
            "passed": answer_correct,
            "answer_correct": answer_correct,
            "retrieval_judge": retrieval_judge,
            "retrieval_judge_mode": retrieval_judge_mode,
            "retrieval_correct": None if answer_only else retrieval_correct,
            "failure_layer": failure_layer,
            "provider": provider,
            "model": model,
            "route_resolver_injected": route_resolver_injected,
            "seeded_sessions": seed_counts["seeded_sessions"],
            "seeded_turns": seed_counts["seeded_turns"],
            "backend_population": dict(seed_counts.get("backend_population") or {}),
            "tier2_batch_telemetry": dict(seed_counts.get("tier2_batch_telemetry") or {}),
            "seed_seconds": round(seed_seconds, 3),
            "conversation_seconds": round(conversation_seconds, 3),
            "api_seconds": round(api_seconds, 3),
            "tool_seconds": round(tool_seconds, 3),
            "judge_seconds": round(judge_seconds, 3),
            "retrieval_judge_seconds": round(retrieval_judge_seconds, 3),
            "total_seconds": round(time.perf_counter() - total_started, 3),
            "tool_events": tool_events,
            "route_events": route_events,
            "requested_mode": str(last_route.get("requested_mode") or ""),
            "applied_mode": str(last_route.get("applied_mode") or ""),
            "route_source": str(last_route.get("source") or ""),
            "route_reason": str(last_route.get("reason") or ""),
            "route_fallback_used": bool(last_route.get("fallback_used")),
            "route_bounds": dict(last_route.get("bounds") or {}),
            "route_channels": route_channels,
            "route_channel_counts": {
                str(channel.get("name") or ""): int(channel.get("candidate_count") or 0)
                for channel in route_channels
                if isinstance(channel, dict)
            },
            "suspicious_answer_judge_pass": suspicious_answer_judge_pass,
            "memory_context_present": memory_context_present,
            "captured_memory_context": captured_memory_context,
            "captured_prompt": captured.get("prompt", ""),
        }
        if progress_label:
            print(
                json.dumps(
                    {
                        "event": "question_done",
                        "label": progress_label,
                        "question_id": payload["question_id"],
                        "passed": payload["passed"],
                        "failure_layer": payload["failure_layer"],
                        "total_seconds": payload["total_seconds"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        return payload


def _write_report(path: Path, summary: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    report = {"summary": summary, "results": results}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


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
    parser.add_argument("--fixed-now", type=str, default="")
    parser.add_argument("--answer-only", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--inject-direct-route-resolver", action="store_true")
    parser.add_argument("--candidate-debug", action="store_true")
    parser.add_argument("--benchmark-tier2-transcript-limit", type=int, default=BENCHMARK_TIER2_TRANSCRIPT_LIMIT)
    parser.add_argument("--benchmark-tier2-flush-turn-interval", type=int, default=BENCHMARK_TIER2_FLUSH_TURN_INTERVAL)
    parser.add_argument("--benchmark-tier2-max-tokens", type=int, default=400)
    parser.add_argument(
        "--benchmark-tier2-flush-mode",
        choices=("turn_interval", "session_boundary"),
        default="turn_interval",
    )
    args = parser.parse_args()

    if args.answer_only and args.retrieval_only:
        parser.error("--answer-only and --retrieval-only are mutually exclusive")

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

    runtime_sync = _verify_runtime_sync(args.hermes_root)
    if not runtime_sync["ok"]:
        first = dict(list(runtime_sync.get("mismatches") or [{}])[0] or {})
        first_detail = f"{first.get('reason')}: {first.get('source')} -> {first.get('target')}"
        raise SystemExit(
            "Runtime sync verification failed before benchmark execution "
            f"({runtime_sync['mismatch_count']} mismatches across {runtime_sync['compared_files']} files). "
            f"First mismatch: {first_detail}"
        )

    dataset_path = Path(donor_module.DEFAULT_DATASET)
    entries = json.loads(dataset_path.read_text(encoding="utf-8"))
    chosen = _select_entries(
        entries,
        donor_module=donor_module,
        sample_size=args.sample_size,
        seed=args.seed,
        question_ids=list(args.question_id or []),
        canary=bool(args.canary),
    )

    model = str(args.model or donor_module.DEFAULT_BENCHMARK_MODEL)
    base_url = str(args.base_url or donor_module.DEFAULT_BENCHMARK_BASE_URL)
    provider = str(args.provider or donor_module.DEFAULT_BENCHMARK_PROVIDER)
    judge_model = str(args.judge_model or getattr(donor_module, "DEFAULT_JUDGE_MODEL", donor_module.DEFAULT_BENCHMARK_MODEL))
    fixed_now = _parse_fixed_now(args.fixed_now)

    results: List[Dict[str, Any]] = []
    started = time.perf_counter()
    for idx, entry in enumerate(chosen, start=1):
        if args.retrieval_only:
            payload = _run_brainstack_retrieval_harness(
                hermes_root=args.hermes_root,
                entry=entry,
                model=model,
                base_url=base_url,
                api_key=api_key,
                oracle_seed=bool(args.oracle_seed),
                benchmark_tier2_transcript_limit=args.benchmark_tier2_transcript_limit,
                benchmark_tier2_flush_turn_interval=args.benchmark_tier2_flush_turn_interval,
                benchmark_tier2_max_tokens=args.benchmark_tier2_max_tokens,
                benchmark_tier2_flush_mode=args.benchmark_tier2_flush_mode,
                inject_direct_route_resolver=bool(args.inject_direct_route_resolver),
                candidate_debug=bool(args.candidate_debug),
                progress_label=f"{idx}/{len(chosen)}",
            )
        else:
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
                fixed_now=fixed_now,
                answer_only=bool(args.answer_only),
                benchmark_tier2_transcript_limit=args.benchmark_tier2_transcript_limit,
                benchmark_tier2_flush_turn_interval=args.benchmark_tier2_flush_turn_interval,
                benchmark_tier2_max_tokens=args.benchmark_tier2_max_tokens,
                benchmark_tier2_flush_mode=args.benchmark_tier2_flush_mode,
                retrieval_only=False,
                inject_direct_route_resolver=bool(args.inject_direct_route_resolver),
                progress_label=f"{idx}/{len(chosen)}",
            )
        results.append(payload)
        print(json.dumps(payload, ensure_ascii=False))
        partial_summary = {
            "mode": (
                "brainstack_retrieval_quality"
                if args.retrieval_only
                else ("brainstack_answer_only" if args.answer_only else "brainstack_split_proof")
            ),
            "sample_size": len(chosen),
            "completed": len(results),
            "passed_so_far": None if args.retrieval_only else sum(1 for item in results if item["passed"]),
            "provider": provider,
            "model": model,
            "judge_model": judge_model,
            "dataset": str(dataset_path),
            "oracle_seed": bool(args.oracle_seed),
            "fixed_now": fixed_now.isoformat() if fixed_now is not None else "",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "runtime_sync": {
                "ok": bool(runtime_sync["ok"]),
                "compared_files": int(runtime_sync["compared_files"]),
                "mismatch_count": int(runtime_sync["mismatch_count"]),
            },
            "selected_question_ids": [str(item.get("question_id") or "") for item in chosen],
            "selection_mode": "canary" if args.canary else ("question_ids" if args.question_id else "sample"),
            "partial": True,
        }
        _write_report(args.report_path, partial_summary, results)

    summary = {
        "mode": (
            "brainstack_retrieval_quality"
            if args.retrieval_only
            else ("brainstack_answer_only" if args.answer_only else "brainstack_split_proof")
        ),
        "sample_size": len(results),
        "passed": None if args.retrieval_only else sum(1 for item in results if item["passed"]),
        "accuracy": (
            None
            if args.retrieval_only
            else round(sum(1 for item in results if item["passed"]) / len(results), 4) if results else 0.0
        ),
        "provider": provider,
        "model": model,
        "judge_model": judge_model,
        "dataset": str(dataset_path),
        "oracle_seed": bool(args.oracle_seed),
        "fixed_now": fixed_now.isoformat() if fixed_now is not None else "",
        "suspicious_answer_judge_passes": None if args.retrieval_only else sum(
            1 for item in results if item.get("suspicious_answer_judge_pass")
        ),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "runtime_sync": {
            "ok": bool(runtime_sync["ok"]),
            "compared_files": int(runtime_sync["compared_files"]),
            "mismatch_count": int(runtime_sync["mismatch_count"]),
        },
        "selected_question_ids": [str(item.get("question_id") or "") for item in chosen],
        "selection_mode": "canary" if args.canary else ("question_ids" if args.question_id else "sample"),
    }
    if args.retrieval_only:
        summary["memory_context_present"] = sum(1 for item in results if item.get("memory_context_present"))
        summary["non_fact_routes"] = sum(
            1 for item in results if str(item.get("applied_mode") or "") in {"temporal", "aggregate"}
        )
    elif not args.answer_only:
        retrieval_correct = sum(1 for item in results if item.get("retrieval_correct") is True)
        both_correct = sum(1 for item in results if item["passed"] and item.get("retrieval_correct") is True)
        summary["retrieval_correct"] = retrieval_correct
        summary["both_correct"] = both_correct
    _write_report(args.report_path, summary, results)
    print(json.dumps({"summary": summary, "report_path": str(args.report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
