# CONCEPT CHECK SUBMISSION

**Name:** Mayur Agrawal
**Concept(s) tested:** Why a backend exists; interface / API; frontend vs backend; authentication & authorization
**Public GitHub Repo link:** https://github.com/mayuragrawal2008/hackathon-c7
**Live app:** https://hackathon-c7.onrender.com

---

## MOVE 1: WATCH TWO PEOPLE
*(Minimum is two; three were run. Raw audio + transcripts in `evidence/`.)*

### Person 1 — (name in private record)
- **Raw record:** by-hand session, logged in `move1-record.md` (Person 1).
- **The sentence where the model became a label:**
  > "something managing interface and backend design make it work"
- **Follow-up used / could they derive after?** Asked "why must that 'somewhere' be a
  separate machine — why can't your phone and your friend's phone talk directly?"
  → **Did NOT derive.** Fell back to "it's just a social media thing." Gap stayed open.

### Person 2 — Hansh Goel
- **Raw record:** `evidence/Hansh_Interview.m4a` + `evidence/Hansh_transcript.txt`.
- **The sentence where the model became a label:** none found.
- **Follow-up used / could they derive after?** N/A — derived backend, interface, API,
  and auth/authz cleanly from first principles under repeated pressure. A genuine
  "no gap exists" case.

### Person 3 — Eddie (the key finding)
- **Raw record:** `evidence/Eddie.m4a` + `evidence/Eddie_transcript.txt`.
- **The sentence where the model became a label:** ambiguous — he derived the *idea*
  in plain language ("the backend is the muscle and organs; the internet is just the
  skeleton; the data has to live somewhere") but lacked technical vocabulary.
- **Follow-up used / could they derive after?** On the WhatsApp peer-to-peer probe he
  stalled on jargon. **The finding:** acting as the tool, I caught myself grading on
  the *technical words I expected* rather than on understanding. Flagging missing
  jargon as a gap is a FALSE POSITIVE — the "Eddie clause" the tool is now built against.

---

## MOVE 2: THE HYPOTHESIS (timestamped, before first commit)
*(Full text in `HYPOTHESIS.md`. First commit `83cc06b`, 23:10 IST 19 Jun, before any code.)*

- **The claim:** A learner who can state/define a systems concept will still fail to
  **derive the *why*** (why it must exist / what breaks without it) under one sharp
  follow-up, more often than not. Naming the gap + one reasoning follow-up lets them
  close it. Understanding is scored on the causal *why*, NOT on technical vocabulary.
- **Result that proves me right:** both Move 5 users fail the "why" on first try, then
  derive it in their own words after the named gap + follow-up.
- **Result that means no problem exists:** both derive the why cleanly on first try.
- **Kill-number:** if **1 or 0 of 2** users shows a real before→after "why"-close,
  "my hypothesis was wrong."
- **Timestamp / commit link:**
  https://github.com/mayuragrawal2008/hackathon-c7/commit/83cc06b

---

## MOVE 3: THE SYSTEM DESIGN
*[paste hand-drawn system design diagram here → `evidence/move3-boundary.jpg`]*
*(Written companion: `MOVE3_design.md`.)*

- **Deterministic parts:** the fixed concept list; every session and attempt record;
  the gap→result link; row-level-security access rules; the stored pass/fail verdict.
- **Probabilistic parts (Groq / Llama 3.3, the only place the LLM lives):** find where
  the explanation stops deriving; write one follow-up; judge whether the second attempt
  derives the why.
- **Who judges the second derivation, and why:** the LLM judges, but it is constrained
  to a causal test — "did they state *why it must exist* or *what breaks without it*,
  cause→effect?" — and must return the exact proof sentence. A human-only judge is
  harder to fake but too slow for a live tool; anchoring the LLM to a causal criterion
  + a quoted proof sentence keeps it from rubber-stamping everyone.
- **Failure mode I accepted:** a fluent learner could produce a causal-*sounding* but
  hollow sentence and earn a false CLOSED. Accepted as residual risk; mitigated by the
  required proof-sentence quote, which makes a hollow pass visible on inspection.
  (Jargon is explicitly ignored — the Eddie clause.)

---

## MOVE 4: DOMAIN MODELLING
*[paste hand-drawn domain model here → `evidence/move4-data-deterministic.jpg`]*
*(Schema in `schema.sql`.)*

Tables: `concepts` (seed) → `sessions` (per learner + concept) → `attempts`. The
load-bearing link is `attempts.gap_closed` — the named gap to its second-pass result.

- **Two-user test: two accounts, attempted cross-read, result:** PASSED.
  User A inserted an attempt (`explanation_1 = "A secret explanation"`); A reads it back;
  **User B reads the same table → `[]` (empty), cannot see A's data.** Full record in
  `evidence/move4-rls-test.md`.

---

## MOVE 5: THE FINAL REPORT
*(To complete after two real users run the live app. At least one must be a cold,
uncoached user. The app auto-records before-state and after-state per user.)*

### Person A (cold user / coached?): __________
- **Before-state evidence (could not derive):** __________  *(explanation_1 +
  first_pass_closed = false)*
- **After-state evidence (derived):** __________  *(explanation_2 + gap_closed = true
  + proof sentence)*

### Person B (cold user / coached?): __________
- **Before-state evidence (could not derive):** __________
- **After-state evidence (derived):** __________

### The surprise (one concrete place reality broke my prediction, with evidence):
__________
