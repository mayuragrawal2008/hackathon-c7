"""Concept Check — gamified Gradio chat UI WITH auth + row-level security (gradio-ui).

Landing -> Play (single screen; result banner appears on top). A login bar at the top
authenticates against Supabase; sessions/attempts are written to the same Postgres DB
with the user's token, so row-level security applies (each user sees only their own
rows). Same boxed Llama 3.3 judge + evals as the baseline.

Note on Gradio 6.19: revealing a hidden Column after content updates crashes the
frontend, so we never do that mid-session — login uses content-only updates and the
result is an inline banner.
"""
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

import gradio as gr
from groq import Groq


# ---------- env + clients ----------
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
SB_URL = os.environ.get("SUPABASE_URL", "")
SB_ANON = os.environ.get("SUPABASE_ANON_KEY", "")

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
# DB concepts were seeded in this exact order -> ids 1..5
CONCEPT_ID = {n: i + 1 for i, (n, _) in enumerate(CONCEPTS)}
NAME_BY_ID = {i + 1: n for i, (n, _) in enumerate(CONCEPTS)}


# ---------- Supabase REST helpers (auth + RLS-protected writes) ----------
def _req(method, url, headers, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        txt = r.read().decode()
        return (json.loads(txt) if txt else None)


def sb_auth(email, password, signup=False):
    """Returns (token, email, error)."""
    url = f"{SB_URL}/auth/v1/signup" if signup else f"{SB_URL}/auth/v1/token?grant_type=password"
    headers = {"apikey": SB_ANON, "Content-Type": "application/json"}
    try:
        d = _req("POST", url, headers, {"email": email, "password": password})
        if d and d.get("access_token"):
            em = (d.get("user") or {}).get("email", email)
            return d["access_token"], em, None
        if d and d.get("id"):  # signup with email-confirm on (no token yet)
            return None, email, "account created — now log in"
        return None, None, "could not authenticate"
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("msg", "auth error")
        except Exception:
            msg = "auth error"
        return None, None, msg
    except Exception:
        return None, None, "network error"


def sb_insert(table, payload, token):
    url = f"{SB_URL}/rest/v1/{table}"
    headers = {"apikey": SB_ANON, "Authorization": f"Bearer {token}",
               "Content-Type": "application/json", "Prefer": "return=representation"}
    d = _req("POST", url, headers, payload)
    return d[0] if isinstance(d, list) and d else d


def sb_update(table, row_id, payload, token):
    url = f"{SB_URL}/rest/v1/{table}?id=eq.{row_id}"
    headers = {"apikey": SB_ANON, "Authorization": f"Bearer {token}",
               "Content-Type": "application/json", "Prefer": "return=representation"}
    _req("PATCH", url, headers, payload)


# ---------- LLM (evals) ----------
RULES = """You judge whether a learner UNDERSTANDS a systems concept by testing whether
they DERIVE THE "WHY" from first principles: why the thing must exist, or what concretely
breaks without it, as cause -> effect.
HARD RULES:
- Judge the causal reasoning, NOT vocabulary. A correct plain-language answer with zero
  technical jargon is a PASS.
- Do NOT be agreeable. Restating the term, defining it, listing features, or deflecting
  ("it's just how it works") is NOT a derivation.
- RIGOR: passing requires an EXPLICIT cause -> effect link — state what happens AND the
  reason it follows (X, THEREFORE Y, BECAUSE ...). Merely naming an outcome with no
  connecting mechanism is NOT enough; a vague one-liner ("then everyone has their own
  version") does NOT pass. Plain language is fine; a missing causal link is not.
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

EXPLAIN_SYS = """Give a concise, first-principles explanation of the concept, in plain
language (4-6 sentences). Focus on WHY it must exist and what concretely breaks without
it — the causal story, not a jargon dump. Plain text only, no markdown headers."""


def groq_json(system, user):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"}, temperature=0.2,
    )
    return json.loads(r.choices[0].message.content)


def explain_concept(concept_prompt):
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": EXPLAIN_SYS},
                      {"role": "user", "content": f"CONCEPT:\n{concept_prompt}"}],
            temperature=0.3,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return ""


# ---------- game state ----------
def new_game():
    return {"xp": 0, "mastered": [], "badges": [], "streak": 0, "phase": "idle",
            "concept": None, "exp1": "", "gap": "", "followup": "",
            "session_id": None, "attempt_id": None}


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
            f"**Mastered:** {bar}  ({filled}/5)\n\n🔥 **Streak:** {g['streak']}\n\n"
            f"🏅 **Badges:** {badges}")


def stats_html(g):
    lvl = level_name(g["xp"])
    filled = len(set(g["mastered"]))
    bar = "🟩" * filled + "⬜" * (5 - filled)
    badges = "  ".join(g["badges"]) if g["badges"] else "—"
    return (f"<div class='statsbox'><div>🎮 <b>{lvl}</b> · ⭐ {g['xp']} XP</div>"
            f"<div>Mastered: {bar} ({filled}/5)</div><div>🔥 Streak: {g['streak']}</div>"
            f"<div>🏅 Badges: {badges}</div></div>")


def result_html(headline, klass, proof, gained, g, explanation=""):
    body = "<div id='cc-title'>🏁 Round Result</div>"
    body += f"<div class='resultcard {klass}'><div class='resulthead'>{headline}</div>"
    if gained:
        body += f"<div class='xpgain'>+{gained} XP</div>"
    if proof:
        body += f"<div class='proof'>“{proof}”</div>"
    body += "</div>"
    if explanation:
        body += (f"<div class='explainbox'><div class='explainhead'>📚 The full picture</div>"
                 f"<div>{explanation}</div></div>")
    return body + stats_html(g)


# ---------- auth handlers (content-only updates; hide login bar on success) ----------
def do_auth(email, password, auth, signup):
    auth = dict(auth or {})
    if not email or not password:
        return auth, "⚠️ Enter email and password.", gr.update(visible=True)
    token, em, err = sb_auth(email.strip(), password, signup=signup)
    if token:
        auth["token"] = token; auth["email"] = em
        return auth, f"✅ Logged in as **{em}** — your progress is saved privately.", gr.update(visible=False)
    return auth, f"⚠️ {err or 'authentication failed'}", gr.update(visible=True)


def do_login(email, password, auth):
    return do_auth(email, password, auth, signup=False)


def do_signup(email, password, auth):
    return do_auth(email, password, auth, signup=True)


# ---------- game handlers ----------
def enter_game():
    return gr.update(visible=False), gr.update(visible=True)


def start_concept(concept_name, g, chat, auth):
    if not (auth and auth.get("token")):
        chat = chat + [{"role": "assistant", "content": "🔒 Please log in at the top first."}]
        return g, chat, stats_md(g), ""
    g = dict(g)
    g["phase"] = "await_exp1"; g["concept"] = concept_name; g["exp1"] = ""
    g["session_id"] = None; g["attempt_id"] = None
    chat = chat + [{"role": "assistant",
                    "content": f"**{concept_name}**\n\n{PROMPT_BY_NAME[concept_name]}\n\n"
                               f"Explain it from scratch — build up the *why*, don't just define it."}]
    return g, chat, stats_md(g), ""


def send(msg, g, chat, auth):
    """Outputs: game, chatbot, stats, box, result_box."""
    token = auth.get("token") if auth else None
    g = dict(g)
    msg = (msg or "").strip()
    if not token:
        if msg:
            chat = chat + [{"role": "user", "content": msg}]
        chat.append({"role": "assistant", "content": "🔒 Please log in at the top to play and save progress."})
        return g, chat, stats_md(g), "", ""
    if not msg:
        return g, chat, stats_md(g), "", ""
    chat = chat + [{"role": "user", "content": msg}]

    if g["phase"] == "idle":
        chat.append({"role": "assistant", "content": "Pick a concept and hit **▶ Start** first 🙂"})
        return g, chat, stats_md(g), "", ""

    cp = PROMPT_BY_NAME[g["concept"]]
    cid = CONCEPT_ID[g["concept"]]

    if g["phase"] == "await_exp1":
        g["exp1"] = msg
        out = groq_json(ANALYZE_SYS, f"CONCEPT:\n{cp}\n\nFIRST EXPLANATION:\n{msg}")
        # persist (RLS: rows written with the user's token)
        try:
            sess = sb_insert("sessions", {"concept_id": cid}, token)
            g["session_id"] = sess["id"]
            att = sb_insert("attempts", {
                "session_id": sess["id"], "concept_id": cid, "explanation_1": msg,
                "first_pass_closed": bool(out.get("first_pass_closed")),
                "gap_named": out.get("gap_named", ""), "followup": out.get("followup", "")}, token)
            g["attempt_id"] = att["id"]
        except Exception:
            pass
        if out.get("first_pass_closed"):
            g["xp"] += 100; g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🥇 First-Try Genius")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            g["phase"] = "idle"
            chat.append({"role": "assistant", "content": "✅ Derived on the first try!"})
            res = result_html("✅ Derived on the first try!", "win",
                              out.get("proof_sentence", ""), 100, g, explain_concept(cp))
            return g, chat, stats_md(g), "", res
        g["gap"] = out.get("gap_named", "")
        g["followup"] = out.get("followup", "")
        g["phase"] = "await_exp2"
        chat.append({"role": "assistant",
                     "content": f"🟠 **Gap found**\n\n**Where it became a label:** {g['gap']}\n\n"
                                f"**One question for you:** {g['followup']}\n\nReason it out 👇"})
        return g, chat, stats_md(g), "", ""

    if g["phase"] == "await_exp2":
        out = groq_json(JUDGE_SYS,
                        f"CONCEPT:\n{cp}\n\nFIRST EXPLANATION:\n{g['exp1']}\n\n"
                        f"GAP:\n{g['gap']}\n\nFOLLOW-UP:\n{g['followup']}\n\nSECOND EXPLANATION:\n{msg}")
        g["phase"] = "idle"
        closed = bool(out.get("gap_closed"))
        try:
            if g.get("attempt_id"):
                sb_update("attempts", g["attempt_id"], {
                    "explanation_2": msg, "gap_closed": closed,
                    "proof_sentence": out.get("proof_sentence", "")}, token)
        except Exception:
            pass
        if closed:
            g["xp"] += 50; g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🔑 Gap Closer")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            chat.append({"role": "assistant", "content": "✅ Gap closed!"})
            res = result_html("✅ Gap closed!", "win", out.get("proof_sentence", ""), 50, g,
                              explain_concept(cp))
        else:
            g["streak"] = 0
            chat.append({"role": "assistant", "content": "❌ Not closed."})
            res = result_html("❌ Gap not closed — that didn't derive the why.", "lose", "", 0, g,
                              explain_concept(cp))
        return g, chat, stats_md(g), "", res

    return g, chat, stats_md(g), "", ""


def reset_all():
    g = new_game()
    return g, [], stats_md(g), "", ""


def my_history(auth):
    """Reads ONLY the logged-in user's own attempts (RLS via their token)."""
    token = auth.get("token") if auth else None
    if not token:
        return "<div class='statsbox'>🔒 Log in to see your history.</div>"
    try:
        url = (f"{SB_URL}/rest/v1/attempts?select=concept_id,first_pass_closed,gap_closed,"
               f"explanation_1,created_at&order=created_at.desc")
        headers = {"apikey": SB_ANON, "Authorization": f"Bearer {token}"}
        rows = _req("GET", url, headers)
    except Exception:
        return "<div class='statsbox'>Couldn't load history.</div>"
    if not rows:
        return "<div class='statsbox'>No attempts yet — play a round!</div>"
    items = ""
    for a in rows:
        name = NAME_BY_ID.get(a.get("concept_id"), a.get("concept_id"))
        if a.get("gap_closed") is True:
            badge = "✅ closed"
        elif a.get("gap_closed") is False:
            badge = "❌ not closed"
        elif a.get("first_pass_closed"):
            badge = "✅ first try"
        else:
            badge = "… in progress"
        snippet = (a.get("explanation_1") or "")[:70]
        items += (f"<div style='border-bottom:1px solid rgba(0,242,254,.15);padding:6px 0'>"
                  f"<b style='color:#7df9ff'>{name}</b> — {badge}"
                  f"<br><span style='color:#9fb0c8;font-size:.85rem'>{snippet}…</span></div>")
    return f"<div class='statsbox'><div style='color:#7df9ff;font-weight:700;margin-bottom:6px'>📜 My past attempts</div>{items}</div>"


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
  color: var(--text-main) !important; font-family: 'Outfit', -apple-system, sans-serif !important; }
