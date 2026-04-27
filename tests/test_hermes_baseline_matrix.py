from __future__ import annotations

from scripts.run_hermes_baseline_matrix import build_matrix


def test_baseline_matrix_classifies_missing_paths_as_invalid_fixture(tmp_path) -> None:
    native = tmp_path / "native"
    brainstack = tmp_path / "brainstack"
    brainstack.mkdir()

    matrix = build_matrix(native, brainstack)
    probes = {item["probe_id"]: item for item in matrix["probes"]}

    assert probes["173-native-boot"]["status"] == "invalid_fixture"
    assert probes["173-brainstack-boot"]["status"] == "pass"

