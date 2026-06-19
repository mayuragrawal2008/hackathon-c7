# Hackathon Rules & Spine — 100xEngineers Cohort 7 Code Path

Reference distilled from the Participant Handbook. Track A: The Concept Check.

---

## The one line
The app is plumbing. It must run and the walls must hold, but there are **no points
for polish**. The grade is the evidence that a human did what the model cannot.
**Build the service. Earn the software. Verify the verifier.**

## The clock
- **Start:** 10:00 PM IST, Fri 19 Jun 2026
- **End / submissions close:** 10:00 PM IST, Sat 20 Jun 2026 (hard deadline)
- **Results:** 8:30 PM IST, Mon 22 Jun 2026 (Zoom)

### Check-ins (every 6h)
| When (IST) | Type | Where |
| ---------- | ---- | ----- |
| 4:00 AM Sat | async | Discord #check-ins |
| 10:00 AM Sat | async | Discord #check-ins |
| 4:00 PM Sat | live sync | Zoom |
| 9:00 PM Sat | async (final push) | Discord #check-ins |

Async check-in template:
```
Name and track:
Furthest move completed: (Move 1 to 5)
What I got working since the last check-in:
Where I am stuck right now: (or: nothing blocking)
Repo link (and deploy link if it is live):
On pace for 10:00 PM? yes / at risk / no
```

---

## The Rules (hard)
1. **Deadline.** Work committed/edited after 10:00 PM IST Sat does not count.
2. **One track.** Switch only before Check-in 1 (4:00 AM) and note it in #check-ins. After that, committed.
3. **Solo by default.** People you test are subjects, not teammates.
4. **Use any AI tools to build.** The model writes the software; the grade is the part it cannot fake.
5. **Hand-drawn means hand-drawn.** Move 3 and Move 4 diagrams on paper, photographed/screenshotted, pasted in. A tool-generated diagram does NOT satisfy this.
6. **Hypothesis is timestamped before the first commit.** Move 2 claim + kill-number = first commit, before any code. Back-dating = automatic fail.
7. **Evidence must be real.** Real people, real sessions, real before/after, with names. Fabrication = automatic fail. Honest disproof > polished fake.
8. **Consent and privacy.** Consent for anything recorded/screenshotted. No private data in public channels. Demonstrate the two-user row-level-security test in your own deployment.
9. **Submission.** One document in the track template + public GitHub repo + reachable deployment, in the form by 10:00 PM IST. **No Move 5, no submission.**
10. **Be present live.** Briefing, 4:00 PM sync, results announcement (Zoom).

---

## The Shared Spine (every track, in order)
1. **Contact before code** — by hand, be the tool yourself with real people first.
2. **Your bet before the build** — claim + kill-number, first commit, before code.
3. **The boundary is the whole skill** — draw the line between deterministic (rules) and probabilistic (LLM); own where the judge sits and its failure mode.
4. **One load-bearing link in the data** — the foreign key from "what the tool said" to "what happened next." Lock with identity + row-level security + two-user test.
5. **Behavioral proof, or nothing** — two people, >=1 cold/uncoached. Only behavioral signal counts. Write the surprise where reality broke your bet.

---

## Track A — The Five Moves (what to submit)
1. **Move 1:** Two raw derivation records (transcript/audio/screenshots, with names) + the by-hand follow-up log + the sentence where the explanation became a label.
2. **Move 2:** Timestamped hypothesis + kill-number, dated before first commit.
3. **Move 3:** Hand-drawn boundary diagram + what's deterministic / probabilistic / who judges the second derivation + the failure mode accepted.
4. **Move 4:** Hand-drawn schema with the gap-to-result foreign key marked + two-user RLS test result (two accounts, attempted cross-read, empty result).
5. **Move 5:** For two people, before/after derivation evidence + one documented surprise. **>=1 cold user.**

## Track A submission template (sections, in order)
```
CONCEPT CHECK SUBMISSION
Name:
Concept(s) tested:
Public Github Repo link:

MOVE 1: WATCH TWO PEOPLE
Person 1, raw record / label sentence / follow-up + could they derive after?
Person 2, raw record / label sentence / follow-up + could they derive after?

MOVE 2: THE HYPOTHESIS (timestamped, before first commit)
The claim / proves right / means no problem / kill-number / timestamp+commit link

MOVE 3: THE SYSTEM DESIGN
[paste hand-drawn diagram] Deterministic / Probabilistic / Who judges 2nd derivation / Failure mode accepted

MOVE 4: DOMAIN MODELLING
[paste hand-drawn diagram] Two-user test: accounts, attempted cross-read, result

MOVE 5: THE FINAL REPORT
Person A (cold?) before/after evidence
Person B (cold?) before/after evidence
The surprise (one concrete place reality broke my prediction, with evidence)
```

---

## Traps to avoid (Track A)
- Building a **multiple-choice quiz** — cannot tell understanding from a lucky guess. Build the opposite: a thing that makes recognition fail loudly.
- Letting the **model decide** whether the learner now understands — a generous judge passes everyone where the claim lives or dies.
- A **kill-number** you secretly know can never happen.
- Starting from the app instead of **watching two real people first**.
- (Our own, from Move 1) Judging **jargon instead of understanding** — the Eddie false-gap.

## The gate
**No Move 5, no submission.** A working app without real-people behavioral evidence is
"a well-built thing that proves nothing." Protect Move 1 and Move 5 above all else.
