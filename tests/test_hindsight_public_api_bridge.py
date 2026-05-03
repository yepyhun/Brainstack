from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
from typing import Any, Mapping

import brainstack.hindsight_public_api_bridge as bridge_module
from brainstack.hindsight_public_api_bridge import (
    DEFAULT_LOCAL_HINDSIGHT_BANK_ID,
    DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER,
    DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_TEI_URL,
    DEFAULT_LOCAL_HINDSIGHT_LLM_PROVIDER,
    DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER,
    DEFAULT_LOCAL_HINDSIGHT_RETAIN_EXTRACTION_MODE,
    HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER,
    HindsightLocalEmbeddedPublicClient,
    HindsightLocalRuntimeConfig,
    HindsightPublicMemoryClient,
    HindsightPublicApiBridge,
    build_hindsight_recall_query,
    build_hindsight_retain_items,
    proposal_batch_from_hindsight_recall,
)


def _source_batch() -> dict[str, Any]:
    return {
        "schema": "brainstack.hindsight_source_batch.v1",
        "session_id": "session-public",
        "scope": {
            "principal_scope_key": "principal-public",
            "workspace_scope_key": "workspace-public",
        },
        "source_spans": [
            {
                "source_span_id": "span-user-project",
                "source_event_id": "event-user-project",
                "speaker": "user",
                "text": "User explicitly states that Project Nova uses a graph memory layer.",
                "observed_at": "2026-04-30T10:00:00Z",
            }
        ],
    }


class FakeHindsightPublicClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.retained_items: list[Mapping[str, Any]] = []

    def retain_memories(
        self,
        *,
        bank_id: str,
        items: list[Mapping[str, Any]],
        document_tags: list[str] | None = None,
        async_mode: bool = True,
    ) -> Mapping[str, Any]:
        self.calls.append(f"retain:{bank_id}:{async_mode}:{','.join(document_tags or [])}")
        self.retained_items = items
        return {"success": True, "bank_id": bank_id, "items_count": len(items), "async": True, "operation_id": "op-retain"}

    def trigger_consolidation(self, *, bank_id: str) -> Mapping[str, Any]:
        self.calls.append(f"consolidate:{bank_id}")
        return {"operation_id": "op-consolidate"}

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
        self.calls.append(f"recall:{bank_id}:{budget}:{max_tokens}:{trace}:{','.join(tags or [])}")
        return {
            "results": [
                {
                    "id": "mem-graph-layer",
                    "text": "Project Nova uses a graph memory layer.",
                    "type": "observation",
                    "metadata": {
                        "source_span_id": "span-user-project",
                        "source_event_id": "event-user-project",
                        "assertion_speaker": "user",
                        "brainstack_target_kind": "project_fact",
                        "brainstack_target_slot": "project.architecture_claim",
                        "confidence": 0.92,
                    },
                    "source_fact_ids": ["fact-1"],
                    "entities": ["Project Nova"],
                    "tags": ["brainstack:tier2"],
                }
            ],
            "trace": {"donor": "hindsight"},
        }


class BrokenHindsightPublicClient(FakeHindsightPublicClient):
    def retain_memories(self, **_: Any) -> Mapping[str, Any]:
        raise RuntimeError("donor unavailable")


def test_local_hindsight_runtime_config_defaults_to_hermes_managed_llm(monkeypatch) -> None:
    monkeypatch.setattr(bridge_module, "_hermes_main_model", lambda: "")
    config = HindsightLocalRuntimeConfig.from_env({})

    assert config.mode == "local_embedded"
    assert config.bank_id == DEFAULT_LOCAL_HINDSIGHT_BANK_ID
    assert config.llm_provider == DEFAULT_LOCAL_HINDSIGHT_LLM_PROVIDER
    assert config.llm_provider == HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER
    assert config.llm_model == ""
    assert config.llm_base_url == ""
    assert config.llm_api_key == ""
    assert config.embeddings_provider == DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_PROVIDER
    assert config.embeddings_tei_url == DEFAULT_LOCAL_HINDSIGHT_EMBEDDINGS_TEI_URL
    assert config.reranker_provider == DEFAULT_LOCAL_HINDSIGHT_RERANKER_PROVIDER
    assert config.retain_extraction_mode == DEFAULT_LOCAL_HINDSIGHT_RETAIN_EXTRACTION_MODE
    assert config.retain_extract_causal_links is False
    assert config.retain_async is False


