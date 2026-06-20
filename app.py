"""Single-URL entry: mounts the Gradio v1 app at / and serves the v2 Constellation
UI at /v2, with a thin JSON LLM API the v2 client calls. Same Supabase DB for both.

Run: uvicorn app:app --host 0.0.0.0 --port $PORT
"""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import gradio as gr

import gradio_app as G  # reuses CONCEPTS, the boxed evals, socratic_step, diagnose, explain

app = FastAPI()


class AnalyzeIn(BaseModel):
    concept_prompt: str
    explanation_1: str


class JudgeIn(BaseModel):
    concept_prompt: str
    explanation_1: str
    followup: str
    explanation_2: str


@app.post("/api/analyze")
def api_analyze(i: AnalyzeIn):
    """First pass: derived first try? else return the ONE follow-up."""
    dlg = [("tutor", i.concept_prompt), ("learner", i.explanation_1)]
    out = G.socratic_step(i.concept_prompt, dlg)
    derived = bool(out.get("derived"))
    return {
        "derived": derived,
        "followup": out.get("next_question", "") or "",
        "proof_sentence": out.get("proof_sentence", "") or "",
        "used_jargon": bool(out.get("used_jargon")),
        "explanation": G.explain_concept(i.concept_prompt) if derived else "",
    }


@app.post("/api/judge")
def api_judge(i: JudgeIn):
    """Second pass: derived after the follow-up? else diagnose the direction missed."""
    dlg = [("tutor", i.concept_prompt), ("learner", i.explanation_1),
           ("tutor", i.followup), ("learner", i.explanation_2)]
    out = G.socratic_step(i.concept_prompt, dlg)
    derived = bool(out.get("derived"))
    res = {
        "derived": derived,
        "proof_sentence": out.get("proof_sentence", "") or "",
        "used_jargon": bool(out.get("used_jargon")),
        "explanation": G.explain_concept(i.concept_prompt) if derived else "",
        "diagnose": {} if derived else G.diagnose_gap(i.concept_prompt, dlg),
    }
    return res


@app.get("/v2")
def v2():
    return FileResponse("constellation.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


# mount the existing Gradio app at the root (Classic mode)
app = gr.mount_gradio_app(app, G.demo, path="/")
