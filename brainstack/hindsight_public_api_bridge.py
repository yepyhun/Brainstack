from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import time
from typing import Any, Mapping, Protocol
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from .hindsight_spine_adapter import (
    SUPPORTED_ACTIONS,
    SUPPORTED_TARGET_KINDS,
    normalize_proposal_action_batch,
    unavailable_proposal_action_batch,
)

HINDSIGHT_PUBLIC_API_BRIDGE_VERSION = "brainstack.hindsight_public_api_bridge.v1"
DEFAULT_LOCAL_HINDSIGHT_PROFILE = "brainstack-tier2"
DEFAULT_LOCAL_HINDSIGHT_BANK_ID = "brainstack-tier2"
HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER = "hermes_managed"
DEFAULT_LOCAL_HINDSIGHT_LLM_PROVIDER = HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER
DEFAULT_LOCAL_HINDSIGHT_LLM_MODEL = ""
DEFAULT_LOCAL_HINDSIGHT_LLM_BASE_URL = ""
DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER = "tei"
DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_TEI_URL = "http://127.0.0.1:7997"
DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER = "rrf"
DEFAULT_LOCAL_HINDSIGHT_RETAIN_EXTRACTION_MODE = "chunks"
DEFAULT_LOCAL_HINDSIGHT_TIMEOUT_SECONDS = 180
_SYNC_RESPONSE_LOOP: asyncio.AbstractEventLoop | None = None


