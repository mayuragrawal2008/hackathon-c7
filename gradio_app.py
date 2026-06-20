"""Concept Check — gamified Gradio chat UI (branch: gradio-ui).

Three screens: Landing -> Game -> Results. Standalone presentation layer over the
same boxed LLM judge (Groq / Llama 3.3). The graded submission remains the baseline
HTML app on `main` (which holds the auth + row-level-security proof).

Palette: cyber-neon (cyan/electric-blue) reused from the team_bash project.
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
            f"**Mastered:** {bar}  ({filled}/5)\n\n"
            f"🔥 **Streak:** {g['streak']}\n\n"
            f"🏅 **Badges:** {badges}")


def stats_html(g):
    lvl = level_name(g["xp"])
    filled = len(set(g["mastered"]))
    bar = "🟩" * filled + "⬜" * (5 - filled)
    badges = "  ".join(g["badges"]) if g["badges"] else "—"
    return (f"<div class='statsbox'>"
            f"<div>🎮 <b>{lvl}</b> · ⭐ {g['xp']} XP</div>"
            f"<div>Mastered: {bar} ({filled}/5)</div>"
            f"<div>🔥 Streak: {g['streak']}</div>"
            f"<div>🏅 Badges: {badges}</div></div>")


def result_md(g, headline, klass, proof, gained):
    body = f"<div class='resultcard {klass}'>"
    body += f"<div class='resulthead'>{headline}</div>"
    if gained:
        body += f"<div class='xpgain'>+{gained} XP</div>"
    if proof:
        body += f"<div class='proof'>“{proof}”</div>"
    body += "</div>"
    return body + stats_html(g)


# ---------- handlers ----------
def enter_game():
    return gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)


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
    show_game, show_res = gr.update(visible=True), gr.update(visible=False)
    if not msg:
        return g, chat, stats_md(g), "", "", show_game, show_res
    chat = chat + [{"role": "user", "content": msg}]

    if g["phase"] == "idle":
        chat.append({"role": "assistant", "content": "Pick a concept and hit **▶ Start** first 🙂"})
        return g, chat, stats_md(g), "", "", show_game, show_res

    cp = PROMPT_BY_NAME[g["concept"]]

    if g["phase"] == "await_exp1":
        g["exp1"] = msg
        out = groq_json(ANALYZE_SYS, f"CONCEPT:\n{cp}\n\nFIRST EXPLANATION:\n{msg}")
        if out.get("first_pass_closed"):
            g["xp"] += 100; g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🥇 First-Try Genius")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            g["phase"] = "idle"
            chat.append({"role": "assistant", "content": "✅ Derived on the first try!"})
            res = result_md(g, "✅ Derived on the first try!", "win",
                            out.get("proof_sentence", ""), 100)
            return g, chat, stats_md(g), "", res, gr.update(visible=False), gr.update(visible=True)
        else:
            g["gap"] = out.get("gap_named", "")
            g["followup"] = out.get("followup", "")
            g["phase"] = "await_exp2"
            chat.append({"role": "assistant",
                         "content": f"🟠 **Gap found**\n\n**Where it became a label:** {g['gap']}\n\n"
                                    f"**One question for you:** {g['followup']}\n\nReason it out 👇"})
            return g, chat, stats_md(g), "", "", show_game, show_res

    if g["phase"] == "await_exp2":
        out = groq_json(JUDGE_SYS,
                        f"CONCEPT:\n{cp}\n\nFIRST EXPLANATION:\n{g['exp1']}\n\n"
                        f"GAP:\n{g['gap']}\n\nFOLLOW-UP:\n{g['followup']}\n\nSECOND EXPLANATION:\n{msg}")
        g["phase"] = "idle"
        if out.get("gap_closed"):
            g["xp"] += 50; g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🔑 Gap Closer")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            chat.append({"role": "assistant", "content": "✅ Gap closed!"})
            res = result_md(g, "✅ Gap closed!", "win", out.get("proof_sentence", ""), 50)
        else:
            g["streak"] = 0
            chat.append({"role": "assistant", "content": "❌ Not closed."})
            res = result_md(g, "❌ Gap not closed — that didn't derive the why.", "lose", "", 0)
        return g, chat, stats_md(g), "", res, gr.update(visible=False), gr.update(visible=True)

    return g, chat, stats_md(g), "", "", show_game, show_res


def next_round():
    return [], gr.update(visible=True), gr.update(visible=False)


def reset_all():
    g = new_game()
    return (g, [], stats_md(g), "", "",
            gr.update(visible=True), gr.update(visible=False), gr.update(visible=False))


# ---------- palette + CSS (cyber-neon, from team_bash) ----------
CSS = """
:root{
  --bg-core:#050508; --bg-card:rgba(13,14,24,0.72); --bg-soft:rgba(5,5,8,0.6);
  --border-glow:rgba(0,242,254,0.30); --primary:#00f2fe; --secondary:#4facfe;
  --success:#00ff87; --danger:#ff0055; --text-main:#e2e8f0; --text-muted:#94a3b8;
}
.gradio-container{
  background:
    radial-gradient(circle at 12% 18%, rgba(0,242,254,0.07) 0%, transparent 42%),
    radial-gradient(circle at 88% 82%, rgba(79,172,254,0.07) 0%, transparent 42%),
    radial-gradient(circle at 50% 50%, rgba(127,0,255,0.04) 0%, transparent 55%),
    var(--bg-core) !important;
  color: var(--text-main) !important;
  font-family: 'Outfit', -apple-system, sans-serif !important;
}
.gradio-container .block, .gradio-container .form, .gradio-container .panel,
.gradio-container .gr-group { background: transparent !important; border: none !important; }
/* inputs + dropdowns */
textarea, input[type=text], select, .gradio-container .wrap, .gradio-container .container input{
  background: var(--bg-soft) !important; color: var(--text-main) !important;
  border: 1px solid var(--border-glow) !important; border-radius: 10px !important;
}
::placeholder{ color: var(--text-muted) !important; }
/* chatbot — kill the white box */
#cc-chat{ background: var(--bg-card) !important; border: 1px solid var(--border-glow) !important;
          border-radius: 14px !important; box-shadow: 0 0 18px rgba(0,242,254,0.10); }
