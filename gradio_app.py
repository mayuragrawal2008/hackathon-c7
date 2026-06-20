"""Concept Check — gamified Gradio chat UI (branch: gradio-ui).

Standalone presentation layer over the same boxed LLM judge (Groq / Llama 3.3).
The graded submission remains the baseline HTML app on `main` (which holds the
auth + row-level-security proof). This version is the gamified demo for Move 5.
"""
import os
import json
from pathlib import Path

import gradio as gr
from groq import Groq


# ---------- env + LLM ----------
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

CONCEPTS = [
    ("Why does a backend exist?",
     "Explain from first principles why a backend exists. Why can't everything just run in the browser?"),
    ("What is an interface / API, really?",
     "Explain what an interface is, and what an API is underneath the word — from first principles."),
    ("Frontend vs backend",
     "What is a frontend, what is a backend, and why do we need both?"),
    ("Why a database, not a file?",
     "From first principles, what ways exist to store data, and why do we need a database rather than just a file?"),
    ("Choosing a storage option",
     "How do you choose one storage option over another? Which factors decide it?"),
]
PROMPT_BY_NAME = {n: p for n, p in CONCEPTS}

RULES = """You judge whether a learner UNDERSTANDS a systems concept by testing whether
they DERIVE THE "WHY" from first principles: why the thing must exist, or what concretely
breaks without it, as cause -> effect.
HARD RULES:
- Judge the causal reasoning, NOT vocabulary. A correct plain-language answer with zero
  technical jargon is a PASS.
- Do NOT be agreeable. Restating the term, defining it, listing features, or deflecting
  ("it's just how it works") is NOT a derivation.
- Always quote the exact sentence from THEIR text that proves your verdict, or "".
Return ONLY valid JSON."""

ANALYZE_SYS = RULES + """
TASK: Decide if the learner DERIVED THE WHY on this first try.
Return JSON: {"first_pass_closed": bool, "gap_named": str, "followup": str,
"proof_sentence": str, "used_jargon": bool}
used_jargon = did they rely on technical jargon, or explain in plain language?
If not closed: gap_named = where it became a label; followup = ONE question that forces
reasoning and never gives the answer."""

JUDGE_SYS = RULES + """
TASK: The learner answered a follow-up aimed at a gap. Decide if they NOW derived the why.
Return JSON: {"gap_closed": bool, "proof_sentence": str, "used_jargon": bool}"""


def groq_json(system, user):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(r.choices[0].message.content)


# ---------- game state ----------
def new_game():
    return {"xp": 0, "mastered": [], "badges": [], "streak": 0,
            "phase": "idle", "concept": None, "exp1": "", "gap": "", "followup": ""}


LEVELS = [(0, "Novice"), (100, "Apprentice"), (250, "Systems Thinker"),
          (450, "Architect"), (700, "Systems Sage")]


def level_name(xp):
    name = LEVELS[0][1]
    for threshold, n in LEVELS:
        if xp >= threshold:
            name = n
    return name


def add_badge(g, badge):
    if badge not in g["badges"]:
        g["badges"].append(badge)


def stats_md(g):
    lvl = level_name(g["xp"])
    nxt = next((t for t, _ in LEVELS if t > g["xp"]), None)
    to_next = f" · {nxt - g['xp']} XP to next level" if nxt else " · max level"
    filled = len(set(g["mastered"]))
    bar = "🟩" * filled + "⬜" * (5 - filled)
    badges = "  ".join(g["badges"]) if g["badges"] else "—"
    return (f"### 🎮 {lvl}  ·  ⭐ {g['xp']} XP{to_next}\n"
            f"**Concepts mastered:** {bar}  ({filled}/5)\n\n"
            f"🔥 **Streak:** {g['streak']}\n\n"
            f"🏅 **Badges:** {badges}")


# ---------- handlers ----------
def start_concept(concept_name, g, chat):
    g = dict(g)
    prompt = PROMPT_BY_NAME[concept_name]
    g["phase"] = "await_exp1"
    g["concept"] = concept_name
    g["exp1"] = ""
    chat = chat + [{"role": "assistant",
                    "content": f"**{concept_name}**\n\n{prompt}\n\n"
                               f"Explain it from scratch — build up the *why*, don't just define it."}]
    return g, chat, stats_md(g)


