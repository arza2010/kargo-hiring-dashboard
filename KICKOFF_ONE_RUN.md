# One-run build prompt for Claude Code

**Before you paste this:**

- The 60 CVs are in `data/applications/`. Use `pm/` and `spm/` subfolders if the
  filenames don't show the role.
- `.env` is filled in: `GEMINI_API_KEY`, `GEMINI_MODEL`, `RESEND_API_KEY`,
  `DEMO_MODE=true`, `DEMO_RECIPIENT`.

Open a terminal in this folder, run `claude`, and paste everything inside the
box below.

Approve commands as Claude Code asks for them. Don't use a skip-permissions
mode: this run installs packages and calls paid APIs.

---

```
You are building the Kargo hiring dashboard in one continuous run. Work through
every phase below without stopping for my approval. Use the automated gates in
each phase in place of my review.

═══════════════════════════════════════════════════════════════
SOURCE OF TRUTH
═══════════════════════════════════════════════════════════════
Read these completely before writing any code:
  CLAUDE.md                          (project rules, stack, spec)
  rubric/kargo_pm_spm_rubric.txt     (scoring rubric v0.2)
  prompts/score_candidate.md         (step A4)
  prompts/interview_brief.md         (step A6)
  prompts/draft_email.md             (step B5)

CLAUDE.md wins over anything in this prompt if the two conflict. The 9
non-negotiables in CLAUDE.md are absolute. The most important ones:
  - Nothing is ever emailed to anyone without a human clicking Send on a
    reviewed draft.
  - No cut-off score and no automatic rejection.
  - No personal details in any AI call.
  - Every score must quote the CV, and the backend verifies each quote.
  - The backend does all score arithmetic.

═══════════════════════════════════════════════════════════════
RULES FOR THIS RUN
═══════════════════════════════════════════════════════════════
DO NOT, at any point in this run:
  - Send any real email. Tests use a fake Resend client. The real send
    function must exist, but only a human clicking Send in the UI calls it.
  - Change the rubric's criteria, anchors or weights, even if calibration
    disagrees. Report the disagreement instead.
  - Change the meaning of the three prompts. You may fix templating or
    formatting bugs, but list every edit in the report.
  - Guess a candidate's applied role or name. Use the fallbacks below.
  - Print, log or commit API keys.
  - Add features listed as out of scope in CLAUDE.md, install OCR, or deploy
    anything online.

Use these defaults instead of asking me:
  - Applied role:
      1. Use a pm/ or spm/ subfolder if there is one.
      2. Otherwise, use the filename if it clearly says pm, product_manager,
         spm or senior.
      3. Otherwise, set role_unknown. Arjun sets it in the UI. Don't score
         the CV until he does.
  - Name not found with confidence: flag needs_name. Arjun types it in the
    UI. Don't send that CV to the AI until he does.
  - Unparseable file (.doc, scanned PDF, image): flag needs_manual_review
    and skip it.
  - acknowledge_delay (used in email drafts): default true. Make it a
    setting on the Setup screen.

Stop only if one of these happens:
  - .env is missing, or GEMINI_API_KEY or GEMINI_MODEL is empty.
    First build everything and run all offline tests, then stop and tell me
    what's missing.
  - A phase's gate still fails after 3 serious fix attempts.
    Stop, and write RUN_REPORT.md covering what is done and what is blocking.
  - You find a genuine contradiction in CLAUDE.md that you can't resolve
    safely. Pick the safer reading and note it, or stop if neither reading is
    safe.

═══════════════════════════════════════════════════════════════
PHASE 0 · PLAN
═══════════════════════════════════════════════════════════════
1. Inspect data/applications, data/hires and data/jds. Record file counts,
   formats, how many roles you could determine, and anything unparseable.
2. Write PLAN.md covering: the SQLite schema, the endpoint list, the module
   layout under app/, and any problems you found in CLAUDE.md or the prompts
   (with your resolution for each).
3. Check the current google-genai SDK and Resend Python SDK documentation.
   Don't write either client from memory.
GATE: PLAN.md exists. Continue.

═══════════════════════════════════════════════════════════════
PHASE 1 · INGEST + PII STRIPPING  (steps A1–A3, no AI)
═══════════════════════════════════════════════════════════════
Build:
  - project setup (requirements.txt, virtualenv instructions)
  - the parsers (docx, pdf)
  - deduplication by content hash
  - the PII stripper and its post-check, exactly as specified in CLAUDE.md
  - tests/test_pii.py
Then run ingest on all applications and on the 8 hire CVs.
GATE: test_pii.py passes. Also, a scan of every cleaned text finds zero
emails, phones, URLs or name tokens. Education sections are gone, and
JNPT and Nhava Sheva are preserved.

═══════════════════════════════════════════════════════════════
PHASE 2 · PATTERN GATE + SCORING + CALIBRATION  (0.5, A4, A5)
═══════════════════════════════════════════════════════════════
Build:
  - the Setup screen, showing the pattern, the weights, rubric Part D and
    the Confirm button. The confirmation is stored against the rubric file's
    SHA-256 hash.
  - the rubric splitter. Only Parts A, B and E ever go to the AI.
  - the Gemini client, with JSON schema output, temperature 0, and retry
    with backoff
  - the scoring call
  - evidence verification (normalised matching; quotes not found become
    level 0 with status unverified)
  - score maths for pm_score, spm_score, years_flag and level_hint
  - tests: test_scoring_math.py, test_evidence.py, test_calibration.py
    (marked live)
Scoring must refuse to run while the pattern is unconfirmed. Your tests may
confirm the pattern on a throwaway test database. The real database must
start unconfirmed, because Arjun confirms it himself.
GATE: all offline tests pass. Then run test_calibration.py once, live.
  - It passes if the lowest "Exceeds" total is above the highest
    non-Exceeds total.
  - If it fails, do NOT change the rubric or prompts to force a pass.
    Record the per-criterion disagreements with hand scores, and the model's
    quoted evidence, in RUN_REPORT.md. Then continue.

═══════════════════════════════════════════════════════════════
PHASE 3 · BRIEF + DASHBOARD  (A6, A7)
═══════════════════════════════════════════════════════════════
Build the interview brief call and the dashboard as specified in
CLAUDE.md:
  - PM, SPM and All tabs
  - both scores, the level hint, the years flag and the status on each row
  - the candidate detail view, with evidence and unverified markers, probes,
    the brief, a link to the original file, and decision buttons
  - the unsent-email banner
  - the stale-candidate banner (scored more than 7 days ago with no decision)
Add a "Score all" button. It is enabled only after the pattern has been
confirmed. It scores and briefs every application that has a known role
and name. It never drafts or sends anything.

For this run, do the full batch scoring on a COPY of the database
(data/dryrun.db). Confirm the pattern on that copy only. The real database
stays unconfirmed and unscored.
GATE: the app starts on 127.0.0.1. Every page renders without errors. Every
scored candidate has a brief. No candidate is hidden or filtered out by
score.

═══════════════════════════════════════════════════════════════
PHASE 4 · DECIDE, DRAFT, REVIEW, SEND  (B1–B8)
═══════════════════════════════════════════════════════════════
Build:
  - the decisions: Interview as PM, Interview as SPM, Pass, plus an
    optional note
  - drafting, with all the backend checks from prompts/draft_email.md
    (regenerate once on failure, then warn)
  - the review screen: editable subject and body, a preview with the name
    merged in, and a Send button
  - the send endpoint, which in DEMO_MODE redirects to DEMO_RECIPIENT with
    the [DEMO → …] subject prefix
  - logging of every decision, draft, edit, send and Resend message ID
  - tests/test_no_autosend.py
Using the fake Resend client, create one test invite and one test rejection,
end to end, on a test database.
GATE: test_no_autosend.py passes. The Resend send call is referenced only
in the send endpoint. The endpoint rejects drafts that haven't been
reviewed. No batch route sends. No real email has been sent during this run.

═══════════════════════════════════════════════════════════════
PHASE 5 · FULL DRY RUN + REPORT
═══════════════════════════════════════════════════════════════
1. Run the full test suite, including the live calibration test once more.
2. Write RUN_REPORT.md with:
   a. How to start the app: the exact commands.
   b. Counts by status, plus lists of role_unknown, needs_name and
      needs_manual_review files.
   c. The score distribution per role, and the top 5 in each tab with
      their one-line rationale.
   d. Calibration results: model vs hand scores for the 8 hires, per
      criterion, and pass or fail.
   e. Unverified quotes, PII blocks and injection flags, with counts and
      examples.
   f. Every edit you made to the prompts, and why.
   g. A CHECKS-TO-CODE MAP. For each of the 9 non-negotiables in CLAUDE.md,
      give the file and function that enforces it and the test that proves
      it.
   h. The top 3 fixes for v2.
   i. A "WHAT THE HUMAN DOES NEXT" section, in order:
        1. Start the app.
        2. Open Setup, read Part D and click Confirm pattern.
        3. Click Score all.
        4. Resolve the flagged files.
        5. Review the ranked candidates.
        6. Record one decision.
        7. Review the draft.
        8. Click Send once and check the DEMO_RECIPIENT inbox.
   Take the numbers for b–e from the dry-run copy, and label them
   "dry run".
3. Make sure the real database is in a clean starting state:
     - CVs ingested and cleaned
     - pattern unconfirmed
     - nothing scored
     - no decisions, drafts or sends
   Keep data/dryrun.db for reference. The app must use the real database
   by default.

Finish with a short summary and the path to RUN_REPORT.md.
```

---

## Why the run still ends with you

The prompt lets Claude Code build and test everything by itself. It stops
short of three things that stay human, exactly as your nine checks require:

- **Confirming the pattern** (gate 0.5)
- **Making a decision** on a candidate (B1)
- **Clicking Send** (B6)

That is why the full scoring run happens on a dry-run copy of the database,
and the real one is left unconfirmed, unscored and with nothing sent. The
first confirmation, the first real scoring run and the first email are yours.