def test_hermes_managed_hindsight_runtime_config_uses_main_model(monkeypatch) -> None:
    monkeypatch.setattr(bridge_module, "_hermes_main_model", lambda: "gpt-5.5")

    config = HindsightLocalRuntimeConfig.from_env({})

    assert config.llm_provider == HERMES_MANAGED_HINDSIGHT_LLM_PROVIDER
    assert config.llm_model == "gpt-5.5"
    assert config.llm_base_url == ""


def test_local_hindsight_runtime_config_allows_explicit_local_override() -> None:
    config = HindsightLocalRuntimeConfig.from_env(
        {
            "BRAINSTACK_TIER2_HINDSIGHT_MODE": "local_embedded",
            "BRAINSTACK_TIER2_HINDSIGHT_BANK_ID": "custom-bank",
            "BRAINSTACK_TIER2_HINDSIGHT_PROFILE": "custom-profile",
            "BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER": "ollama",
            "BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL": "local-model",
            "BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
            "BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_PROVIDER": "tei",
            "BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL": "http://127.0.0.1:7997",
            "BRAINSTACK_TIER2_HINDSIGHT_RERANKER_PROVIDER": "rrf",
            "BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACTION_MODE": "concise",
            "BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACT_CAUSAL_LINKS": "true",
            "BRAINSTACK_TIER2_HINDSIGHT_API_COMMAND": "/custom/hindsight-api",
            "BRAINSTACK_TIER2_HINDSIGHT_TIMEOUT_SECONDS": "45",
            "BRAINSTACK_TIER2_HINDSIGHT_RETAIN_ASYNC": "true",
        }
    )

    assert config.bank_id == "custom-bank"
    assert config.profile == "custom-profile"
    assert config.llm_model == "local-model"
    assert config.llm_base_url == "http://127.0.0.1:11434/v1"
    assert config.embeddings_provider == "tei"
    assert config.embeddings_tei_url == "http://127.0.0.1:7997"
    assert config.reranker_provider == "rrf"
    assert config.retain_extraction_mode == "concise"
    assert config.retain_extract_causal_links is True
    assert config.api_command == "/custom/hindsight-api"
    assert config.timeout_seconds == 45
    assert config.retain_async is True


def test_local_hindsight_runtime_config_derives_tei_base_from_brainstack_embed_url() -> None:
    config = HindsightLocalRuntimeConfig.from_env(
        {"BRAINSTACK_EMBEDDINGS_URL": "http://127.0.0.1:7997/embed"}
    )

    assert config.embeddings_tei_url == "http://127.0.0.1:7997"


def test_public_client_protocol_accepts_fake_client() -> None:
    client: HindsightPublicMemoryClient = FakeHindsightPublicClient()

    response = client.retain_memories(bank_id="bank", items=[], async_mode=False)

    assert response["success"] is True


def test_async_donor_response_uses_shared_sync_event_loop(monkeypatch) -> None:
    async def _response() -> str:
        return "ok"

    def _fail_asyncio_run(_: Any) -> None:
        raise AssertionError("asyncio.run must not fork donor client loop")

    monkeypatch.setattr(bridge_module.asyncio, "run", _fail_asyncio_run)

    assert bridge_module._resolve_sync_response(_response()) == "ok"


