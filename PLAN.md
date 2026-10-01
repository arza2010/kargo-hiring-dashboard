# PLAN.md — Kargo Hiring Dashboard

Written at the start of the one-run build (KICKOFF_ONE_RUN.md). Covers the
data inventory, schema, endpoints, module layout, and how ambiguities in
CLAUDE.md / the prompts were resolved.

## 1. Data inventory

| Folder | Count | Formats | Notes |
|---|---|---|---|
| `data/applications/` | **0 real CVs** | — | Only a `README.md` placeholder is present. Arjun has not added the 60 CVs yet. |
| `data/hires/` | 8 | `.docx` | `cv_01_rohan_desai.docx` … `cv_08_rahul_bose.docx`. All have real names/emails/phones in a header line — exactly what A3 must strip. |
| `data/jds/` | 2 | `.docx` | `jd_product_manager.docx`, `jd_senior_product_manager.docx`. |

**Consequence:** Flow A (ingest → score → brief) can be fully built, tested, and
exercised on the 8 hire CVs (used for calibration only, never shown as
"applications" on the dashboard). There is nothing to batch-score as
applications yet. The app is built to ingest real applications the moment
Arjun drops them into `data/applications/` (flat, or under `pm/`/`spm/`
subfolders) and clicks **Score all** — nothing else changes.

Nothing here is unparseable ahead of time; `.doc`, scanned PDFs and images will
be flagged `needs_manual_review` by the parser at ingest time per CLAUDE.md.

## 2. Applied-role and name fallbacks (per KICKOFF_ONE_RUN.md, not guessed)

- Role: `pm/`/`spm/` subfolder name → filename containing `pm`/`product_manager`
  or `spm`/`senior` (word-boundary, case-insensitive) → else `role_unknown`,
  which blocks scoring until Arjun sets it in the UI.
- Name: taken from the header line of the parsed text, cross-checked against
  the filename (if the filename encodes a name) using a token-overlap check.
  If confidence is low, the CV is flagged `needs_name` and scoring is blocked
  until Arjun types the name in.

## 3. Resolutions to ambiguities / apparent conflicts in CLAUDE.md and the prompts

