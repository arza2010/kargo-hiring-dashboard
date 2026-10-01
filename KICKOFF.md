# Kickoff: paste these into Claude Code, one at a time

**Before you start:**

1. Put the 60 application CVs in `data/applications/`.
2. Copy `.env.example` to `.env` and fill it in.
3. Open a terminal in this folder and run `claude`.

After each milestone, read what it built, run the app yourself, and only then
paste the next prompt.

---

## Prompt 0: plan (no code yet)

```
Read CLAUDE.md fully, then rubric/kargo_pm_spm_rubric.txt and every file in prompts/.

Then:
1. Inspect data/applications, data/hires and data/jds. Report file counts and
   formats, and flag anything that can't be parsed (legacy .doc, scans, images).
2. Tell me how the applied role (PM or SPM) can be worked out for each
   application. If you can't tell from the files, ask me. Don't guess.
3. Propose a build plan for milestones 1–5 below, including the SQLite schema
   and a list of endpoints.
4. List anything in CLAUDE.md or the prompts that you think is wrong,
   contradictory or underspecified.

Don't write any code until I approve the plan.
```

---

## Prompt 1: ingest and PII stripping (no AI yet)

```
Build milestone 1: project setup, file parsing (A2), the PII stripper (A3), and
test_pii.py.

No AI calls in this milestone.

When the tests pass, show me:
- the cleaned text for cv_01_rohan_desai.docx and cv_07_lavanya_iyer.docx
- a list of every application that was flagged, with the reason

Then stop.
```

**What to check yourself:**
- No names, emails, phones or links are left.
- The Education sections are gone.
- JNPT and Nhava Sheva are still there.

---

## Prompt 2: pattern gate, scoring and calibration

```
Build milestone 2:
- the Setup screen with the Confirm pattern gate (0.5), tied to the rubric hash
- the Gemini client
- the scoring call (A4)
- evidence verification and score maths (A5)
- test_scoring_math.py and test_evidence.py
- test_calibration.py (live)

Run the calibration test and show me the per-criterion comparison against the
hand scores. If the lowest "Exceeds" total is not above the highest non-Exceeds
total, do not change the rubric. Show me where the model disagreed with the hand
scores and why.

Then stop.
```

**What to check yourself:** does the model agree with the hand scores on C1?
C1 carries the most weight.

---

## Prompt 3: brief and dashboard

```
Build milestone 3: the interview brief call (A6) and the dashboard (A7), as
specified in CLAUDE.md.

That includes:
- role tabs
- both scores
- the level hint
- the years flag
- the candidate detail view with evidence and unverified markers
- the stale-candidate banner

Score all applications. Then show me the top 5 in each tab and any candidate
with an unverified quote.

Then stop.
```

---

## Prompt 4: decide, draft, review, send

```
Build milestone 4:
- decisions (B1–B4)
- email drafting (B5) with the backend checks in prompts/draft_email.md
- the review-and-send screen (B6)
- sending through Resend in DEMO_MODE (B7)
- logging (B8)
- test_no_autosend.py

Demonstrate one invite and one rejection end to end. Both should arrive in my
DEMO_RECIPIENT inbox.

Confirm in writing that no code path sends without a click on a reviewed draft.

Then stop.
```

---

## Prompt 5: full run and review

```
Milestone 5:
1. Run the whole flow on all applications, up to drafts only. Send nothing.
2. Give me a short report:
   - counts by status
   - the score distribution per role
   - how many quotes were unverified
   - any PII blocks
   - any injection flags
   - the three things you would fix first in v2
3. Re-read CLAUDE.md and list every non-negotiable with the file and function
   that enforces it.
```

The mapping from step 3 is what you defend in class: each check from the nine
checks, pointing at the line of code that enforces it.