def test_local_hindsight_client_closes_generated_session_on_own_loop() -> None:
    loop = asyncio.new_event_loop()

    class _FakePool:
        _loop = loop

    class _FakeRest:
        _pool_manager = _FakePool()

    class _FakeApiClient:
        rest_client = _FakeRest()
        closed = False

        async def close(self) -> None:
            self.closed = True

    class _FakeHindsight:
        _api_client = _FakeApiClient()

        def close(self) -> None:
            raise AssertionError("generated client must close on aiohttp session loop")

    client = HindsightLocalEmbeddedPublicClient(HindsightLocalRuntimeConfig())
    client._client = _FakeHindsight()
    try:
        client.close()
        assert client._client is None
        assert _FakeHindsight._api_client.closed is True
    finally:
        loop.close()


def test_local_hindsight_client_repairs_stale_pg0_stopping_pid(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pid_path = data_dir / "postmaster.pid"
    pid_path.write_text(
        "999999\n"
        f"{data_dir}\n"
        "1777587910\n"
        "65432\n"
        "/tmp\n"
        "localhost\n"
        "  3185589         0\n"
        "stopping\n",
        encoding="utf-8",
    )

    info = types.SimpleNamespace(running=True, port=65432, data_dir=str(data_dir))

    class _FakePg0:
        seen: list[dict[str, Any]] = []

        def __init__(self, **kwargs: Any) -> None:
            self.seen.append(dict(kwargs))

        def info(self) -> Any:
            return info

    monkeypatch.setitem(sys.modules, "pg0", types.SimpleNamespace(Pg0=_FakePg0))

    report = bridge_module._repair_stale_hindsight_pg0_instance("brainstack-tier2")

    assert report["status"] == "repaired"
    assert report["reason"] == "stale_pg0_postmaster_pid_moved"
    assert _FakePg0.seen[0]["name"] == "hindsight-embed-brainstack-tier2"
    assert not pid_path.exists()
    assert list(data_dir.glob("postmaster.pid.stale-*"))


def test_local_hindsight_client_triggers_consolidation_over_public_http(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeResponse:
        status = 202

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"operation_id":"op-public"}'

    class _FakeHindsight:
        _base_url = "http://127.0.0.1:9727/v1/default"

    def _fake_urlopen(request: Any, *, timeout: int) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(bridge_module.urllib_request, "urlopen", _fake_urlopen)
    client = HindsightLocalEmbeddedPublicClient(HindsightLocalRuntimeConfig(timeout_seconds=17))
    client._client = _FakeHindsight()

    response = client.trigger_consolidation(bank_id="bank one")

    assert captured == {
        "url": "http://127.0.0.1:9727/v1/default/banks/bank%20one/consolidate",
        "method": "POST",
        "timeout": 17,
    }
    assert response["http_status"] == 202
    assert response["operation_id"] == "op-public"


def test_retain_items_preserve_source_metadata_without_private_payload_in_metadata() -> None:
    items = build_hindsight_retain_items(_source_batch())

    assert len(items) == 1
    assert items[0]["content"].startswith("User explicitly states")
    assert items[0]["metadata"]["source_span_id"] == "span-user-project"
    assert items[0]["metadata"]["source_event_id"] == "event-user-project"
    assert items[0]["metadata"]["source_text_hash"].startswith("sha256:")
    assert "User explicitly states" not in str(items[0]["metadata"])


def test_recall_query_uses_source_text_for_donor_recall() -> None:
    query = build_hindsight_recall_query(_source_batch())

    assert "Project Nova" in query
    assert len(query) <= 1200


def test_public_bridge_calls_hindsight_public_methods_and_returns_proposal_batch() -> None:
    client = FakeHindsightPublicClient()
    batch = HindsightPublicApiBridge(client=client, bank_id="bank-public", donor_version="hindsight-test").propose(
        _source_batch()
    )

    assert client.calls == [
        "retain:bank-public:True:brainstack:tier2",
        "consolidate:bank-public",
        "recall:bank-public:low:900:True:brainstack:tier2",
    ]
    assert batch["schema"] == "brainstack.hindsight_proposal_action_batch.v1"
    assert batch["status"] == "ok"
    assert batch["donor"] == "hindsight"
    assert batch["donor_version"] == "hindsight-test"
    assert batch["adapter_version"] == "brainstack.hindsight_public_api_bridge.v1"
    assert batch["actions"][0]["target_kind"] == "project_fact"
    assert batch["actions"][0]["source_span_ids"] == ["span-user-project"]
    assert batch["actions"][0]["source_event_ids"] == ["event-user-project"]
    assert batch["critical_counters"]["missing_source_refs"] == 0
    assert "Project Nova uses a graph memory layer." not in str(batch)


def test_public_bridge_can_run_deterministic_sync_retain_for_shadow_probe() -> None:
    client = FakeHindsightPublicClient()
    batch = HindsightPublicApiBridge(
        client=client,
        bank_id="bank-public",
        donor_version="hindsight-test",
        retain_async=False,
    ).propose(_source_batch())

    assert "retain:bank-public:False:brainstack:tier2" in client.calls
    assert batch["status"] == "ok"


def test_public_bridge_missing_verified_source_ref_degrades_to_inspectable_proposal() -> None:
    recall_response = {
        "results": [
            {
                "id": "mem-no-source",
                "text": "Unverified donor observation.",
                "type": "observation",
                "metadata": {"assertion_speaker": "unknown"},
                "source_fact_ids": ["hindsight-fact"],
            }
        ]
    }

    batch = proposal_batch_from_hindsight_recall(
        recall_response=recall_response,
        source_batch=_source_batch(),
        donor_version="hindsight-test",
    )

    assert batch["status"] == "degraded"
    assert batch["actions"] == []
    assert batch["critical_counters"]["missing_source_refs"] == 0
    assert batch["failure"] == {
        "reason_code": "HINDSIGHT_UNVERIFIED_RECALL_DROPPED",
        "dropped_unsourced_candidates": 1,
    }


def test_public_bridge_drops_assistant_authored_recall_actions() -> None:
    source_batch = _source_batch()
    source_batch["source_spans"].append(
        {
            "source_span_id": "span-assistant-noise",
            "source_event_id": "event-assistant-noise",
            "speaker": "assistant",
            "assertion_speaker": "assistant",
            "text": "Assistant claims it saved a project secret without user evidence.",
            "observed_at": "2026-04-30T10:01:00Z",
        }
    )
    recall_response = {
        "results": [
            {
                "id": "mem-assistant-noise",
                "text": "Assistant claims it saved a project secret.",
                "type": "observation",
                "metadata": {
                    "source_span_id": "span-assistant-noise",
                    "source_event_id": "event-assistant-noise",
                    "assertion_speaker": "assistant",
                    "brainstack_target_kind": "project_fact",
                },
            }
        ]
    }

    batch = proposal_batch_from_hindsight_recall(
        recall_response=recall_response,
        source_batch=source_batch,
        donor_version="hindsight-test",
    )

    assert batch["status"] == "degraded"
    assert batch["actions"] == []
    assert batch["critical_counters"]["assistant_authored_actions"] == 0
    assert batch["failure"] == {
        "reason_code": "HINDSIGHT_ASSISTANT_AUTHORED_ACTION_DROPPED",
        "dropped_assistant_authored_actions": 1,
    }


def test_public_bridge_client_failure_is_explicitly_unavailable() -> None:
    batch = HindsightPublicApiBridge(
        client=BrokenHindsightPublicClient(),
        bank_id="bank-public",
        donor_version="hindsight-test",
    ).propose(_source_batch())

    assert batch["status"] == "unavailable"
    assert batch["failure"]["reason_code"] == "HINDSIGHT_PUBLIC_CLIENT_FAILED:RuntimeError"
    assert batch["actions"] == []