.gradio-container .block, .gradio-container .form, .gradio-container .panel,
.gradio-container .gr-group { background: transparent !important; border: none !important; }
textarea, input[type=text], input[type=password], select, .gradio-container .wrap, .gradio-container .container input{
  background: var(--bg-soft) !important; color: var(--text-main) !important;
  border: 1px solid var(--border-glow) !important; border-radius: 10px !important; }
::placeholder{ color: var(--text-muted) !important; }
#cc-chat{ background: var(--bg-card) !important; border: 1px solid var(--border-glow) !important;
          border-radius: 14px !important; box-shadow: 0 0 18px rgba(0,242,254,0.10); }
#cc-chat *{ color: var(--text-main) !important; }
#cc-chat .user, #cc-chat .bot, #cc-chat .message{ background: rgba(5,5,8,0.55) !important;
          border: 1px solid rgba(0,242,254,0.18) !important; }
#cc-chat .icon-button-wrapper, #cc-chat .avatar-container,
#cc-chat button[aria-label], #cc-chat .image-button{ display:none !important; }
.gradio-container label, .gradio-container .label-wrap span,
.gradio-container .block-label{ color:#7df9ff !important; opacity:1 !important; }
.gradio-container .label-wrap, .gradio-container .block-label{
  background: transparent !important; border: none !important; box-shadow: none !important; }
ul.options, .options, #concept-dd ul{ background:#0a0c18 !important; color: var(--text-main) !important;
  border:1px solid var(--border-glow) !important; }
