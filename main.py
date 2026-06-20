"""Concept Check — FastAPI backend.

The boundary (Move 3):
  DETERMINISTIC  — the DB (Supabase) holds concepts, sessions, attempts, the
                   gap->result link, and enforces row-level security. The frontend
                   talks to Supabase directly with the user's token, so RLS applies.
  PROBABILISTIC  — this backend is the ONLY place the LLM lives. It does three
                   judgment jobs, each boxed by strict instructions: find the gap,
                   write one follow-up, judge whether the learner derived the WHY.

The LLM judges the causal "why / what-breaks", NOT the presence of jargon
(the Eddie clause), and must return the exact proof sentence so a hollow pass is
visible on inspection.
"""
import os
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq


def load_env(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

MODEL = "llama-3.3-70b-versatile"
client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
app = FastAPI(title="Concept Check")


# ---------- request shapes ----------
class AnalyzeIn(BaseModel):
    concept_prompt: str
    explanation_1: str


class JudgeIn(BaseModel):
    concept_prompt: str
    explanation_1: str
    gap_named: str
    followup: str
    explanation_2: str


# ---------- the boxed judge ----------
RULES = """You judge whether a learner UNDERSTANDS a systems concept, by testing
whether they can DERIVE THE "WHY" from first principles: why the thing must exist,
or what concretely breaks without it, stated as cause -> effect.

HARD RULES:
- Judge the causal reasoning, NOT vocabulary. A correct plain-language answer with
  zero technical jargon is a PASS (e.g. "the backend is like the muscle and organs;
  the data has to live somewhere central so everyone sees the same thing").
- Do NOT be agreeable. Restating the term, giving a definition, listing features,
  or deflecting ("it's just how it works", "it's a social media thing") is NOT a
  derivation. If they did not state a cause->effect reason, it is NOT closed.
- RIGOR: passing requires an EXPLICIT cause -> effect link — they must state what
  happens AND the reason it follows (X, THEREFORE Y, BECAUSE ...). Merely naming an
  outcome with no connecting mechanism is NOT enough. A vague one-liner that gestures
  at a consequence but cannot say why it follows ("then everyone has their own
  version") does NOT pass. Plain language is fine; a missing causal link is not.
- Always return the exact sentence from THEIR text that proves your verdict, or ""
  if none exists.
Return ONLY valid JSON. No prose outside the JSON."""

ANALYZE_SYS = RULES + """

TASK: Read the concept question and the learner's first explanation. Decide whether
they already DERIVED THE WHY on this first try.

Return JSON:
{
  "first_pass_closed": true/false,   // did they derive the why on the first try?
  "gap_named": "...",   // if NOT closed: one sentence naming the exact place their
                        //   explanation stopped deriving and became a label. else ""
  "followup": "...",    // if NOT closed: ONE sharp question that targets that gap and
                        //   forces them to reason out the why. NEVER give the answer. else ""
  "proof_sentence": "..."  // the sentence in their text that drove your verdict, or ""
}"""

JUDGE_SYS = RULES + """

TASK: The learner was shown a follow-up question aimed at a gap in their first
explanation. Read their SECOND explanation (the answer to the follow-up). Decide
whether they have NOW derived the why in their own words.

Return JSON:
{
  "gap_closed": true/false,      // did they derive the why after the follow-up?
  "proof_sentence": "..."        // the exact sentence from their second answer that
                                 //   proves it, or "" if they did not derive it
}"""


def groq_json(system: str, user: str) -> dict:
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(r.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")


# Post-verdict reinforcement (NOT an eval — generated only after the verdict, so it
# never leaks the answer before judging).
EXPLAIN_SYS = """Give a concise, first-principles explanation of the concept, in plain
language (4-6 sentences). Focus on WHY it must exist and what concretely breaks without
it — the causal story, not a jargon dump. Plain text only."""


def explain_concept(concept_prompt: str) -> str:
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": EXPLAIN_SYS},
                {"role": "user", "content": f"CONCEPT:\n{concept_prompt}"},
            ],
            temperature=0.3,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return ""


# ---------- routes ----------
@app.post("/analyze")
def analyze(inp: AnalyzeIn):
    user = (
        f"CONCEPT QUESTION:\n{inp.concept_prompt}\n\n"
        f"LEARNER'S FIRST EXPLANATION:\n{inp.explanation_1}"
    )
    out = groq_json(ANALYZE_SYS, user)
    first_pass = bool(out.get("first_pass_closed", False))
    return {
        "first_pass_closed": first_pass,
        "gap_named": out.get("gap_named", "") or "",
        "followup": out.get("followup", "") or "",
        "proof_sentence": out.get("proof_sentence", "") or "",
        # reinforcement only when the round ends here (first-try pass)
        "explanation": explain_concept(inp.concept_prompt) if first_pass else "",
    }


@app.post("/judge")
def judge(inp: JudgeIn):
    user = (
        f"CONCEPT QUESTION:\n{inp.concept_prompt}\n\n"
        f"FIRST EXPLANATION:\n{inp.explanation_1}\n\n"
        f"GAP THAT WAS NAMED:\n{inp.gap_named}\n\n"
        f"FOLLOW-UP QUESTION ASKED:\n{inp.followup}\n\n"
        f"LEARNER'S SECOND EXPLANATION (answer to the follow-up):\n{inp.explanation_2}"
    )
    out = groq_json(JUDGE_SYS, user)
    return {
        "gap_closed": bool(out.get("gap_closed", False)),
        "proof_sentence": out.get("proof_sentence", "") or "",
        "explanation": explain_concept(inp.concept_prompt),
    }


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "has_key": bool(os.environ.get("GROQ_API_KEY"))}


@app.get("/")
def root():
    return FileResponse("index.html")
