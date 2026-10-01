from app.rubric import WEIGHTS
from app.scoring import finalize_score


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def _raw(levels: dict[str, int], pm_years=3.0) -> dict:
    criteria = {
        k: {"level": levels[k], "evidence": "some evidence line" if levels[k] > 0 else None,
            "status": "evidenced" if levels[k] > 0 else "not_evidenced"}
        for k in ("C1", "C2", "C3", "C4", "C5_PM", "C5_SPM")
    }
    return {
        "criteria": criteria,
        "pm_years_from_cv": pm_years,
        "probes": [],
        "one_line_rationale": "test",
        "injection_detected": False,
    }


def test_perfect_score_is_100():
    raw = _raw({"C1": 4, "C2": 4, "C3": 4, "C4": 4, "C5_PM": 4, "C5_SPM": 4})
    cleaned = "some evidence line " * 6
    result = finalize_score(raw, cleaned)
    assert result["pm_score"] == 100.0
    assert result["spm_score"] == 100.0


def test_formula_matches_hand_calculation():
    # C1=4 C2=2 C3=0 C4=3 C5_PM=1 C5_SPM=4
    raw = _raw({"C1": 4, "C2": 2, "C3": 0, "C4": 3, "C5_PM": 1, "C5_SPM": 4})
    cleaned = "some evidence line " * 6
    result = finalize_score(raw, cleaned)
    expected_pm = 30 * 4 / 4 + 20 * 2 / 4 + 15 * 0 / 4 + 10 * 3 / 4 + 25 * 1 / 4
    expected_spm = 30 * 4 / 4 + 20 * 2 / 4 + 15 * 0 / 4 + 10 * 3 / 4 + 25 * 4 / 4
    assert result["pm_score"] == round(expected_pm, 2)
    assert result["spm_score"] == round(expected_spm, 2)


def test_level_hint_true_when_gap_is_10_or_more():
    raw = _raw({"C1": 4, "C2": 4, "C3": 4, "C4": 4, "C5_PM": 0, "C5_SPM": 4})
    cleaned = "some evidence line " * 6
    result = finalize_score(raw, cleaned)
    assert abs(result["pm_score"] - result["spm_score"]) >= 10
    assert result["level_hint"] is True


def test_level_hint_false_when_gap_is_small():
    raw = _raw({"C1": 4, "C2": 4, "C3": 4, "C4": 4, "C5_PM": 4, "C5_SPM": 3})
    cleaned = "some evidence line " * 6
    result = finalize_score(raw, cleaned)
    assert result["level_hint"] is False


def test_years_flag_ranges():
    from app.rubric import years_flag_for

    assert years_flag_for(None) == "unclear"
    assert years_flag_for(3) == "within PM range"
    assert years_flag_for(6) == "within SPM range"
    assert years_flag_for(0.5) == "outside both"
    assert years_flag_for(20) == "outside both"
