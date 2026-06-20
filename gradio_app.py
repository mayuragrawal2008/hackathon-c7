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
    ("Why do we cache?",
     "From first principles, why do systems cache data? What does caching trade off, and what breaks without it?"),
    ("Why do APIs have rate limits?",
     "Why would a service limit how many requests you can make? What breaks if there were no limit?"),
    ("Why do we use HTTPS / encryption in transit?",
     "Why encrypt data travelling over the internet? What exactly goes wrong if it's sent in plain text?"),
    ("Why do we need a load balancer?",
     "From first principles, why put a load balancer in front of servers? What breaks at scale without one?"),
    ("Why do databases use indexes?",
     "Why does a database need an index? What is the trade-off, and what happens to queries without one?"),
    ("Why use a queue / async processing?",
     "Why process some work asynchronously through a queue instead of doing it immediately? What breaks if everything is synchronous?"),
    ("Why do we design servers to be stateless?",
     "What does it mean for a server to be stateless, and why is that useful? What breaks if each server holds its own state?"),
    ("Why do we version APIs?",
     "Why give an API a version? What breaks for existing users if you change an API without versioning?"),
    ("Why do we use a CDN?",
     "From first principles, why serve content from a CDN? What problem does distance/geography create that a CDN solves?"),
    ("Why hash passwords instead of storing them?",
     "Why store a hash of a password rather than the password itself? What exactly is the danger of storing plain passwords?"),
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

# Socratic tutor: leads the learner to derive the WHY themselves through questions only.
SOCRATIC_SYS = RULES + """

You are a SOCRATIC TUTOR. Lead the learner to DERIVE the concept's WHY entirely by
themselves, using questions only.
TUTOR RULES:
- NEVER state the answer, give facts, or say "correct/wrong" mid-dialogue.
- Ask exactly ONE short question per turn. Build on what the learner JUST said. Push for
  the cause ("why must that be true?", "what breaks if it weren't?"), and probe deeper
  wherever they are vague or circular. Adapt to their answers.
- Using the rigor rules above, judge whether across the WHOLE dialogue the LEARNER has now
  themselves stated the explicit cause->effect WHY (not you).
Return JSON:
{"derived": bool, "proof_sentence": str, "next_question": str, "used_jargon": bool}
- derived=true ONLY when they articulated the causal why themselves -> next_question="".
- derived=false -> next_question = the single next Socratic question."""


def socratic_step(concept_prompt, dialogue):
    convo = "\n".join(f"{who.capitalize()}: {text}" for who, text in dialogue)
    user = f"CONCEPT:\n{concept_prompt}\n\nDIALOGUE SO FAR:\n{convo}"
    return groq_json(SOCRATIC_SYS, user)


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
MAX_TURNS = 5  # max Socratic questions before revealing


def new_game():
    return {"xp": 0, "mastered": [], "badges": [], "streak": 0, "phase": "idle",
            "concept": None, "exp1": "", "turns": 0, "dialogue": [],
            "session_id": None, "attempt_id": None}


LEVELS = [(0, "Novice"), (100, "Apprentice"), (250, "Systems Thinker"),
          (450, "Architect"), (700, "Systems Sage"), (1000, "Grandmaster")]


def level_name(xp):
    name = LEVELS[0][1]
    for threshold, n in LEVELS:
        if xp >= threshold:
            name = n
    return name


def add_badge(g, badge):
    if badge not in g["badges"]:
        g["badges"].append(badge)


def award_milestones(g):
    """Streak / mastery badges, checked after a win."""
    if g["streak"] >= 3:
        add_badge(g, "🔥 Hot Streak")
    if g["streak"] >= 5:
        add_badge(g, "💎 Unstoppable")
    if len(set(g["mastered"])) >= len(CONCEPTS):
        add_badge(g, "🎓 Polymath")


# every badge in the game + how to earn it (for the hover menu)
ALL_BADGES = [
    ("🥇 First-Try Genius", "Derive the why on your first explanation"),
    ("🦉 Socratic Thinker", "Reason to the why through the tutor's questions"),
    ("⚡ One-Question Wonder", "Derive it after just one Socratic question"),
    ("🧠 No-Jargon Master", "Derive it in plain language, no jargon"),
    ("🔥 Hot Streak", "Win 3 rounds in a row"),
    ("💎 Unstoppable", "Win 5 rounds in a row"),
    ("🎓 Polymath", "Master all 15 concepts"),
]


