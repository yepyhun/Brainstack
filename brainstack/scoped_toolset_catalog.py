"""Scoped toolset capability catalog and escalation contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


SCHEMA_VERSION = "brainstack.scoped_toolset_catalog.v1"


@dataclass(frozen=True)
class ToolsetProfile:
    name: str
    purpose: str
    capabilities: tuple[str, ...]
    unavailable_by_default: tuple[str, ...]
    escalation_allowed: bool
    risk_class: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        data["unavailable_by_default"] = list(self.unavailable_by_default)
        return data


PROFILES: dict[str, ToolsetProfile] = {
    "read_only_audit": ToolsetProfile(
        name="read_only_audit",
        purpose="Inspect files, logs, sessions, and reports without mutation.",
        capabilities=("file.read", "search", "log.inspect", "brainstack.inspect"),
        unavailable_by_default=("file.write", "release", "docker.restart", "external.post"),
        escalation_allowed=True,
        risk_class="low",
    ),
    "code_edit": ToolsetProfile(
        name="code_edit",
        purpose="Read, edit, and test source code in the current workspace.",
        capabilities=("file.read", "file.write", "search", "test.run", "lint.run"),
        unavailable_by_default=("release", "docker.restart", "external.post"),
        escalation_allowed=True,
        risk_class="medium",
    ),
    "release_wizard": ToolsetProfile(
        name="release_wizard",
        purpose="Run release checklist, installer, wizard, and version parity checks.",
        capabilities=("file.read", "file.write", "test.run", "installer.run", "release.check"),
        unavailable_by_default=("external.post",),
        escalation_allowed=True,
        risk_class="high",
    ),
    "cron_script_only": ToolsetProfile(
        name="cron_script_only",
        purpose="Run bounded local scripts without calling an LLM executor.",
        capabilities=("script.run", "health.write", "state.inspect"),
        unavailable_by_default=("llm.execute", "external.post", "release"),
        escalation_allowed=False,
        risk_class="low",
    ),
    "kanban_orchestration": ToolsetProfile(
        name="kanban_orchestration",
        purpose="Inspect and update durable work items through the Hermes Kanban surface.",
        capabilities=("kanban.read", "kanban.write", "state.inspect", "fanout.plan"),
        unavailable_by_default=("release", "docker.restart", "external.post"),
        escalation_allowed=True,
        risk_class="medium",
    ),
    "memory_diagnosis": ToolsetProfile(
        name="memory_diagnosis",
        purpose="Diagnose Brainstack memory, graph, corpus, recall, and provenance behavior.",
        capabilities=("brainstack.inspect", "brainstack.recall", "db.inspect", "file.read"),
        unavailable_by_default=("memory.destructive_write", "release", "docker.restart"),
        escalation_allowed=True,
        risk_class="medium",
    ),
    "full_debug": ToolsetProfile(
        name="full_debug",
        purpose="Escalated broad debugging mode for cross-boundary incidents.",
        capabilities=("file.read", "file.write", "search", "terminal", "test.run", "docker.inspect"),
        unavailable_by_default=("external.post", "release.publish"),
        escalation_allowed=True,
        risk_class="high",
    ),
}


def get_toolset_profile(name: str) -> ToolsetProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown toolset profile: {name}") from exc


def build_agent_capability_catalog(profile_name: str) -> dict[str, Any]:
    profile = get_toolset_profile(profile_name)
    return {
        "schema": SCHEMA_VERSION,
        "profile": profile.name,
        "purpose": profile.purpose,
        "current_capabilities": list(profile.capabilities),
        "not_available_by_default": list(profile.unavailable_by_default),
        "escalation": {
            "allowed": profile.escalation_allowed,
            "instruction": (
                "If a missing capability is necessary, emit an escalation request with capability, reason, risk, and fallback."
                if profile.escalation_allowed
                else "This profile cannot escalate; write a degraded status instead of pretending the capability exists."
            ),
        },
        "risk_class": profile.risk_class,
        "capability_shrunk": False,
    }


def validate_escalation_request(
    request: Mapping[str, Any],
    *,
    current_profile: str,
) -> dict[str, Any]:
    profile = get_toolset_profile(current_profile)
    required = ("capability", "reason", "risk_class", "fallback_if_denied")
    missing = [key for key in required if not str(request.get(key) or "").strip()]
    capability = str(request.get("capability") or "")
    already_available = capability in profile.capabilities
    allowed = profile.escalation_allowed and not missing and not already_available
    reasons: list[str] = []
    if not profile.escalation_allowed:
        reasons.append("PROFILE_ESCALATION_DISABLED")
    if missing:
        reasons.append("MISSING_REQUIRED_FIELDS")
    if already_available:
        reasons.append("CAPABILITY_ALREADY_AVAILABLE")
    return {
        "schema": "brainstack.toolset_escalation_request.v1",
        "verdict": "valid" if allowed else "invalid",
        "current_profile": current_profile,
        "allowed": allowed,
        "reason_codes": reasons,
    }