#cc-chat *{ color: var(--text-main) !important; }
#cc-chat .user, #cc-chat .bot, #cc-chat .message{ background: rgba(5,5,8,0.55) !important;
          border: 1px solid rgba(0,242,254,0.18) !important; }
/* hide chatbot's built-in toolbar icons + empty avatar squares */
#cc-chat .icon-button-wrapper, #cc-chat .avatar-container,
#cc-chat button[aria-label], #cc-chat .image-button{ display:none !important; }
/* all component labels readable (Quiz-master, 1) Pick a concept, etc.) */
.gradio-container label, .gradio-container .label-wrap span,
.gradio-container .block-label, .gradio-container span[data-testid="block-info"]{
  color:#7df9ff !important; opacity:1 !important; }
/* kill the light pill behind component labels (e.g. "Quiz-master") */
.gradio-container .label-wrap, .gradio-container .block-label,
#cc-chat .label-wrap, #cc-chat .block-label{
  background: transparent !important; border: none !important; box-shadow: none !important; }
.gradio-container .block-label svg, #cc-chat .block-label svg{ fill:#7df9ff !important; color:#7df9ff !important; }
/* dropdown menu styling */
#concept-dd input, #concept-dd .wrap-inner, #concept-dd .secondary-wrap{
  background: var(--bg-soft) !important; color: var(--text-main) !important; }
ul.options, .options, #concept-dd ul{
  background:#0a0c18 !important; color: var(--text-main) !important;
  border:1px solid var(--border-glow) !important; }