ul.options li, .options li{ color: var(--text-main) !important; background: transparent !important; }
ul.options li:hover, .options li.selected, .options li.active{
  background: rgba(0,242,254,0.18) !important; color:#7df9ff !important; }
.cc-caption{ color:#7df9ff !important; font-weight:700; font-size:1rem; padding:2px 2px 6px; }
#cc-result{ min-height:10px; }
.statsbox{ background:var(--bg-card); border:1px solid var(--border-glow); border-radius:12px;
  padding:14px 16px; margin-top:6px; line-height:1.8; }
.statsbox, .statsbox div{ color:#e8edf6 !important; }
.statsbox b{ color:#7df9ff !important; }
#cc-stats, #cc-stats *{ color: var(--text-main) !important; }
#cc-auth, #cc-auth *{ color: var(--text-main) !important; }
#hero h1, #cc-title{ font-weight:800; background: linear-gradient(135deg,#00f2fe,#4facfe);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
#cc-title{ font-size:1.7rem; padding:4px 2px 10px; }
#hero{ text-align:center; padding:30px 18px 6px; }
#hero h1{ font-size:2.7rem; margin:0; }
#hero p{ color:#cbd5e1; font-size:1.05rem; max-width:560px; margin:10px auto; }
#hero b, #hero strong, #hero i, #hero em,
.pitchcard b, .pitchcard strong, .pitchcard i, .pitchcard em{ color:#7df9ff !important; font-style:normal; }
.pitchcard, #topbar, #loginbar{ background: var(--bg-card); border:1px solid var(--border-glow);
  border-radius:14px; box-shadow: 0 0 18px rgba(0,242,254,0.08); }
.pitchcard{ padding:16px 18px; margin:10px auto; max-width:620px; color:#dbe4f0; line-height:1.6; }
#topbar, #loginbar{ padding:12px 14px; margin-bottom:12px; }
.pillrow{ display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin:6px 0 2px; }
.pill{ background:rgba(0,242,254,0.10); border:1px solid var(--border-glow); color:#7df9ff;
  border-radius:999px; padding:4px 12px; font-size:.85rem; }
.gradio-container button.primary, .gradio-container .primary{
  background: linear-gradient(135deg,#00f2fe,#4facfe) !important; color:#001018 !important;
  border:none !important; box-shadow:0 0 16px rgba(0,242,254,0.40) !important; font-weight:700 !important; }
.gradio-container button.secondary{ background: var(--bg-soft) !important;
  color: var(--primary) !important; border:1px solid var(--border-glow) !important; }
.resultcard{ border-radius:18px; padding:26px; text-align:center; margin:8px 0 14px; border:1px solid var(--border-glow); }
.resultcard.win{ background:linear-gradient(160deg, rgba(0,255,135,.14), rgba(0,242,254,.08)); box-shadow:0 0 22px rgba(0,255,135,.15); }
.resultcard.lose{ background:linear-gradient(160deg, rgba(255,0,85,.14), rgba(127,0,255,.08)); box-shadow:0 0 22px rgba(255,0,85,.12); }
.resulthead{ font-size:1.6rem; font-weight:700; color:var(--text-main); }
.xpgain{ font-size:2.2rem; font-weight:800; color:var(--success); margin:8px 0; }
.proof{ font-style:italic; color:#cfe9ff; margin-top:10px; }
.explainbox{ background:var(--bg-card); border:1px solid var(--border-glow); border-radius:14px;
  padding:16px 18px; margin:6px 0 12px; line-height:1.6; }
.explainbox, .explainbox div{ color:#e8edf6 !important; }
.explainhead{ color:#7df9ff !important; font-weight:700; margin-bottom:6px; }
"""

THEME = gr.themes.Base(
    primary_hue="cyan", secondary_hue="blue", neutral_hue="slate",
    font=[gr.themes.GoogleFont("Outfit"), "sans-serif"],
)

with gr.Blocks(title="Concept Check — Game") as demo:
    game = gr.State(new_game())
    auth = gr.State({"token": None, "email": None})

    # -------- LANDING --------
    with gr.Column(visible=True) as landing:
        gr.HTML("""
        <div id='hero'>
          <h1>🧩 Concept Check</h1>
          <p>Anyone can <i>recognize</i> the words — the model defines them for free.
             The one thing still yours is whether you can <b>derive a concept from scratch</b>.</p>
        </div>
        <div class='pitchcard'>
          <b>How it works</b><br>
          Log in, pick a systems concept, and explain it in your own words. The quiz-master
          finds the exact spot your explanation becomes a memorized label, asks <b>one</b>
          sharp question, and checks if you can now derive the <i>why</i> — judged on
          reasoning, <b>not jargon</b>. Your progress is saved privately to your account.
          <div class='pillrow' style='margin-top:12px'>
            <span class='pill'>🔒 Private account</span>
            <span class='pill'>⭐ Earn XP</span>
            <span class='pill'>🏅 Badges</span>
            <span class='pill'>🎮 Level up</span>
          </div>
        </div>
        """)
        enter_btn = gr.Button("▶  Start Playing", variant="primary")

    # -------- PLAY VIEW (single screen) --------
    with gr.Column(visible=False) as play_view:
        gr.HTML("<div id='cc-title'>🧩 Concept Check</div>")

        # LOGIN BAR (hidden once logged in — hiding is safe in Gradio)
        with gr.Row(elem_id="loginbar") as login_bar:
            login_email = gr.Textbox(label="Email", placeholder="you@example.com", scale=2)
            login_pw = gr.Textbox(label="Password", type="password", placeholder="min 6 chars", scale=2)
            login_btn = gr.Button("Log in", variant="primary", scale=1)
            signup_btn = gr.Button("Sign up", variant="secondary", scale=1)
        auth_status = gr.Markdown("🔒 Log in to play — your answers are saved privately to your account.",
                                  elem_id="cc-auth")

        result_box = gr.HTML(elem_id="cc-result")
        with gr.Row(elem_id="topbar"):
            concept_dd = gr.Dropdown([n for n, _ in CONCEPTS], label="1) Pick a concept",
                                     value=CONCEPTS[0][0], scale=4, elem_id="concept-dd")
            start_btn = gr.Button("▶ Start", variant="primary", scale=1)
        with gr.Row():
            with gr.Column(scale=2):
                gr.HTML("<div class='cc-caption'>💬 Quiz-Master</div>")
                chatbot = gr.Chatbot(height=400, show_label=False, elem_id="cc-chat")
                with gr.Row():
                    box = gr.Textbox(placeholder="2) Type your explanation...", scale=4, show_label=False)
                    send_btn = gr.Button("Send", variant="primary", scale=1)
            with gr.Column(scale=1):
                stats = gr.Markdown(stats_md(new_game()), elem_id="cc-stats")
                reset_btn = gr.Button("↺ Reset game", variant="secondary")
                hist_btn = gr.Button("📜 My history", variant="secondary")
                history_box = gr.HTML()

    # -------- wiring --------
    enter_btn.click(enter_game, None, [landing, play_view])
    login_btn.click(do_login, [login_email, login_pw, auth], [auth, auth_status, login_bar]
                    ).then(my_history, auth, history_box)
    signup_btn.click(do_signup, [login_email, login_pw, auth], [auth, auth_status, login_bar]
                     ).then(my_history, auth, history_box)
    start_btn.click(start_concept, [concept_dd, game, chatbot, auth], [game, chatbot, stats, result_box])
    send_btn.click(send, [box, game, chatbot, auth], [game, chatbot, stats, box, result_box]
                   ).then(my_history, auth, history_box)
    box.submit(send, [box, game, chatbot, auth], [game, chatbot, stats, box, result_box]
               ).then(my_history, auth, history_box)
    reset_btn.click(reset_all, None, [game, chatbot, stats, box, result_box])
    hist_btn.click(my_history, auth, history_box)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)),
                css=CSS, theme=THEME)
