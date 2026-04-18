from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_brainstack_phase29_obedience_quality.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("brainstack_phase29_obedience_quality", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load script: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_startup_smalltalk_checker_fails_on_observed_generic_followup_style():
    module = _load_script()
    scenario = next(item for item in module.SCENARIOS if item.name == "startup_smalltalk_after_reset")

    answer = "Persze Tomi, itt vagyok.\n\nMire gondolsz — mit akarsz megbeszélni?"
    evaluation = module._evaluate_answer(scenario, answer)

    assert evaluation["passed"] is False
    assert "no_dash_punctuation" in evaluation["missing"]
    assert "no_generic_followup_question" in evaluation["missing"]


def test_startup_smalltalk_checker_accepts_compact_hungarian_acknowledgement():
    module = _load_script()
    scenario = next(item for item in module.SCENARIOS if item.name == "startup_smalltalk_after_reset")

    answer = "Szia Tomi.\nItt vagyok."
    evaluation = module._evaluate_answer(scenario, answer)

    assert evaluation == {
        "passed": True,
        "quality_class": "strong_pass",
        "missing": [],
    }


def test_ordinary_help_checker_requires_multiline_and_mechanical_cleanliness():
    module = _load_script()
    scenario = next(item for item in module.SCENARIOS if item.name == "ordinary_help_after_reset")

    one_line = "Pihenj kicsit ma délután és igyál vizet."
    evaluation = module._evaluate_answer(scenario, one_line)
    assert evaluation["passed"] is False
    assert "multiline_structure" in evaluation["missing"]

    multiline = "Pihenj húsz percet.\nMenj egy rövid sétára."
    good = module._evaluate_answer(scenario, multiline)
    assert good["passed"] is True
    assert good["quality_class"] == "strong_pass"


def test_phase29_matrix_targets_ordinary_prompts_not_rule_recall_only():
    module = _load_script()

    assert any(item.use_reset for item in module.SCENARIOS)
    assert all("szabály" not in item.final_question.lower() for item in module.SCENARIOS)
    assert {item.evaluator for item in module.SCENARIOS} == {"startup_smalltalk", "ordinary_help"}