def earned_html(badges):
    if not badges:
        inner = "<div style='color:#9fb0c8'>No badges yet — play to earn them!</div>"
    else:
        inner = "".join(f"<div>{b}</div>" for b in badges)
    return ("<div class='statsbox'><div style='color:#7df9ff;font-weight:700;margin-bottom:6px'>"
            f"🏅 Your badges</div>{inner}</div>")


def _bar(g, segs=10):
    total = len(CONCEPTS)
    filled = len(set(g["mastered"]))
    on = round(segs * filled / total) if total else 0
    return "🟩" * on + "⬜" * (segs - on), filled, total


def stats_md(g):
    lvl = level_name(g["xp"])
    nxt = next((t for t, _ in LEVELS if t > g["xp"]), None)
    to_next = f" · {nxt - g['xp']} XP to next level" if nxt else " · max level"
    bar, filled, total = _bar(g)
    badges = "  ".join(g["badges"]) if g["badges"] else "—"
    return (f"### 🎮 {lvl}  ·  ⭐ {g['xp']} XP{to_next}\n"
            f"**Mastered:** {bar}  ({filled}/{total})\n\n🔥 **Streak:** {g['streak']}\n\n"
            f"🏅 **Badges:** {badges}")


def stats_html(g):
    lvl = level_name(g["xp"])
    bar, filled, total = _bar(g)
    badges = "  ".join(g["badges"]) if g["badges"] else "—"
    return (f"<div class='statsbox'><div>🎮 <b>{lvl}</b> · ⭐ {g['xp']} XP</div>"
            f"<div>Mastered: {bar} ({filled}/{total})</div><div>🔥 Streak: {g['streak']}</div>"
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
    prompt = PROMPT_BY_NAME[concept_name]
    g["phase"] = "await_exp1"; g["concept"] = concept_name; g["exp1"] = ""
    g["session_id"] = None; g["attempt_id"] = None
    g["turns"] = 0
    g["dialogue"] = [("tutor", prompt)]
    chat = chat + [{"role": "assistant",
                    "content": f"**{concept_name}**\n\n{prompt}\n\n"
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

    # record the learner's turn in the dialogue
    g["dialogue"] = list(g["dialogue"]) + [("learner", msg)]

    # ----- FIRST explanation: open the Socratic session + persist -----
    if g["phase"] == "await_exp1":
        g["exp1"] = msg
        out = socratic_step(cp, g["dialogue"])
        derived = bool(out.get("derived"))
        try:
            sess = sb_insert("sessions", {"concept_id": cid}, token)
            g["session_id"] = sess["id"]
            att = sb_insert("attempts", {
                "session_id": sess["id"], "concept_id": cid, "explanation_1": msg,
                "first_pass_closed": derived,
                "gap_named": "", "followup": out.get("next_question", "")}, token)
            g["attempt_id"] = att["id"]
        except Exception:
            pass
        if derived:  # nailed it with no Socratic help
            g["xp"] += 100; g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🥇 First-Try Genius")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            award_milestones(g)
            g["phase"] = "idle"
            chat.append({"role": "assistant", "content": "✅ Derived on the first try!"})
            res = result_html("✅ Derived on the first try!", "win",
                              out.get("proof_sentence", ""), 100, g, explain_concept(cp))
            return g, chat, stats_md(g), "", res
        # begin the Socratic dialogue
        q = out.get("next_question", "") or "Why do you think that has to be the case?"
        g["dialogue"].append(("tutor", q))
        g["turns"] = 1
        g["phase"] = "socratic"
        chat.append({"role": "assistant", "content": f"🤔 {q}"})
        return g, chat, stats_md(g), "", ""

    # ----- ongoing Socratic dialogue -----
    if g["phase"] == "socratic":
        out = socratic_step(cp, g["dialogue"])
        derived = bool(out.get("derived"))
        if derived:
            g["phase"] = "idle"
            gained = max(40, 90 - 10 * g["turns"])  # fewer questions -> more XP
            g["xp"] += gained; g["streak"] += 1
            if g["concept"] not in g["mastered"]:
                g["mastered"].append(g["concept"])
            add_badge(g, "🦉 Socratic Thinker")
            if g["turns"] == 1:
                add_badge(g, "⚡ One-Question Wonder")
            if not out.get("used_jargon"):
                add_badge(g, "🧠 No-Jargon Master")
            award_milestones(g)
            try:
                if g.get("attempt_id"):
                    sb_update("attempts", g["attempt_id"], {
                        "explanation_2": msg, "gap_closed": True,
                        "proof_sentence": out.get("proof_sentence", "")}, token)
            except Exception:
                pass
            chat.append({"role": "assistant", "content": "✅ You reasoned your way there!"})
            res = result_html("✅ You reasoned your way there!", "win",
                              out.get("proof_sentence", ""), gained, g, explain_concept(cp))
            return g, chat, stats_md(g), "", res

        if g["turns"] >= MAX_TURNS:  # out of questions
            g["phase"] = "idle"; g["streak"] = 0
            try:
                if g.get("attempt_id"):
                    sb_update("attempts", g["attempt_id"], {
                        "explanation_2": msg, "gap_closed": False, "proof_sentence": ""}, token)
            except Exception:
                pass
            chat.append({"role": "assistant", "content": "We'll pause here — let's look at it together."})
            res = result_html("🟡 Not quite — but here's the reasoning.", "lose", "", 0, g,
                              explain_concept(cp))
            return g, chat, stats_md(g), "", res

        # ask the next Socratic question
        q = out.get("next_question", "") or "And why does that matter?"
        g["dialogue"].append(("tutor", q))
        g["turns"] += 1
        chat.append({"role": "assistant", "content": f"🤔 {q}"})
        return g, chat, stats_md(g), "", ""

    return g, chat, stats_md(g), "", ""


def reset_all():
    g = new_game()
    return g, [], stats_md(g), "", ""


def do_logout():
    """Clear the session and bring back the login bar. Outputs:
    auth, auth_status, login_bar, game, chatbot, stats, result_box, history_box, badges_earned."""
    g = new_game()
    return ({"token": None, "email": None},
            "🔒 Logged out. Log in to play.",
            gr.update(visible=True),
            g, [], stats_md(g), "", "", earned_html([]))


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


def load_progress(auth, g):
    """On login: rebuild prior badges / XP / mastery from the user's own history (RLS).
    Outputs: game, stats, earned-badges HTML."""
    token = auth.get("token") if auth else None
    if not token:
        return g, stats_md(g), earned_html([])
    try:
        url = (f"{SB_URL}/rest/v1/attempts?select=concept_id,first_pass_closed,gap_closed"
               f"&order=created_at")
        rows = _req("GET", url, {"apikey": SB_ANON, "Authorization": f"Bearer {token}"})
    except Exception:
        return g, stats_md(g), earned_html([])
    g = dict(g)
    mastered, badges, ft, soc = set(), [], 0, 0
    for a in rows or []:
        if a.get("first_pass_closed"):
            ft += 1; mastered.add(a.get("concept_id"))
        elif a.get("gap_closed"):
            soc += 1; mastered.add(a.get("concept_id"))
    if ft:
        badges.append("🥇 First-Try Genius")
    if soc:
        badges.append("🦉 Socratic Thinker")
    if len(mastered) >= len(CONCEPTS):
        badges.append("🎓 Polymath")
    g["mastered"] = [NAME_BY_ID[c] for c in mastered if c in NAME_BY_ID]
    g["badges"] = badges
    g["xp"] = 100 * ft + 60 * soc  # approx restore (turn counts aren't stored)
    return g, stats_md(g), earned_html(badges)


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
/* floating badges background */
.float-bg{ position:fixed; inset:0; overflow:hidden; pointer-events:none; z-index:0; }
.float-bg span{ position:absolute; bottom:-60px; opacity:0; will-change:transform;
  animation:floatUp linear infinite; filter:drop-shadow(0 0 6px rgba(0,242,254,.4)); }
@keyframes floatUp{
  0%{ transform:translateY(0) rotate(0deg); opacity:0; }
  12%{ opacity:.5; }
  88%{ opacity:.5; }
  100%{ transform:translateY(-115vh) rotate(320deg); opacity:0; } }
/* keep interactive content above the floating layer */
.gradio-container .block{ position:relative; z-index:1; }
/* all-badges hover menu */
.badge-help{ position:relative; display:inline-block; cursor:help; color:#7df9ff; font-weight:700;
  border:1px solid var(--border-glow); border-radius:10px; padding:6px 10px; margin-top:8px; }
.badge-tip{ display:none; position:absolute; right:0; bottom:120%; width:270px; z-index:50;
  background:#0a0c18; border:1px solid var(--border-glow); border-radius:12px; padding:12px 14px;
  box-shadow:0 0 22px rgba(0,242,254,.3); color:#e8edf6; font-weight:400; line-height:1.4; text-align:left; }
.badge-tip > div{ margin-bottom:9px; } .badge-tip b{ color:#7df9ff; }
.badge-help:hover .badge-tip{ display:block; }
"""

BADGE_HELP_HTML = ("<div class='badge-help'>❓ Badges you can earn<div class='badge-tip'>"
                   + "".join(f"<div><b>{n}</b><br><span style='color:#9fb0c8'>{h}</span></div>"
                             for n, h in ALL_BADGES)
                   + "</div></div>")

import random as _random
_BADGE_EMOJIS = ["🥇", "🦉", "⚡", "🧠", "🔥", "💎", "🎓", "🏅", "⭐", "🧩", "🔑", "🚀"]
_random.seed(7)
_spans = "".join(
    f"<span style='left:{_random.randint(2, 95)}%;font-size:{_random.randint(20, 40)}px;"
    f"animation-duration:{_random.randint(16, 32)}s;animation-delay:-{_random.randint(0, 28)}s'>"
    f"{_random.choice(_BADGE_EMOJIS)}</span>"
    for _ in range(22)
)
FLOAT_HTML = f"<div class='float-bg'>{_spans}</div>"

THEME = gr.themes.Base(
    primary_hue="cyan", secondary_hue="blue", neutral_hue="slate",
    font=[gr.themes.GoogleFont("Outfit"), "sans-serif"],
)

with gr.Blocks(title="Concept Check — Game") as demo:
    gr.HTML(FLOAT_HTML)  # floating badges background (decorative)
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
          <b>How it works — the Socratic way</b><br>
          Log in, pick a systems concept, and explain it in your own words. A <b>Socratic
          tutor</b> never hands you the answer — it asks one probing question at a time,
          building on what you said, until <i>you</i> derive the <b>why</b> yourself. Judged
          on reasoning, <b>not jargon</b>. Your progress is saved privately to your account.
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
                gr.HTML("<div class='cc-caption'>🦉 Socratic Tutor</div>")
                chatbot = gr.Chatbot(height=400, show_label=False, elem_id="cc-chat")
                with gr.Row():
                    box = gr.Textbox(placeholder="2) Type your explanation...", scale=4, show_label=False)
                    send_btn = gr.Button("Send", variant="primary", scale=1)
            with gr.Column(scale=1):
                stats = gr.Markdown(stats_md(new_game()), elem_id="cc-stats")
                badges_earned = gr.HTML(earned_html([]))
                gr.HTML(BADGE_HELP_HTML)
                reset_btn = gr.Button("↺ Reset game", variant="secondary")
                logout_btn = gr.Button("🚪 Log out", variant="secondary")
                hist_btn = gr.Button("📜 My history", variant="secondary")
                history_box = gr.HTML()

    # -------- wiring --------
    enter_btn.click(enter_game, None, [landing, play_view])
    login_btn.click(do_login, [login_email, login_pw, auth], [auth, auth_status, login_bar]
                    ).then(my_history, auth, history_box
                    ).then(load_progress, [auth, game], [game, stats, badges_earned])
    signup_btn.click(do_signup, [login_email, login_pw, auth], [auth, auth_status, login_bar]
                     ).then(my_history, auth, history_box
                     ).then(load_progress, [auth, game], [game, stats, badges_earned])
    start_btn.click(start_concept, [concept_dd, game, chatbot, auth], [game, chatbot, stats, result_box])
    send_btn.click(send, [box, game, chatbot, auth], [game, chatbot, stats, box, result_box]
                   ).then(my_history, auth, history_box)
    box.submit(send, [box, game, chatbot, auth], [game, chatbot, stats, box, result_box]
               ).then(my_history, auth, history_box)
    reset_btn.click(reset_all, None, [game, chatbot, stats, box, result_box])
    logout_btn.click(do_logout, None,
                     [auth, auth_status, login_bar, game, chatbot, stats, result_box,
                      history_box, badges_earned])
    hist_btn.click(my_history, auth, history_box)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)),
                css=CSS, theme=THEME)