1. **`.env` is missing**, and `.env.example` contains what look like live-shaped
   API keys (redacted here — see the note left in `.env.example` itself) and an
   invalid model name (`gemini-3.5-flash` — not a real Gemini model id) with
   `DEMO_RECIPIENT` left blank. Per CLAUDE.md ("Never print, log or commit API
   keys") and the run rules ("Stop if `.env` is missing or `GEMINI_API_KEY`/
   `GEMINI_MODEL` is empty"), I will **not** copy `.env.example` to `.env`
   myself, and will not run anything that calls Gemini or Resend for real.
   I'll build the full app and every offline test, then stop per the run's
   first stop condition and flag this file to Arjun directly — committing
   real-shaped secrets into a template file is itself a problem worth his
   attention.
2. **Two copies of the rubric exist** (`kargo_pm_spm_rubric.txt` at repo root
   and `rubric/kargo_pm_spm_rubric.txt`). They are byte-identical (`diff`
   confirms it). CLAUDE.md's folder layout and hash-gate both point at
   `rubric/kargo_pm_spm_rubric.txt`, so that is the one the app reads and
   hashes. The root copy is left alone (not part of the spec'd layout, so not
   mine to delete without being asked).
3. **`KICKOFF.md` vs the pasted one-run instructions** ask for opposite
   process: KICKOFF.md (and CLAUDE.md's "How to work with me") says stop after
   every milestone for review; the pasted run instructions say run straight
   through using each phase's automated gate instead of manual review. The
   pasted instructions are the explicit, detailed instruction for *this*
   session, so they govern process for this run. CLAUDE.md's 9 non-negotiables
   still govern the actual behaviour of the app — that hasn't changed.
4. **Rubric Part A.10 (years) vs the dashboard's "years flag" requirement**:
   the rubric is explicit that years are never scored, only reported as an
   info field with a flag when outside the JD's range. `years_flag` is
   computed in the backend from `pm_years_from_cv` (which the AI extracts) and
   the applied role's JD range (PM 2–4, SPM 5–8) — never fed back into either
   score.
5. **`level_hint`**: CLAUDE.md's dashboard spec says "a level hint when the
   other role's score is 10+ points higher". I compute this in the backend
   from the already-computed `pm_score`/`spm_score` (not asked of the AI),
   consistent with rule 6 ("the backend does the maths").
6. **Prompt `score_candidate.md` Part E vs the app's actual schema**: the
   prompt file says its own Response Schema section "overrides Part E of the
   rubric" — no totals in the AI response, since the backend computes them.
   I implement the JSON schema exactly as given in `score_candidate.md`.
7. **PII stripper and JNPT/Nhava Sheva**: these are logistics location names,
   not personal city names, and are explicitly listed as "keep". The
   configurable city list (Mumbai, Bengaluru, Bangalore, Chennai, Delhi, New
   Delhi, Pune, Hyderabad, Kolkata, Ahmedabad, Jamshedpur) is the only set of
   place names redacted to `[CITY]`.
8. **No changes made** to the rubric, the three prompts' meaning, or any
   scoring weight. I fixed nothing in the prompts — templating is straightforward
   and will be documented in RUN_REPORT.md as "no edits" if that holds.

## 3a. Database: Neon (Postgres), not SQLite

Mid-build, Arjun asked to switch the database from SQLite to Neon. I flagged
that this moves candidate PII (name, email, phone) off the local machine into
a hosted Postgres instance, and that it contradicts CLAUDE.md's "local tool,
no auth, SQLite" stack line — he confirmed he wants Neon anyway. Everything
else about the non-negotiables (no auto-send, no auto-reject, pattern gate,
PII stripped before any AI call, evidence-checked quotes, backend-computed
scores, no-reasons rejections, full logging, CV-text-as-data) is unaffected;
only the storage engine changes.

- Driver: `psycopg` v3 (`psycopg[binary]`), raw SQL — no ORM, to keep the code
  as simple to read as the original SQLite plan.
- Connection string: `DATABASE_URL` env var (a Neon connection string,
  `postgresql://...`). Added to `.env.example`. Like `GEMINI_API_KEY` and
  `RESEND_API_KEY`, this is not fabricated — the app requires Arjun to supply
  his own Neon connection string in `.env`. Until then, `app/db.py` raises a
  clear startup error rather than falling back to a local file silently.
- The schema below is unchanged in shape; only the SQLite-specific syntax
  (`AUTOINCREMENT` → `GENERATED ALWAYS AS IDENTITY`, `0/1` flags → real
  `BOOLEAN`) is adapted for Postgres. Timestamps stay ISO-8601 `TEXT` for
  simplicity, written as UTC.
- Because this now depends on a live network connection Arjun controls, tests
  that touch the database use an isolated test schema/prefix on the same Neon
  branch (or `DATABASE_URL_TEST` if he provides a separate one), never the
  real data.

## 4. Database schema (`app/db.py`, Postgres/Neon)

```
candidates
  id                 TEXT PRIMARY KEY        -- cv_<contenthash8>
  source             TEXT                    -- 'application' | 'hire'
  file_path           TEXT
  content_hash        TEXT UNIQUE
  original_filename    TEXT
  applied_role         TEXT                  -- PM | SPM | role_unknown
  name                 TEXT                  -- real name, only column allowed to hold PII
  email                TEXT
  phone                TEXT
  cleaned_text          TEXT                 -- PII-stripped text sent to the AI
  parse_status          TEXT                 -- ok | needs_manual_review | needs_name | pii_block
  parse_notes            TEXT
  status                 TEXT                -- new | scored | decided | drafted | sent
  created_at              TEXT
  updated_at              TEXT

scores
  candidate_id       TEXT PRIMARY KEY REFERENCES candidates(id)
  criteria_json       TEXT   -- {C1..C5_PM/C5_SPM: {level, evidence, status}} after verification
  pm_score             REAL
  spm_score             REAL
  pm_years_from_cv       REAL
  years_flag              TEXT
  level_hint               INTEGER  -- 0/1
  probes_json               TEXT
  one_line_rationale         TEXT
  injection_detected           INTEGER
  scored_at                     TEXT

briefs
  candidate_id       TEXT PRIMARY KEY REFERENCES candidates(id)
  who_text            TEXT
  why_ranked_json       TEXT
  gaps_json              TEXT
  probes_json              TEXT
  level_note                TEXT
  created_at                  TEXT

decisions
  id                 INTEGER PRIMARY KEY AUTOINCREMENT
  candidate_id       TEXT REFERENCES candidates(id)
  decision            TEXT  -- interview_pm | interview_spm | pass
  note                  TEXT
  decided_at              TEXT

drafts
  id                 INTEGER PRIMARY KEY AUTOINCREMENT
  candidate_id       TEXT REFERENCES candidates(id)
  decision_id          INTEGER REFERENCES decisions(id)
  subject               TEXT
  body_text              TEXT
  reviewed                 INTEGER  -- 0/1, set true once the review screen is opened/saved
  warning                    TEXT   -- backend-check warning, if any
  created_at                   TEXT
  updated_at                     TEXT

sends
  id                 INTEGER PRIMARY KEY AUTOINCREMENT
  draft_id           TEXT REFERENCES drafts(id)
  resend_message_id   TEXT
  to_address            TEXT
  subject_sent            TEXT
  sent_at                   TEXT

setup
  id                 INTEGER PRIMARY KEY CHECK (id = 1)
  rubric_hash        TEXT
  confirmed_at         TEXT
  acknowledge_delay      INTEGER DEFAULT 1

event_log
  id                 INTEGER PRIMARY KEY AUTOINCREMENT
  ts                 TEXT
  event_type          TEXT   -- decision | draft | edit | send | pii_block | injection_flag
  candidate_id          TEXT
  detail_json              TEXT
```

## 5. Module layout (`app/`)

- `config.py` — loads `.env`, exposes settings, no defaults for secrets.
- `db.py` — schema + connection helper (`sqlite3`, `row_factory=Row`).
- `rubric.py` — splits the rubric file on `PART X ·` headers, computes SHA-256,
  exposes Parts A/B/E (AI-facing) and Part D (setup screen only).
- `parsing.py` — `.docx`/`.pdf` text extraction, content hashing, dedup.
- `pii.py` — the A3 stripper + post-check (fail-closed).
- `gemini_client.py` — thin wrapper over `google.genai`, retry/backoff on
  `errors.APIError` with 429/5xx codes.
- `scoring.py` — builds the A4 prompt, calls Gemini, verifies evidence quotes,
  computes `pm_score`/`spm_score`/`years_flag`/`level_hint` (A5).
- `brief.py` — builds and calls the A6 prompt.
- `email_draft.py` — builds and calls the B5 prompt, runs the backend checks,
  one regenerate-then-warn retry.
- `resend_client.py` — the **only** module that imports/calls the Resend SDK.
- `ingest.py` — orchestrates A1–A3 for a single file or a batch import.
- `main.py` — FastAPI app + all routes; Jinja2 templates in `app/templates/`.
- `templates/` — `setup.html`, `dashboard.html`, `candidate.html`,
  `review_email.html`, partials.

## 6. Endpoint list

```
GET  /                          -> redirect to /setup or /dashboard
GET  /setup                     -> setup screen (pattern, weights, Part D)
POST /setup/confirm             -> stores confirmation against rubric hash
GET  /setup/settings            -> (fragment) acknowledge_delay toggle
POST /setup/settings            -> update acknowledge_delay

POST /candidates/upload         -> A1 single-file upload (+ role dropdown)
POST /candidates/import-batch   -> A1 batch import from data/applications/
POST /candidates/{id}/role      -> set role for role_unknown
POST /candidates/{id}/name      -> set name for needs_name

POST /score/all                 -> A4-A6 batch: score + brief every eligible,
                                    known-role, named candidate. Gated on
                                    pattern confirmation. Never drafts/sends.
POST /candidates/{id}/score     -> score+brief a single candidate

GET  /dashboard                 -> tabs (PM/SPM/All), banners
GET  /candidates/{id}           -> detail view

POST /candidates/{id}/decision  -> record decision (+ optional note),
                                    creates the draft (B1-B5)
GET  /drafts/{id}               -> review screen (B6)
POST /drafts/{id}                -> save edits to subject/body
POST /drafts/{id}/send             -> **the only path that calls Resend** (B7)

GET  /files/{id}                    -> serves the original CV file
```

## 7. SDKs (docs checked live, not from memory)

- **google-genai**: `google.genai.Client(api_key=...)`,
  `client.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(response_mime_type='application/json', response_json_schema=..., temperature=...))`.
  Retries on `google.genai.errors.APIError` where `e.code in (429, 500, 503)`.
- **resend**: `resend.api_key = ...`; `resend.Emails.send({...})` with
  `from`, `to`, `subject`, `text`.

## 8. What's next

Phase 1 (ingest + PII, no AI) starts immediately.
