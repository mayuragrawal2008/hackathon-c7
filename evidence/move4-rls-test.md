# Move 4 — Two-User Row-Level-Security Test (PASSED)

Proof that one learner can never read another learner's rows. Run against the live
Supabase database (project `laeqihuhaokwnguzdepn`).

## Setup
- Created two real auth users: User A and User B (Supabase Auth, email+password).
- Each acts with their own JWT, so Postgres `auth.uid()` differs per user.
- RLS policies (see `schema.sql`): a row in `sessions` / `attempts` is visible only
  when `auth.uid() = user_id`.

## The test
1. **User A** created a session (`concept_id = 1`) and inserted an attempt with
   `explanation_1 = "A secret explanation"` → HTTP **201 Created**.
2. **User A** reads `attempts` →
   `[{"explanation_1":"A secret explanation"}]`  ✅ sees own row.
3. **User B** reads `attempts` (the attempted cross-read) →
   `[]`  ✅ **empty — cannot see User A's data.**

## Result
- Two accounts ✔
- Attempted cross-read ✔
- Empty result for the other user ✔

Row-level security is enforced. Isolation holds.
