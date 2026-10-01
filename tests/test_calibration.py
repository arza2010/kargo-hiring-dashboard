"""Live calibration test (Gemini). Reproduces rubric Part C by scoring the
8 PII-stripped hire CVs on C1-C4 and comparing against the hand scores.

Requires GEMINI_API_KEY / GEMINI_MODEL in the environment. Run with:
    pytest tests/test_calibration.py -m live -q -s
"""
import json
from pathlib import Path

import pytest

from app.ingest import ingest_file
from app.scoring import score_candidate

pytestmark = pytest.mark.live

HIRES_DIR = Path(__file__).resolve().parent.parent / "data" / "hires"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hire_ratings.json"


@pytest.fixture(scope="module")
def hand_ratings():
    data = json.loads(FIXTURES.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


@pytest.fixture(scope="module")
def model_results(hand_ratings):
    results = {}
    for filename in hand_ratings:
        path = HIRES_DIR / filename
        row = ingest_file(path, source="hire")
        assert row["parse_status"] == "ok", f"{filename}: {row['parse_notes']}"
        scored = score_candidate("PM", row["cleaned_text"])
        c = scored["criteria"]
        total_75 = sum(
            {"C1": 30, "C2": 20, "C3": 15, "C4": 10}[k] * c[k]["level"] / 4
            for k in ("C1", "C2", "C3", "C4")
        )
        results[filename] = {"criteria": c, "total_75": round(total_75, 2)}
    return results


def test_calibration_separates_exceeds_from_the_rest(hand_ratings, model_results):
    exceeds_totals = [
        model_results[f]["total_75"] for f, r in hand_ratings.items() if r["rating"] == "Exceeds"
    ]
    non_exceeds_totals = [
        model_results[f]["total_75"] for f, r in hand_ratings.items() if r["rating"] != "Exceeds"
    ]

    print("\nPer-criterion comparison (model vs hand), out of 75:\n")
    for filename, hand in hand_ratings.items():
        m = model_results[filename]
        print(f"{filename}  rating={hand['rating']}  hand_total={hand['total']}  model_total={m['total_75']}")
        for k in ("C1", "C2", "C3", "C4"):
            mc = m["criteria"][k]
            print(f"    {k}: hand={hand['hand'][k]} model={mc['level']} status={mc['status']} evidence={mc['evidence']!r}")

    assert min(exceeds_totals) > max(non_exceeds_totals), (
        f"lowest Exceeds total ({min(exceeds_totals)}) is not above "
        f"highest non-Exceeds total ({max(non_exceeds_totals)})"
    )
