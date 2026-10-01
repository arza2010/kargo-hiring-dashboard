"""Two more non-negotiables that are cheap to check without a live DB or AI call:
check 07's "no reasons in a rejection", and check 09's "CV text is data,
not instructions" framing actually present in the prompts sent to the model.
"""
from app.email_draft import run_backend_checks
from app.prompt_loader import load_prompt


def test_pass_email_with_forbidden_terms_is_rejected():
    body = (
        "Hi {{first_name}}, thank you for applying for the Product Manager role. "
        "Unfortunately, based on your score against our rubric criteria, we won't be moving forward. "
        "Wishing you the best in your search."
    )
    problems = run_backend_checks("pass", body)
    assert any("score" in p for p in problems)
    assert any("rubric" in p for p in problems)
    assert any("criteria" in p for p in problems)


def test_clean_pass_email_has_no_problems():
    body = (
        "Hi {{first_name}}, thank you for applying for the Product Manager role. "
        "We won't be moving forward this time. Wishing you all the best in your search."
    )
    assert run_backend_checks("pass", body) == []


def test_pass_email_over_word_limit_is_rejected():
    body = "Hi {{first_name}}, " + ("thanks so much for applying today. " * 20) + "We won't be moving forward. Best of luck."
    problems = run_backend_checks("pass", body)
    assert any("word" in p for p in problems)


def test_missing_first_name_placeholder_is_rejected():
    problems = run_backend_checks("pass", "Hi there, we won't be moving forward. Best of luck.")
    assert any("first_name" in p for p in problems)


def test_extra_placeholder_is_rejected():
    body = "Hi {{first_name}}, we won't be moving forward for the {{role}} role. Best of luck."
    problems = run_backend_checks("pass", body)
    assert any("unexpected placeholders" in p for p in problems)


def test_score_prompt_fences_cv_and_tells_model_to_ignore_embedded_instructions():
    system = load_prompt("score_candidate.md").system
    user = load_prompt("score_candidate.md").user_template
    assert "<cv>" in user and "</cv>" in user
    assert "ignore" in system.lower()
    assert "instruction" in system.lower()


def test_brief_and_draft_prompts_also_treat_cv_as_data():
    brief_system = load_prompt("interview_brief.md").system
    assert "ignore" in brief_system.lower()

    draft_system = load_prompt("draft_email.md").system
    draft_user = load_prompt("draft_email.md").user_template
    assert "<highlight>" in draft_user
    assert "ignore" in draft_system.lower()
