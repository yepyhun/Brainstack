from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from plugins.memory.brainstack.donors.registry import DonorSpec


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "brainstack_refresh_donors.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("brainstack_refresh_donors_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_refresh_report_rejects_unknown_donor_key():
    module = _load_module()
    with pytest.raises(ValueError, match="Unknown donor key"):
        module._build_report(selected={"missing-donor"}, run_smoke=False)


def test_refresh_report_rejects_adapter_path_escape(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "list_donor_specs",
        lambda: [
            DonorSpec(
                key="escape",
                role="bad adapter",
                strategy="invalid",
                upstream="none",
                baseline="none",
                local_adapter="../escape.py",
                local_owner="test",
                smoke_tests=(),
                notes="",
            )
        ],
    )
    with pytest.raises(ValueError, match="escapes repo root"):
        module._build_report(selected=None, run_smoke=False)
