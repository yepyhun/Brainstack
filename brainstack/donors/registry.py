from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class DonorSpec:
    key: str
    role: str
    strategy: str
    upstream: str
    baseline: str
    local_adapter: str
    local_owner: str
    smoke_tests: tuple[str, ...]
    notes: str = ""

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["smoke_tests"] = list(self.smoke_tests)
        return data


DONOR_REGISTRY: Dict[str, DonorSpec] = {
    "continuity": DonorSpec(
        key="continuity",
        role="recency, continuity, transcript snapshots",
        strategy="donor-pattern-behind-local-adapter",
        upstream="hindsight + hermes-lcm transcript pattern",
        baseline="local-pattern adoption only",
        local_adapter="brainstack/donors/continuity_adapter.py",
        local_owner="Brainstack continuity shelf",
        smoke_tests=(
            "tests/test_brainstack_donor_boundaries.py::TestBrainstackDonorBoundaries::test_provider_sync_turn_uses_donor_continuity_adapter",
            "tests/test_brainstack_donor_boundaries.py::TestBrainstackDonorBoundaries::test_provider_on_pre_compress_uses_donor_snapshot_adapter",
            "tests/test_brainstack_transcript_shelf.py",
        ),
        notes="Pattern donor only. No parallel runtime is allowed.",
    ),
    "graph_truth": DonorSpec(
        key="graph_truth",
        role="entities, relations, temporal truth, conflicts",
        strategy="donor-pattern-behind-local-adapter",
        upstream="graphiti",
        baseline="reviewed local baseline",
        local_adapter="brainstack/donors/graph_adapter.py",
        local_owner="Brainstack graph-truth shelf",
        smoke_tests=(
            "tests/test_brainstack_donor_boundaries.py::TestBrainstackDonorBoundaries::test_provider_sync_turn_uses_donor_graph_adapter",
            "tests/test_brainstack_donor_boundaries.py::TestBrainstackDonorBoundaries::test_provider_on_session_end_uses_donor_snapshot_and_graph_adapters",
            "tests/test_brainstack_real_world_flows.py::TestBrainstackRealWorldFlows::test_temporal_graph_truth_shows_current_and_prior_state",
        ),
    ),
    "corpus": DonorSpec(
        key="corpus",
        role="document ingestion, sectioning, bounded corpus recall",
        strategy="adapter-seam-with-upstream-baseline",
        upstream="mempalace",
        baseline="latest upstream donor baseline tracked manually",
        local_adapter="brainstack/donors/corpus_adapter.py",
        local_owner="Brainstack corpus shelf",
        smoke_tests=(
            "tests/test_brainstack_donor_boundaries.py::TestBrainstackDonorBoundaries::test_provider_ingest_corpus_document_uses_donor_corpus_adapter",
            "tests/test_brainstack_real_world_flows.py::TestBrainstackRealWorldFlows::test_corpus_recall_returns_relevant_bounded_document_sections",
        ),
        notes="This layer is the strongest future candidate for fuller upstream alignment.",
    ),
}


def get_donor_registry() -> Dict[str, DonorSpec]:
    return DONOR_REGISTRY


def list_donor_specs() -> List[DonorSpec]:
    return [DONOR_REGISTRY[key] for key in sorted(DONOR_REGISTRY)]
