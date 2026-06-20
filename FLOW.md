# Concept Check — Flow Diagram

Baseline app (`main` branch): `index.html` (frontend) + `main.py` (FastAPI backend) +
Supabase (DB/Auth/RLS) + Groq/Llama (the judge).

## High-level architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         BROWSER  ·  index.html                             │
│  (UI + Supabase auth + DB reads/writes + calls to backend)                 │
└───────┬───────────────────────────────────────────────┬───────────────────┘
        │                                                 │
        │ auth + DB (with the user's JWT → RLS)           │ POST /analyze, /judge
        ▼                                                 ▼
┌─────────────────────────────────────┐      ┌────────────────────────────────┐
│   SUPABASE  (Postgres + Auth)        │      │   FastAPI  ·  main.py          │
│   DETERMINISTIC                      │      │   (the only place the LLM runs)│
│   • concepts (seed list)            │      │   • /analyze  → first-pass judge│
│   • sessions  (user_id = auth.uid()) │      │   • /judge    → second-pass     │
│   • attempts  (gap_closed ★ metric)  │      │   • explain_concept (reinforce) │
│   • Row-Level Security policies      │      └───────────────┬────────────────┘
└─────────────────────────────────────┘                      │ HTTPS
        ▲  RLS: a row is visible only                         ▼
        │  if user_id = auth.uid()              ┌────────────────────────────────┐
        │                                       │  GROQ  ·  Llama 3.3            │
        └───────────────────────────────────── │  PROBABILISTIC (the judge)     │
                                                │  RULES + ANALYZE_SYS/JUDGE_SYS │
                                                └────────────────────────────────┘
   ★ gap_closed = the load-bearing link: named gap → second-pass result
```

## One full round (sequence)

```
USER                 index.html              main.py (FastAPI)        Groq/Llama        Supabase
 │                       │                         │                       │                │
 │  open app             │                         │                       │                │
 │──────────────────────►│  GET /  ───────────────►│                       │                │
 │                       │◄────────── index.html ──│                       │                │
 │                       │                         │                       │                │
 │  sign up / log in     │                         │                       │                │
 │──────────────────────►│  auth.signUp ──────────────────────────────────────────────────►│
 │                       │◄──────────────────────── JWT (identity) ───────────────────────  │
 │                       │  loadConcepts() ───────────────────────────────────────────────►│
 │                       │◄──────────────────────── concepts list ────────────────────────  │
 │                       │                         │                       │                │
 │  pick concept +       │                         │                       │                │
 │  type explanation_1   │                         │                       │                │
 │──────────────────────►│  insert sessions row ──────────────────────────────────────────►│ (RLS: user_id set)
 │                       │  POST /analyze ────────►│  groq_json(ANALYZE) ─►│                │
 │                       │                         │◄── gap/followup/expl ─│                │
 │                       │◄── first_pass? gap? ────│                       │                │
 │                       │  insert attempts row ──────────────────────────────────────────►│
 │                       │                         │                       │                │
 │   ┌─ first try PASS ──► showVerdict + 📚 explanation                    │                │
 │   └─ gap found ───────► show follow-up question                         │                │
 │                       │                         │                       │                │
 │  answer follow-up     │                         │                       │                │
 │  (explanation_2)      │                         │                       │                │
 │──────────────────────►│  POST /judge ──────────►│  groq_json(JUDGE) ───►│                │
 │                       │                         │◄── gap_closed/proof ──│                │
 │                       │◄── verdict + expl ──────│                       │                │
 │                       │  update attempts row ──────────────────────────────────────────►│ (gap_closed ★)
 │                       │  showVerdict + 📚 explanation                   │                │
 │                       │  loadHistory() ────────────────────────────────────────────────►│
 │                       │◄── only THIS user's rows (RLS) ─────────────────────────────────  │
 │◄── verdict + history ─│                         │                       │                │
```

## The boundary (Move 3)

```
        DETERMINISTIC (rules / data)          │        PROBABILISTIC (the model)
 ───────────────────────────────────────────┼────────────────────────────────────────
  • fixed concept list                        │  • find where the explanation stops
  • session + attempt records                 │    deriving the "why"
  • gap_closed (the link / metric) ★          │  • write ONE follow-up question
  • row-level-security access rules            │  • judge: did they derive the why?
  • stored pass/fail verdict                   │    (causal test, ignore jargon, quote proof)
 ───────────────────────────────────────────┴────────────────────────────────────────
  Enforced by Supabase + main.py logic        │  Enforced by RULES/ANALYZE_SYS/JUDGE_SYS
                                               │  ⭕ the judge of the 2nd derivation lives here
```

## Gradio demo (`gradio-ui` branch) — same logic, one file

```
BROWSER ──► gradio_app.py (Python)
                ├─ Supabase REST: auth + insert/update attempts (user JWT → RLS)
                └─ Groq/Llama: same ANALYZE_SYS / JUDGE_SYS / explain_concept
```
