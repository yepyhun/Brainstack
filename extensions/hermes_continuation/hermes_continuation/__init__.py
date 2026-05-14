"""Optional Hermes continuation extension.

This package is intentionally separate from the Brainstack memory kernel. It
contains side-effect-free decision contracts that a Hermes runtime adapter can
use to decide whether work should continue, split, verify, repair, learn, wait,
or ask for a human gate.
"""

from .control_contract import build_continuation_control_contract, build_frontier_continuation_contract
from .capability import validate_capability_assignment, validate_completion_proof
from .engine import build_autonomy_continuation_decision, build_autonomy_runtime_adapter_contract
from .trace_replay import build_checkpoint, render_replay_summary, replay_decision_trace, validate_decision_trace
from .work_graph import validate_work_graph
from .work_state import build_durable_work_state_contract, durable_work_state_summary

__all__ = [
    "build_autonomy_continuation_decision",
    "build_autonomy_runtime_adapter_contract",
    "build_checkpoint",
    "build_continuation_control_contract",
    "build_durable_work_state_contract",
    "build_frontier_continuation_contract",
    "durable_work_state_summary",
    "render_replay_summary",
    "replay_decision_trace",
    "validate_capability_assignment",
    "validate_completion_proof",
    "validate_decision_trace",
    "validate_work_graph",
]