ul.options li, .options li{ color: var(--text-main) !important; background: transparent !important; }
ul.options li:hover, .options li.selected, .options li.active{
  background: rgba(0,242,254,0.18) !important; color:#7df9ff !important; }
/* my own chatbot caption (replaces the white label pill) */
.cc-caption{ color:#7df9ff !important; font-weight:700; font-size:1rem; padding:2px 2px 6px; }
#cc-result{ min-height:80px; }
.statsbox{ background:var(--bg-card); border:1px solid var(--border-glow); border-radius:12px;
  padding:14px 16px; margin-top:6px; color:var(--text-main); line-height:1.8; }
.statsbox b{ color:#7df9ff; }
/* readable markdown */
#cc-stats, #cc-stats *{ color: var(--text-main) !important; }
/* titles */
#hero h1, #cc-title{ font-weight:800; background: linear-gradient(135deg,#00f2fe,#4facfe);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
#cc-title{ font-size:1.7rem; padding:4px 2px 8px; }
#hero{ text-align:center; padding:30px 18px 6px; }
#hero h1{ font-size:2.7rem; margin:0; }
#hero p{ color:#cbd5e1; font-size:1.05rem; max-width:560px; margin:10px auto; }
/* emphasized words must stay readable (neon highlight, not dim) */
#hero b, #hero strong, #hero i, #hero em,
.pitchcard b, .pitchcard strong, .pitchcard i, .pitchcard em{
  color:#7df9ff !important; font-style:normal; }
/* cards */
.pitchcard, #topbar{ background: var(--bg-card); border:1px solid var(--border-glow);
  border-radius:14px; box-shadow: 0 0 18px rgba(0,242,254,0.08); }
.pitchcard{ padding:16px 18px; margin:10px auto; max-width:620px; color:#dbe4f0; line-height:1.6; }
#topbar{ padding:12px 14px; margin-bottom:12px; }
.pillrow{ display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin:6px 0 2px; }
.pill{ background:rgba(0,242,254,0.10); border:1px solid var(--border-glow); color:#7df9ff;
  border-radius:999px; padding:4px 12px; font-size:.85rem; }
/* buttons */
.gradio-container button.primary, .gradio-container .primary{
  background: linear-gradient(135deg,#00f2fe,#4facfe) !important; color:#001018 !important;
  border:none !important; box-shadow:0 0 16px rgba(0,242,254,0.40) !important; font-weight:700 !important; }
.gradio-container button.secondary{ background: var(--bg-soft) !important;
  color: var(--primary) !important; border:1px solid var(--border-glow) !important; }
/* result cards */
.resultcard{ border-radius:18px; padding:26px; text-align:center; margin:8px 0 14px;
  border:1px solid var(--border-glow); }
.resultcard.win{ background:linear-gradient(160deg, rgba(0,255,135,.14), rgba(0,242,254,.08));
  box-shadow:0 0 22px rgba(0,255,135,.15); }
.resultcard.lose{ background:linear-gradient(160deg, rgba(255,0,85,.14), rgba(127,0,255,.08));
  box-shadow:0 0 22px rgba(255,0,85,.12); }
.resulthead{ font-size:1.6rem; font-weight:700; color:var(--text-main); }
.xpgain{ font-size:2.2rem; font-weight:800; color:var(--success); margin:8px 0; }
.proof{ font-style:italic; color:#cfe9ff; margin-top:10px; }
"""

THEME = gr.themes.Base(
    primary_hue="cyan", secondary_hue="blue", neutral_hue="slate",
    font=[gr.themes.GoogleFont("Outfit"), "sans-serif"],
)

with gr.Blocks(title="Concept Check — Game") as demo:
    game = gr.State(new_game())

    # -------- SCREEN 1: LANDING --------
    with gr.Column(visible=True) as landing:
        gr.HTML("""
        <div id='hero'>
          <h1>🧩 Concept Check</h1>
          <p>Anyone can <i>recognize</i> the words — the model defines them for free.
             The one thing still yours is whether you can <b>derive a concept from scratch</b>.</p>
        </div>
        <div class='pitchcard'>
          <b>How it works</b><br>
          Pick a systems concept. Explain it in your own words. The quiz-master finds the
          exact spot your explanation becomes a memorized label, asks <b>one</b> sharp
          question, and checks if you can now derive the <i>why</i> — judged on reasoning,
          <b>not jargon</b>.
          <div class='pillrow' style='margin-top:12px'>
            <span class='pill'>⭐ Earn XP</span>
            <span class='pill'>🏅 Unlock badges</span>
            <span class='pill'>🔥 Build streaks</span>
            <span class='pill'>🎮 Level up</span>
          </div>
        </div>
        """)
        enter_btn = gr.Button("▶  Start Playing", variant="primary")

    # -------- SCREEN 2: GAME --------
    with gr.Column(visible=False) as game_screen:
        gr.HTML("<div id='cc-title'>🧩 Concept Check</div>")
        # TOP BAR: concept picker + Start (so users start here, no confusion)
        with gr.Row(elem_id="topbar"):
            concept_dd = gr.Dropdown([n for n, _ in CONCEPTS], label="1) Pick a concept",
                                     value=CONCEPTS[0][0], scale=4, elem_id="concept-dd")
            start_btn = gr.Button("▶ Start", variant="primary", scale=1)
        with gr.Row():
            with gr.Column(scale=2):
                gr.HTML("<div class='cc-caption'>💬 Quiz-Master</div>")
                chatbot = gr.Chatbot(height=420, show_label=False, elem_id="cc-chat")
                with gr.Row():
                    box = gr.Textbox(placeholder="2) Type your explanation...", scale=4, show_label=False)
                    send_btn = gr.Button("Send", variant="primary", scale=1)
            with gr.Column(scale=1):
                stats = gr.Markdown(stats_md(new_game()), elem_id="cc-stats")
                reset_btn = gr.Button("↺ Reset game", variant="secondary")

    # -------- SCREEN 3: RESULTS --------
    with gr.Column(visible=False) as results_screen:
        gr.HTML("<div id='cc-title'>🏁 Round Result</div>")
        results_md = gr.HTML(elem_id="cc-result")
        with gr.Row():
            next_btn = gr.Button("➡ Next concept", variant="primary")
            reset_btn2 = gr.Button("↺ Reset game", variant="secondary")

    # -------- wiring --------
    enter_btn.click(enter_game, None, [landing, game_screen, results_screen])
    start_btn.click(start_concept, [concept_dd, game, chatbot], [game, chatbot, stats])
    send_btn.click(send, [box, game, chatbot],
                   [game, chatbot, stats, box, results_md, game_screen, results_screen])
    box.submit(send, [box, game, chatbot],
               [game, chatbot, stats, box, results_md, game_screen, results_screen])
    next_btn.click(next_round, None, [chatbot, game_screen, results_screen])
    reset_btn.click(reset_all, None,
                    [game, chatbot, stats, box, results_md, landing, game_screen, results_screen])
    reset_btn2.click(reset_all, None,
                     [game, chatbot, stats, box, results_md, landing, game_screen, results_screen])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)),
                css=CSS, theme=THEME)