def send(msg, g, chat):
    g = dict(g)
    msg = (msg or "").strip()
    if not msg:
        return g, chat, stats_md(g), ""
    chat = chat + [{"role": "user", "content": msg}]

    if g["phase"] == "idle":
        chat.append({"role": "assistant", "content": "Pick a concept above and hit **Start** first 🙂"})
        return g, chat, stats_md(g), ""

    cp = PROMPT_BY_NAME[g["concept"]]

    if g["phase"] == "await_exp1":
        g["exp1"] = msg
        out = groq_json(ANALYZE_SYS, f"CONCEPT:\n{cp}\n\nFIRST EXPLANATION:\n{msg}")
        if out.get("first_pass_closed"):
            g["xp"] += 100
            g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🥇 First-Try Genius")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            g["phase"] = "idle"
            proof = out.get("proof_sentence", "")
            chat.append({"role": "assistant",
                         "content": f"✅ **Derived on the first try! +100 XP**\n\n"
                                    f"_Proof:_ “{proof}”\n\nPick another concept to keep leveling up."})
        else:
            g["gap"] = out.get("gap_named", "")
            g["followup"] = out.get("followup", "")
            g["phase"] = "await_exp2"
            chat.append({"role": "assistant",
                         "content": f"🟠 **Gap found**\n\n**Where it became a label:** {g['gap']}\n\n"
                                    f"**One question for you:** {g['followup']}\n\nReason it out 👇"})
        return g, chat, stats_md(g), ""

    if g["phase"] == "await_exp2":
        out = groq_json(JUDGE_SYS,
                        f"CONCEPT:\n{cp}\n\nFIRST EXPLANATION:\n{g['exp1']}\n\n"
                        f"GAP:\n{g['gap']}\n\nFOLLOW-UP:\n{g['followup']}\n\nSECOND EXPLANATION:\n{msg}")
        if out.get("gap_closed"):
            g["xp"] += 50
            g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🔑 Gap Closer")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            proof = out.get("proof_sentence", "")
            chat.append({"role": "assistant",
                         "content": f"✅ **Gap closed! +50 XP**\n\n_Proof:_ “{proof}”\n\n"
                                    f"🔥 Streak {g['streak']}. Pick another concept!"})
        else:
            g["streak"] = 0
            chat.append({"role": "assistant",
                         "content": "❌ **Not yet** — that still didn't derive the *why*. "
                                    "Streak reset. Try a different concept and come back to this one."})
        g["phase"] = "idle"
        return g, chat, stats_md(g), ""

    return g, chat, stats_md(g), ""


def reset():
    g = new_game()
    return g, [], stats_md(g), ""


# ---------- UI ----------
with gr.Blocks(title="Concept Check — Game") as demo:
    gr.Markdown("# 🧩 Concept Check\nDo you *understand* a concept, or just know the words? "
                "Derive the **why** to earn XP, badges, and level up.")
    game = gr.State(new_game())
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=420, label="Quiz-master")
            with gr.Row():
                box = gr.Textbox(placeholder="Type your explanation...", scale=4, show_label=False)
                send_btn = gr.Button("Send", variant="primary", scale=1)
        with gr.Column(scale=1):
            stats = gr.Markdown(stats_md(new_game()))
            concept_dd = gr.Dropdown([n for n, _ in CONCEPTS], label="Pick a concept",
                                     value=CONCEPTS[0][0])
            start_btn = gr.Button("▶ Start", variant="secondary")
            reset_btn = gr.Button("↺ Reset game")

    start_btn.click(start_concept, [concept_dd, game, chatbot], [game, chatbot, stats])
    send_btn.click(send, [box, game, chatbot], [game, chatbot, stats, box])
    box.submit(send, [box, game, chatbot], [game, chatbot, stats, box])
    reset_btn.click(reset, None, [game, chatbot, stats, box])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)),
                theme=gr.themes.Soft())
