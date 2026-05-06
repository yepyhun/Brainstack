from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .background_task_binding import build_background_task_status


TIER2_RUNTIME_ROUTE_SCHEMA = "brainstack.tier2_runtime_route.v1"
TIER2_RUNTIME_SPINE_SCHEMA = "brainstack.tier2_runtime_spine.v1"
TIER2_INTERNAL_EXTRACTOR = "internal_extractor"
TIER2_HINDSIGHT_PUBLIC_API_BRIDGE = "hindsight_public_api_bridge"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True)
class Tier2RuntimeSpine:
    runtime: str
    actual_worker_path: str
    binding_status: str
    binding_reason_code: str
    runtime_invoked_by_worker: bool
    mode: str
    hindsight_mode: str
    llm_provider: str
    configured_model: str
    effective_model: str
    effective_model_source: str
    configured_base_url_present: bool
    background_task_status: Mapping[str, Any]

    @property
    def worker_callable(self) -> bool:
        return self.binding_status in {"bound", "test_extractor_override"}

    @property
    def configured_runtime_equals_worker_path(self) -> bool:
        return self.runtime == self.actual_worker_path or self.binding_status == "test_extractor_override"

    def worker_block_reason(self) -> str:
        if self.binding_status == "configured_unbound":
            return (
                "Tier-2 runtime is configured as hindsight_public_api_bridge, "
                "but no Hindsight worker binding is installed."
            )
        if not self.worker_callable:
            return "Tier-2 runtime is not callable through the configured worker spine."
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TIER2_RUNTIME_ROUTE_SCHEMA,
            "runtime_spine_schema": TIER2_RUNTIME_SPINE_SCHEMA,
            "runtime": self.runtime,
            "actual_worker_path": self.actual_worker_path,
            "binding_status": self.binding_status,
            "binding_reason_code": self.binding_reason_code,
            "runtime_invoked_by_worker": self.runtime_invoked_by_worker,
            "configured_runtime_equals_worker_path": self.configured_runtime_equals_worker_path,
            "worker_callable": self.worker_callable,
            "mode": self.mode,
            "hindsight_mode": self.hindsight_mode,
            "llm_provider": self.llm_provider or "default",
            "configured_model": self.configured_model,
            "effective_model": self.effective_model,
            "effective_model_source": self.effective_model_source,
            "configured_base_url_present": self.configured_base_url_present,
            "uses_legacy_gpt_5_2_codex": (
                self.effective_model == "gpt-5.2-codex"
                or self.configured_model == "gpt-5.2-codex"
            ),
            "background_task_status": dict(self.background_task_status or {}),
            "model_answer": (
                f"Tier2 current route uses {self.effective_model} via {self.llm_provider or 'default provider'}."
                if self.effective_model
                else "Tier2 current route model is not resolved in this process."
            ),
        }


def _effective_hindsight_model(*, provider: str, configured_model: str) -> tuple[str, str]:
    if provider == "hermes_managed" and not configured_model:
        try:
            from .hindsight_public_api_bridge import _hermes_main_model

            return _text(_hermes_main_model()), "hermes_main_model"
        except Exception:
            return "", "unavailable"
    return configured_model, "brainstack_config"


def build_tier2_runtime_spine(config: Mapping[str, Any] | None) -> Tier2RuntimeSpine:
    cfg = config if isinstance(config, Mapping) else {}
    runtime = _text(cfg.get("tier2_runtime")) or TIER2_INTERNAL_EXTRACTOR
    mode = _text(cfg.get("tier2_mode")) or "unknown"
    hindsight_mode = _text(cfg.get("tier2_hindsight_mode"))
    llm_provider = _text(cfg.get("tier2_hindsight_llm_provider"))
    configured_model = _text(cfg.get("tier2_hindsight_llm_model"))
    configured_base_url = _text(cfg.get("tier2_hindsight_llm_base_url"))
    effective_model, effective_model_source = _effective_hindsight_model(
        provider=llm_provider,
        configured_model=configured_model,
    )
    extractor_override = callable(cfg.get("_tier2_extractor"))
    if runtime == TIER2_HINDSIGHT_PUBLIC_API_BRIDGE:
        binding_status = "configured_unbound"
        binding_reason_code = "TIER2_HINDSIGHT_PUBLIC_API_BRIDGE_UNBOUND"
        actual_worker_path = TIER2_INTERNAL_EXTRACTOR
        runtime_invoked_by_worker = False
        if extractor_override:
            binding_status = "test_extractor_override"
            binding_reason_code = "TIER2_TEST_EXTRACTOR_OVERRIDE_NOT_RUNTIME_BINDING"
            actual_worker_path = "test_injected_extractor"
    else:
        runtime = TIER2_INTERNAL_EXTRACTOR
        binding_status = "bound"
        binding_reason_code = "TIER2_INTERNAL_EXTRACTOR_BOUND"
        actual_worker_path = "test_injected_extractor" if extractor_override else TIER2_INTERNAL_EXTRACTOR
        runtime_invoked_by_worker = True
    return Tier2RuntimeSpine(
        runtime=runtime,
        actual_worker_path=actual_worker_path,
        binding_status=binding_status,
        binding_reason_code=binding_reason_code,
        runtime_invoked_by_worker=runtime_invoked_by_worker,
        mode=mode,
        hindsight_mode=hindsight_mode,
        llm_provider=llm_provider,
        configured_model=configured_model,
        effective_model=effective_model,
        effective_model_source=effective_model_source,
        configured_base_url_present=bool(configured_base_url),
        background_task_status=build_background_task_status(cfg),
    )


def build_tier2_runtime_route_status(config: Mapping[str, Any] | None) -> dict[str, Any]:
    return build_tier2_runtime_spine(config).to_dict()
