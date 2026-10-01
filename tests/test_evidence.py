from app.evidence import normalise, quote_found, verify_all, verify_criterion

CLEANED_TEXT = (
    "Led engineer on the core freight tracking platform, serving 40+ freight "
    "forwarder clients. Designed and built a Bill of Lading verification module."
)


def test_real_quote_is_verified():
    c = {"level": 3, "evidence": "Led engineer on the core freight tracking platform", "status": "evidenced"}
    result = verify_criterion(c, CLEANED_TEXT)
    assert result["status"] == "evidenced"
    assert result["level"] == 3


def test_fabricated_quote_becomes_level_0_unverified():
    c = {"level": 4, "evidence": "Personally negotiated a merger with a Fortune 500 company", "status": "evidenced"}
    result = verify_criterion(c, CLEANED_TEXT)
    assert result["level"] == 0
    assert result["status"] == "unverified"
    # original quote is kept so Arjun can see what the model claimed
    assert result["evidence"] == "Personally negotiated a merger with a Fortune 500 company"


def test_level_0_with_no_evidence_stays_not_evidenced():
    c = {"level": 0, "evidence": None, "status": "not_evidenced"}
    result = verify_criterion(c, CLEANED_TEXT)
    assert result["level"] == 0
    assert result["status"] == "not_evidenced"


def test_normalisation_tolerates_whitespace_and_punctuation():
    quote = "Led  engineer, on the core freight-tracking platform!"
    assert normalise(quote) != quote
    # punctuation/whitespace differences alone shouldn't fail a real quote
    c = {"level": 2, "evidence": "Led   engineer on the core freight tracking, platform", "status": "evidenced"}
    result = verify_criterion(c, CLEANED_TEXT)
    assert result["status"] == "evidenced"


def test_quote_found_helper():
    assert quote_found("Bill of Lading verification module", CLEANED_TEXT)
    assert not quote_found("Bill of Lading approval committee", CLEANED_TEXT)
    assert not quote_found(None, CLEANED_TEXT)
    assert not quote_found("", CLEANED_TEXT)


def test_verify_all_verifies_each_criterion_independently():
    criteria = {
        "C1": {"level": 3, "evidence": "Led engineer on the core freight tracking platform", "status": "evidenced"},
        "C2": {"level": 4, "evidence": "fabricated quote that does not exist anywhere", "status": "evidenced"},
    }
    result = verify_all(criteria, CLEANED_TEXT)
    assert result["C1"]["status"] == "evidenced"
    assert result["C2"]["status"] == "unverified"
    assert result["C2"]["level"] == 0
