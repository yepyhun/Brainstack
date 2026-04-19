# ruff: noqa: E402
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.graph_evidence import extract_graph_evidence_from_text


def test_legacy_graph_ingress_ignores_broad_role_like_sentences():
    evidence_items = extract_graph_evidence_from_text("Do you think his rejection is a defense mechanism?")
    assert evidence_items == []


def test_legacy_graph_ingress_keeps_status_and_location_patterns():
    evidence_items = extract_graph_evidence_from_text("Project Atlas is active now. Laura is in Budapest.")
    assert any(item.kind == "state" and item.attribute == "status" for item in evidence_items)
    assert any(item.kind == "state" and item.attribute == "location" for item in evidence_items)
