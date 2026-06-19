# Move 3 — The System Boundary (deterministic vs probabilistic)

Track A: The Concept Check. The hand-drawn version of this lives at
`evidence/move3-boundary.jpg` (required, drawn on paper). This file is the written
companion the submission template asks for.

---

## Deterministic (fixed, rule-based — code + Postgres)
- **Concept list** — interface, API, why-a-backend, frontend/backend, storage,
  choosing storage. Shipped as fixed seed data, NOT generated per request.
- **Session records** — learner, concept, first explanation, named gap, follow-up
  asked, second attempt text.
- **The load-bearing link** — foreign key from a named gap to its second-attempt
  result (this is also the Move 4 metric: did the gap close?).
- **Access rules** — Supabase row-level security; a learner sees only their own rows.
- **The verdict tally** — the plain boolean "did the gap close?" stored per attempt.

## Probabilistic (judgment — Groq / Llama 3.3)
- **Find the gap** — read the learner's explanation, locate where they stop deriving
  the *why* and fall back to a label.
- **Write one follow-up** — a single sharp question aimed at that exact spot. Not the answer.
- **Judge the second attempt** — decide CLOSED / NOT_CLOSED.

## Who judges the second derivation, and why
The LLM judges, but it is **constrained to a causal test, not a free vibe-check**.
It must answer one structured question:

> "Did the learner state *why the thing must exist* or *what breaks without it*, in
> cause -> effect form? Return CLOSED or NOT_CLOSED, plus the exact sentence that
> proves it."

Reasoning: a human-only judge is harder to fake but too slow for a 24h build and a
live tool. Anchoring the LLM to (a) a causal criterion and (b) a required
proof-sentence quote keeps it from rubber-stamping everyone, while staying fast.

### The Eddie clause (from Move 1)
Jargon is explicitly **ignored**. A correct plain-language causal answer
("the backend is the muscle, the internet is just the skeleton; data has to live
somewhere") counts as CLOSED. Grading on vocabulary instead of understanding is the
false-positive discovered live in Move 1 Person 3, and the tool is built against it.

## Failure mode I accept (on purpose)
A fluent learner could produce a causal-*sounding* but hollow sentence and earn a
false CLOSED. I accept this residual risk rather than forcing a slow human-only
verdict. Mitigation: the judge must quote the proof-sentence, so a hollow pass is
visible on inspection and can be caught in the Move 5 review.

## Where it would quietly break if I let the model do everything
If the LLM both wrote the follow-up AND freely decided "they understand now," it
would pass nearly everyone — the claim (people fail to derive the why) could never
be observed, because the judge is too agreeable. The deterministic spine (fixed
concepts, recorded attempts, the gap->result link, the boolean verdict) is what
keeps the judgment honest and measurable.