class HindsightPublicMemoryClient(Protocol):
    """Small protocol over Hindsight public memory API names."""

    def retain_memories(
        self,
        *,
        bank_id: str,
        items: list[Mapping[str, Any]],
        document_tags: list[str] | None = None,
        async_mode: bool = True,
    ) -> Mapping[str, Any]: ...

    def trigger_consolidation(self, *, bank_id: str) -> Mapping[str, Any]: ...

    def recall_memories(
        self,
        *,
        bank_id: str,
        query: str,
        budget: str = "low",
        max_tokens: int = 900,
        trace: bool = True,
        tags: list[str] | None = None,
    ) -> Mapping[str, Any]: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _hash_json(value: Any, *, length: int = 32) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _hash_text(value: str, *, length: int = 32) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(value: str | None, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _tei_base_url(value: str) -> str:
    stripped = _text(value).rstrip("/")
    if stripped.endswith("/embed"):
        return stripped[: -len("/embed")]
    return stripped


def _installed_hindsight_api_command() -> str:
    sibling = Path(sys.executable).with_name("hindsight-api")
    if sibling.exists():
        return str(sibling)
    return shutil.which("hindsight-api") or ""


def _sanitize_hindsight_profile_name(profile: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", profile or "default")


def _hindsight_pg0_instance_name(profile: str | None) -> str:
    return f"hindsight-embed-{_sanitize_hindsight_profile_name(profile)}"


def _localhost_port_accepts_connections(port: int, *, timeout_seconds: float = 0.5) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _pid_file_state(pid_path: Path) -> tuple[int, str]:
    try:
        lines = pid_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0, ""
    pid = 0
    try:
        pid = int(str(lines[0]).strip()) if lines else 0
    except ValueError:
        pid = 0
    state = str(lines[7]).strip().lower() if len(lines) >= 8 else ""
    return pid, state


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _repair_stale_hindsight_pg0_instance(profile: str) -> dict[str, Any]:
    """Move aside stale pg0 postmaster state before Hindsight's daemon manager starts.

    pg0 can report an embedded PostgreSQL instance as running when a stale
    postmaster.pid remains after shutdown. If the recorded port refuses
    connections, Hindsight skips startup and then fails migrations. Do not call
    ``pg0 stop`` here: a recycled PID can belong to the host runtime, so the
    safe repair is only to move the stale PostgreSQL pid marker aside.
    """
    try:
        from pg0 import Pg0  # type: ignore[import-not-found]
    except Exception:
        return {"status": "skipped", "reason": "pg0_unavailable"}
    instance_name = _hindsight_pg0_instance_name(profile)
    try:
        pg0 = Pg0(name=instance_name, username="hindsight", password="hindsight", database="hindsight")
        info = pg0.info()
    except Exception as exc:
        return {"status": "skipped", "reason": f"pg0_info_failed:{type(exc).__name__}"}
    if not bool(getattr(info, "running", False)):
        return {"status": "healthy", "reason": "pg0_not_running"}
    port = int(getattr(info, "port", 0) or 0)
    if _localhost_port_accepts_connections(port):
        return {"status": "healthy", "reason": "pg0_port_accepts_connections", "port": port}
    data_dir = _text(getattr(info, "data_dir", ""))
    if not data_dir:
        return {"status": "suspect", "reason": "pg0_running_without_reachable_port_or_data_dir", "port": port}
    pid_path = Path(data_dir) / "postmaster.pid"
    if not pid_path.exists():
        return {"status": "suspect", "reason": "pg0_running_without_reachable_port_or_pid_file", "port": port}
    pid, state = _pid_file_state(pid_path)
    if state not in {"stopping"} and _process_exists(pid):
        return {
            "status": "suspect",
            "reason": "pg0_unreachable_but_recorded_pid_exists",
            "port": port,
            "pid": pid,
            "postmaster_state": state,
        }
    stale_path = pid_path.with_name(f"postmaster.pid.stale-{int(time.time())}")
    try:
        pid_path.replace(stale_path)
    except OSError as exc:
        return {"status": "failed", "reason": f"stale_pid_move_failed:{type(exc).__name__}", "port": port}
    return {
        "status": "repaired",
        "reason": "stale_pg0_postmaster_pid_moved",
        "port": port,
        "pid": pid,
        "postmaster_state": state,
        "stale_pid_path": str(stale_path),
    }


def _hermes_main_model() -> str:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
    except Exception:
        return ""
    model_cfg = cfg.get("model", {}) if isinstance(cfg, Mapping) else {}
    if isinstance(model_cfg, str):
        return _text(model_cfg)
    if isinstance(model_cfg, Mapping):
        return _text(model_cfg.get("default"))
    return ""


def _response_to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(k): _response_to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_response_to_jsonable(item) for item in value]
    for method_name in ("to_dict", "model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _response_to_jsonable(method())
            except Exception:
                continue
    data: dict[str, Any] = {}
    for key in (
        "id",
        "text",
        "type",
        "document_id",
        "chunk_id",
        "metadata",
        "source_fact_ids",
        "entities",
        "tags",
        "results",
        "trace",
        "operation_id",
        "operation_ids",
        "status",
        "success",
        "items_count",
    ):
        if hasattr(value, key):
            data[key] = _response_to_jsonable(getattr(value, key))
    return data or str(value)


def _response_to_mapping(value: Any) -> Mapping[str, Any]:
    jsonable = _response_to_jsonable(value)
    return jsonable if isinstance(jsonable, Mapping) else {}


def _resolve_sync_response(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        global _SYNC_RESPONSE_LOOP
        loop = _SYNC_RESPONSE_LOOP
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _SYNC_RESPONSE_LOOP = loop
        return loop.run_until_complete(value)
    raise RuntimeError("Hindsight async response cannot be awaited from a running event loop")


def _close_generated_hindsight_client(client: Any) -> bool:
    api_client = getattr(client, "_api_client", None)
    rest_client = getattr(api_client, "rest_client", None)
    pool_manager = getattr(rest_client, "_pool_manager", None)
    loop = getattr(pool_manager, "_loop", None)
    if loop is None:
        connector = getattr(pool_manager, "_connector", None)
        loop = getattr(connector, "_loop", None)
    if api_client is None or loop is None or loop.is_closed():
        return False
    close = getattr(api_client, "close", None)
    if not callable(close):
        return False
    close_coro = close()
    if loop.is_running():
        loop.create_task(close_coro)
    else:
        loop.run_until_complete(close_coro)
    return True


def _hindsight_consolidation_url(client: Any, bank_id: str) -> str:
    base_url = _text(getattr(client, "_base_url", "")).rstrip("/")
    if not base_url:
        return ""
    bank = urllib_parse.quote(bank_id, safe="")
    if base_url.endswith("/v1/default"):
        return f"{base_url}/banks/{bank}/consolidate"
    return f"{base_url}/v1/default/banks/{bank}/consolidate"


def _post_hindsight_consolidation(url: str, *, timeout_seconds: int) -> Mapping[str, Any]:
    request = urllib_request.Request(
        url,
        data=b"{}",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace").strip()
        data = json.loads(body) if body else {}
        if not isinstance(data, Mapping):
            data = {"response": data}
        return {"http_status": response.status, **dict(data)}


def _source_span_text(span: Mapping[str, Any]) -> str:
    for key in ("text", "content", "excerpt", "redacted_excerpt"):
        value = _text(span.get(key))
        if value:
            return value
    return ""


def build_hindsight_retain_items(source_batch: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    scope = _mapping(source_batch.get("scope"))
    for span in _list(source_batch.get("source_spans")):
        if not isinstance(span, Mapping):
            continue
        content = _source_span_text(span)
        source_span_id = _text(span.get("source_span_id") or span.get("span_id"))
        source_event_id = _text(span.get("source_event_id") or span.get("event_id"))
        if not content or not source_span_id:
            continue
        items.append(
            {
                "content": content,
                "timestamp": _text(span.get("observed_at") or span.get("timestamp")),
                "context": _text(span.get("context")),
                "metadata": {
                    "brainstack_bridge_version": HINDSIGHT_PUBLIC_API_BRIDGE_VERSION,
                    "source_span_id": source_span_id,
                    "source_event_id": source_event_id,
                    "assertion_speaker": _text(span.get("assertion_speaker") or span.get("speaker")),
                    "source_modality": _text(span.get("source_modality") or "conversation"),
                    "principal_scope_key": _text(scope.get("principal_scope_key")),
                    "workspace_scope_key": _text(scope.get("workspace_scope_key")),
                    "session_id": _text(source_batch.get("session_id")),
                    "source_text_hash": _hash_text(content),
                },
                "tags": [
                    tag
                    for tag in (
                        _text(scope.get("principal_scope_key")),
                        _text(scope.get("workspace_scope_key")),
                        "brainstack:tier2",
                    )
                    if tag
                ],
            }
        )
    return items


def build_hindsight_recall_query(source_batch: Mapping[str, Any]) -> str:
    snippets = []
    for span in _list(source_batch.get("source_spans")):
        if isinstance(span, Mapping):
            text = _source_span_text(span)
            if text:
                snippets.append(text)
    return "\n".join(snippets)[:1200]


def _verified_source_refs(
    result: Mapping[str, Any],
    source_batch: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    known_spans: set[str] = set()
    known_events: dict[str, str] = {}
    for span in _list(source_batch.get("source_spans")):
        if not isinstance(span, Mapping):
            continue
        span_id = _text(span.get("source_span_id") or span.get("span_id"))
        event_id = _text(span.get("source_event_id") or span.get("event_id"))
        if span_id:
            known_spans.add(span_id)
            if event_id:
                known_events[span_id] = event_id

    metadata = _mapping(result.get("metadata"))
    raw_span_ids = []
    raw_span_ids.extend(_list(metadata.get("source_span_ids")))
    if _text(metadata.get("source_span_id")):
        raw_span_ids.append(metadata.get("source_span_id"))

    source_span_ids = []
    source_event_ids = []
    for raw in raw_span_ids:
        span_id = _text(raw)
        if span_id and span_id in known_spans and span_id not in source_span_ids:
            source_span_ids.append(span_id)
            event_id = _text(known_events.get(span_id))
            if event_id and event_id not in source_event_ids:
                source_event_ids.append(event_id)

    for raw in _list(metadata.get("source_event_ids")):
        event_id = _text(raw)
        if event_id and event_id in set(known_events.values()) and event_id not in source_event_ids:
            source_event_ids.append(event_id)

    return source_span_ids, source_event_ids


def _target_kind(metadata: Mapping[str, Any]) -> str:
    target_kind = _text(metadata.get("brainstack_target_kind") or metadata.get("target_kind"))
    return target_kind if target_kind in SUPPORTED_TARGET_KINDS else "support_context"


def _action(metadata: Mapping[str, Any]) -> str:
    action = _text(metadata.get("brainstack_action") or metadata.get("action"))
    return action if action in SUPPORTED_ACTIONS else "create"


def _related_memory_ref(result: Mapping[str, Any]) -> dict[str, Any]:
    text = _text(result.get("text"))
    return {
        "donor": "hindsight",
        "memory_id": _text(result.get("id")),
        "type": _text(result.get("type")),
        "document_id": _text(result.get("document_id")),
        "chunk_id": _text(result.get("chunk_id")),
        "text_hash": _hash_text(text) if text else "",
        "source_fact_ids": [_text(item) for item in _list(result.get("source_fact_ids")) if _text(item)],
        "entities": [_text(item) for item in _list(result.get("entities")) if _text(item)],
        "tags": [_text(item) for item in _list(result.get("tags")) if _text(item)],
    }


def proposal_batch_from_hindsight_recall(
    *,
    recall_response: Mapping[str, Any],
    source_batch: Mapping[str, Any],
    retain_response: Mapping[str, Any] | None = None,
    consolidation_response: Mapping[str, Any] | None = None,
    donor_version: str = "",
    config_hash: str = "",
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    dropped_unsourced_candidates = 0
    for result in _list(recall_response.get("results")):
        if not isinstance(result, Mapping):
            continue
        metadata = _mapping(result.get("metadata"))
        source_span_ids, source_event_ids = _verified_source_refs(result, source_batch)
        if not source_span_ids or not source_event_ids:
            dropped_unsourced_candidates += 1
            continue
        target_kind = _target_kind(metadata)
        result_id = _text(result.get("id"))
        result_text = _text(result.get("text"))
        seed = {
            "result_id": result_id,
            "result_text_hash": _hash_text(result_text) if result_text else "",
            "source_span_ids": source_span_ids,
            "target_kind": target_kind,
            "target_slot": _text(metadata.get("brainstack_target_slot") or metadata.get("target_slot")),
        }
        actions.append(
            {
                "proposal_id": _text(metadata.get("brainstack_proposal_id"))
                or "hpub_" + _hash_json(seed, length=24).removeprefix("sha256:"),
                "action": _action(metadata),
                "target_kind": target_kind,
                "target_slot": _text(metadata.get("brainstack_target_slot") or metadata.get("target_slot")),
                "stable_key": _text(metadata.get("brainstack_stable_key") or result_id),
                "value_fingerprint": _text(metadata.get("value_fingerprint"))
                or _hash_json({"id": result_id, "text_hash": _hash_text(result_text)}, length=32),
                "confidence": float(metadata.get("confidence") or 0.0),
                "reason_code": _text(metadata.get("reason_code")) or "HINDSIGHT_PUBLIC_RECALL_RESULT",
                "source_span_ids": source_span_ids,
                "source_event_ids": source_event_ids,
                "related_memory_refs": [_related_memory_ref(result)],
                "assertion_speaker": _text(
                    metadata.get("assertion_speaker")
                    or metadata.get("source_role")
                    or metadata.get("speaker")
                )
                or "unknown",
                "support_visibility": _text(metadata.get("support_visibility"))
                or ("support_context" if target_kind == "support_context" else "inspect_only"),
            }
        )

    failure: dict[str, Any] = {}
    status = "ok" if actions else "empty"
    if dropped_unsourced_candidates:
        status = "degraded"
        failure = {
            "reason_code": "HINDSIGHT_UNVERIFIED_RECALL_DROPPED",
            "dropped_unsourced_candidates": dropped_unsourced_candidates,
        }
    raw = {
        "status": status,
        "operation_id": _text(
            _mapping(retain_response).get("operation_id")
            or _mapping(consolidation_response).get("operation_id")
            or recall_response.get("operation_id")
        ),
        "donor_version": donor_version,
        "config_hash": config_hash,
        "actions": actions,
        "failure": failure,
    }
    normalized = normalize_proposal_action_batch(raw)
    normalized["donor_operation_refs"] = {
        "retain": _operation_ref(retain_response),
        "consolidation": _operation_ref(consolidation_response),
    }
    normalized["adapter_version"] = HINDSIGHT_PUBLIC_API_BRIDGE_VERSION
    return normalized


def _operation_ref(response: Mapping[str, Any] | None) -> dict[str, Any]:
    data = _mapping(response)
    return {
        "operation_id": _text(data.get("operation_id")),
        "operation_ids": [_text(item) for item in _list(data.get("operation_ids")) if _text(item)],
        "status": _text(data.get("status")),
        "success": bool(data.get("success")) if "success" in data else None,
        "items_count": int(data.get("items_count") or 0),
    }


@dataclass(frozen=True)
class HindsightLocalRuntimeConfig:
    mode: str = "local_embedded"
    profile: str = DEFAULT_LOCAL_HINDSIGHT_PROFILE
    bank_id: str = DEFAULT_LOCAL_HINDSIGHT_BANK_ID
    llm_provider: str = DEFAULT_LOCAL_HINDSIGHT_LLM_PROVIDER
    llm_model: str = DEFAULT_LOCAL_HINDSIGHT_LLM_MODEL
    llm_base_url: str = DEFAULT_LOCAL_HINDSIGHT_LLM_BASE_URL
    llm_api_key: str = ""
    embeddings_provider: str = DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER
    embeddings_tei_url: str = DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_TEI_URL
    reranker_provider: str = DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER
    retain_extraction_mode: str = DEFAULT_LOCAL_HINDSIGHT_RETAIN_EXTRACTION_MODE
    retain_extract_causal_links: bool = False
    api_command: str = ""
    timeout_seconds: int = DEFAULT_LOCAL_HINDSIGHT_TIMEOUT_SECONDS
    idle_timeout_seconds: int = 300
    budget: str = "low"
    max_tokens: int = 900
    retain_async: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "HindsightLocalRuntimeConfig":
        env = environ or os.environ
        llm_provider = (
            _text(env.get("BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER"))
            or DEFAULT_LOCAL_HINDSIGHT_LLM_PROVIDER
        )
        default_model = _hermes_main_model() if llm_provider == HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER else DEFAULT_LOCAL_HINDSIGHT_LLM_MODEL
        default_base_url = "" if llm_provider == HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER else DEFAULT_LOCAL_HINDSIGHT_LLM_BASE_URL
        return cls(
            mode=_text(
                env.get("BRAINSTACK_TIER2_HINDSIGHT_MODE")
                or env.get("HINDSIGHT_MODE")
                or "local_embedded"
            ),
            profile=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_PROFILE"))
            or DEFAULT_LOCAL_HINDSIGHT_PROFILE,
            bank_id=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_BANK_ID"))
            or _text(env.get("HINDSIGHT_BANK_ID"))
            or DEFAULT_LOCAL_HINDSIGHT_BANK_ID,
            llm_provider=llm_provider,
            llm_model=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL"))
            or default_model,
            llm_base_url=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL"))
            or default_base_url,
            llm_api_key=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_LLM_API_KEY")),
            embeddings_provider=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_PROVIDER"))
            or DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER,
            embeddings_tei_url=_tei_base_url(
                _text(env.get("BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL"))
                or _text(env.get("BRAINSTACK_EMBEDDINGS_URL"))
                or DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_TEI_URL
            ),
            reranker_provider=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_RERANKER_PROVIDER"))
            or DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER,
            retain_extraction_mode=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACTION_MODE"))
            or DEFAULT_LOCAL_HINDSIGHT_RETAIN_EXTRACTION_MODE,
            retain_extract_causal_links=_bool_env(
                env.get("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACT_CAUSAL_LINKS"),
                default=False,
            ),
            api_command=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_API_COMMAND"))
            or _installed_hindsight_api_command(),
            timeout_seconds=_int_env(
                env.get("BRAINSTACK_TIER2_HINDSIGHT_TIMEOUT_SECONDS"),
                default=DEFAULT_LOCAL_HINDSIGHT_TIMEOUT_SECONDS,
            ),
            idle_timeout_seconds=_int_env(
                env.get("BRAINSTACK_TIER2_HINDSIGHT_IDLE_TIMEOUT_SECONDS"),
                default=300,
            ),
            budget=_text(env.get("BRAINSTACK_TIER2_HINDSIGHT_BUDGET")) or "low",
            max_tokens=_int_env(env.get("BRAINSTACK_TIER2_HINDSIGHT_MAX_TOKENS"), default=900),
            retain_async=_bool_env(env.get("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_ASYNC"), default=False),
        )


class HindsightLocalEmbeddedPublicClient:
    """Local Hindsight public-memory client backed by HindsightEmbedded.

    This keeps Hindsight as the donor implementation while Brainstack keeps
    proposal/admission/receipt authority. It is intentionally local-only:
    no cloud URL or secret is needed for the default Ollama route.
    """

    def __init__(self, config: HindsightLocalRuntimeConfig):
        if config.mode not in {"local", "local_embedded"}:
            raise ValueError(f"unsupported local Hindsight mode: {config.mode}")
        self.config = config
        self._client: Any | None = None
        self._manager: Any | None = None
        self._hermes_llm_proxy: Any | None = None

    def _hindsight_llm_settings(self) -> dict[str, str]:
        if self.config.llm_provider != HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER:
            return {
                "provider": self.config.llm_provider,
                "api_key": self.config.llm_api_key,
                "model": self.config.llm_model,
                "base_url": self.config.llm_base_url,
            }
        from .hindsight_hermes_llm_proxy import HermesManagedLLMProxy

        if self._hermes_llm_proxy is None:
            model = self.config.llm_model or _hermes_main_model()
            self._hermes_llm_proxy = HermesManagedLLMProxy(
                model=model,
                provider="main",
                timeout_seconds=float(self.config.timeout_seconds),
            ).start()
        return {
            "provider": "openai",
            "api_key": "brainstack-hermes-managed",
            "model": self.config.llm_model or _hermes_main_model() or "brainstack-hermes-managed",
            "base_url": self._hermes_llm_proxy.base_url,
        }

    def _get_client(self) -> Any:
        if self._client is None:
            llm = self._hindsight_llm_settings()
            try:
                from hindsight import HindsightEmbedded
            except Exception:
                self._client = self._start_slim_embedded_client()
            else:
                kwargs: dict[str, Any] = {
                    "profile": self.config.profile,
                    "llm_provider": llm["provider"],
                    "llm_api_key": llm["api_key"],
                    "llm_model": llm["model"],
                    "idle_timeout": self.config.idle_timeout_seconds,
                }
                if llm["base_url"]:
                    kwargs["llm_base_url"] = llm["base_url"]
                self._client = HindsightEmbedded(**kwargs)
        return self._client

    def _start_slim_embedded_client(self) -> Any:
        try:
            from hindsight_client import Hindsight
            from hindsight_embed.cli import get_embed_manager
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Hindsight local slim runtime is not installed") from exc
        llm = self._hindsight_llm_settings()
        config = {
            "HINDSIGHT_API_LLM_PROVIDER": llm["provider"],
            "HINDSIGHT_API_LLM_API_KEY": llm["api_key"],
            "HINDSIGHT_API_LLM_MODEL": llm["model"],
            "HINDSIGHT_API_LLM_BASE_URL": llm["base_url"],
            "HINDSIGHT_API_EMBEDDINGS_PROVIDER": self.config.embeddings_provider,
            "HINDSIGHT_API_EMBEDDINGS_TEI_URL": self.config.embeddings_tei_url,
            "HINDSIGHT_API_RERANKER_PROVIDER": self.config.reranker_provider,
            "HINDSIGHT_API_RETAIN_EXTRACTION_MODE": self.config.retain_extraction_mode,
            "HINDSIGHT_API_RETAIN_EXTRACT_CAUSAL_LINKS": str(
                self.config.retain_extract_causal_links
            ).lower(),
            "HINDSIGHT_API_LOG_LEVEL": "info",
            "HINDSIGHT_EMBED_DAEMON_IDLE_TIMEOUT": str(self.config.idle_timeout_seconds),
        }
        self._manager = get_embed_manager()
        if self.config.api_command:
            self._manager._find_api_command = lambda: [self.config.api_command]
        _repair_stale_hindsight_pg0_instance(self.config.profile)
        if not self._manager.ensure_running(config, self.config.profile):
            raise RuntimeError(f"Failed to start Hindsight local profile {self.config.profile!r}")
        return Hindsight(
            base_url=self._manager.get_url(self.config.profile),
            timeout=float(self.config.timeout_seconds),
        )

    def retain_memories(
        self,
        *,
        bank_id: str,
        items: list[Mapping[str, Any]],
        document_tags: list[str] | None = None,
        async_mode: bool = True,
    ) -> Mapping[str, Any]:
        response = self._get_client().retain_batch(
            bank_id=bank_id,
            items=[dict(item) for item in items],
            document_tags=document_tags,
            retain_async=async_mode,
        )
        data = dict(_response_to_mapping(response))
        data.setdefault("items_count", len(items))
        return data

    def trigger_consolidation(self, *, bank_id: str) -> Mapping[str, Any]:
        client = self._get_client()
        url = _hindsight_consolidation_url(client, bank_id)
        if not url:
            return {"status": "unavailable", "reason": "HINDSIGHT_CONSOLIDATION_API_MISSING"}
        return _post_hindsight_consolidation(url, timeout_seconds=self.config.timeout_seconds)

    def recall_memories(
        self,
        *,
        bank_id: str,
        query: str,
        budget: str = "low",
        max_tokens: int = 900,
        trace: bool = True,
        tags: list[str] | None = None,
    ) -> Mapping[str, Any]:
        response = self._get_client().recall(
            bank_id=bank_id,
            query=query,
            budget=budget,
            max_tokens=max_tokens,
            trace=trace,
            include_source_facts=True,
            tags=tags,
        )
        return _response_to_mapping(response)

    def close(self) -> None:
        if self._client is None:
            return
        if not _close_generated_hindsight_client(self._client):
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
        self._client = None
        if self._hermes_llm_proxy is not None:
            self._hermes_llm_proxy.close()
            self._hermes_llm_proxy = None


def build_local_hindsight_public_client(
    config: HindsightLocalRuntimeConfig | None = None,
) -> HindsightLocalEmbeddedPublicClient:
    return HindsightLocalEmbeddedPublicClient(config or HindsightLocalRuntimeConfig.from_env())


@dataclass(frozen=True)
class HindsightPublicApiBridge:
    client: HindsightPublicMemoryClient | None
    bank_id: str
    donor_version: str = ""
    budget: str = "low"
    max_tokens: int = 900
    trigger_consolidation: bool = True
    retain_async: bool = True

    def propose(self, source_batch: Mapping[str, Any]) -> dict[str, Any]:
        if self.client is None:
            return unavailable_proposal_action_batch(
                reason="HINDSIGHT_PUBLIC_CLIENT_UNCONFIGURED",
                donor_version=self.donor_version,
            )
        try:
            items = build_hindsight_retain_items(source_batch)
            retain_response: Mapping[str, Any] = {}
            if items:
                retain_response = self.client.retain_memories(
                    bank_id=self.bank_id,
                    items=items,
                    document_tags=["brainstack:tier2"],
                    async_mode=self.retain_async,
                )
            consolidation_response: Mapping[str, Any] = {}
            if self.trigger_consolidation:
                consolidation_response = self.client.trigger_consolidation(bank_id=self.bank_id)
            recall_response = self.client.recall_memories(
                bank_id=self.bank_id,
                query=build_hindsight_recall_query(source_batch),
                budget=self.budget,
                max_tokens=self.max_tokens,
                trace=True,
                tags=["brainstack:tier2"],
            )
        except Exception as exc:
            return unavailable_proposal_action_batch(
                reason=f"HINDSIGHT_PUBLIC_CLIENT_FAILED:{type(exc).__name__}",
                donor_version=self.donor_version,
            )
        return proposal_batch_from_hindsight_recall(
            recall_response=recall_response,
            source_batch=source_batch,
            retain_response=retain_response,
            consolidation_response=consolidation_response,
            donor_version=self.donor_version,
            config_hash=_hash_json(
                {
                    "bank_id": self.bank_id,
                    "budget": self.budget,
                    "max_tokens": self.max_tokens,
                    "trigger_consolidation": self.trigger_consolidation,
                    "retain_async": self.retain_async,
                }
            ),
        )
