-- Concept Check — database schema + row-level security (Move 4)
-- Paste into Supabase SQL Editor and Run.

-- ============ CONCEPTS (fixed list, deterministic) ============
create table if not exists concepts (
  id     bigint generated always as identity primary key,
  slug   text unique not null,
  name   text not null,
  prompt text not null
);
alter table concepts enable row level security;

drop policy if exists "concepts readable by authenticated" on concepts;
create policy "concepts readable by authenticated"
  on concepts for select to authenticated using (true);

-- ============ SESSIONS (one per learner attempt at a concept) ============
create table if not exists sessions (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  concept_id bigint not null references concepts(id),
  created_at timestamptz not null default now()
);
alter table sessions enable row level security;

drop policy if exists "own sessions select" on sessions;
create policy "own sessions select"
  on sessions for select to authenticated using (auth.uid() = user_id);

drop policy if exists "own sessions insert" on sessions;
create policy "own sessions insert"
  on sessions for insert to authenticated with check (auth.uid() = user_id);

-- ============ ATTEMPTS (the heart — before/after + the gap->result link) ============
create table if not exists attempts (
  id                uuid primary key default gen_random_uuid(),
  session_id        uuid not null references sessions(id) on delete cascade,
  user_id           uuid not null default auth.uid() references auth.users(id) on delete cascade,
  concept_id        bigint not null references concepts(id),
  explanation_1     text,             -- their first derivation
  first_pass_closed boolean,          -- did they derive the WHY on the first try?
  gap_named         text,             -- where the explanation became a label
  followup          text,             -- the one question that targets the gap
  explanation_2     text,             -- their answer to the follow-up
  gap_closed        boolean,          -- did they derive the WHY after? (LOAD-BEARING LINK)
  proof_sentence    text,             -- the exact sentence proving the verdict
  created_at        timestamptz not null default now()
);
alter table attempts enable row level security;

drop policy if exists "own attempts select" on attempts;
create policy "own attempts select"
  on attempts for select to authenticated using (auth.uid() = user_id);

drop policy if exists "own attempts insert" on attempts;
create policy "own attempts insert"
  on attempts for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists "own attempts update" on attempts;
create policy "own attempts update"
  on attempts for update to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ============ SEED the fixed concept list ============
insert into concepts (slug, name, prompt) values
('why-backend','Why does a backend exist?','Explain from first principles why a backend exists. Why can''t everything just run in the browser?'),
('interface-api','What is an interface / API, really?','Explain what an interface is, and what an API is underneath the word — from first principles.'),
('frontend-backend','Frontend vs backend','What is a frontend, what is a backend, and why do we need both?'),
('storage-database','Why a database, not a file?','From first principles, what ways exist to store data, and why do we need a database rather than just a file?'),
('choose-storage','Choosing a storage option','How do you choose one storage option over another? Which factors decide it?'),
('caching','Why do we cache?','From first principles, why do systems cache data? What does caching trade off, and what breaks without it?'),
('rate-limit','Why do APIs have rate limits?','Why would a service limit how many requests you can make? What breaks if there were no limit?'),
('https-encryption','Why do we use HTTPS / encryption in transit?','Why encrypt data travelling over the internet? What exactly goes wrong if it''s sent in plain text?'),
('load-balancer','Why do we need a load balancer?','From first principles, why put a load balancer in front of servers? What breaks at scale without one?'),
('db-index','Why do databases use indexes?','Why does a database need an index? What is the trade-off, and what happens to queries without one?'),
('async-queue','Why use a queue / async processing?','Why process some work asynchronously through a queue instead of doing it immediately? What breaks if everything is synchronous?'),
('statelessness','Why do we design servers to be stateless?','What does it mean for a server to be stateless, and why is that useful? What breaks if each server holds its own state?'),
('api-versioning','Why do we version APIs?','Why give an API a version? What breaks for existing users if you change an API without versioning?'),
('cdn','Why do we use a CDN?','From first principles, why serve content from a CDN? What problem does distance/geography create that a CDN solves?'),
('password-hashing','Why hash passwords instead of storing them?','Why store a hash of a password rather than the password itself? What exactly is the danger of storing plain passwords?')
on conflict (slug) do nothing;
