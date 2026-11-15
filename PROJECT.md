# Carmine: a standing skeptic for your startup

> An AI agent that continuously attacks a founder's assumptions and pitch with sourced, verified objections. The founder rules on every one.

**Challenge:** AI Agents for Founders Challenge
**Task automated:** the weekly "what could make this fail?" research that founders know they should do and almost never do
**Models:** free tiers and open-weight only (no paid credits at runtime)
**Status:** planning. Names, dates, and numbers marked `TODO` are to be filled in by the team.

---

## 1. Summary

Founders are biased toward their own idea, and the people around them are usually too polite. A real devil's-advocate investigation (failed startups in your space, competitor moves, regulation, unit economics, the hard investor questions) takes days of unpleasant research, so it gets skipped.

Carmine does that work every week. It takes the founder's assumptions, hunts for evidence that they are wrong, verifies every piece of evidence against its source, and puts a ranked queue of objections in front of the founder. The agent never decides what is a real risk. The founder accepts, rebuts, investigates, or dismisses each objection, and every decision is logged.

**Why it is not "just ask a chatbot":** persistence (a living risk register), push instead of pull (runs weekly without being asked), verified sources (every quote is checked against the page), a structured human checkpoint (forced rebuttals, logged reasoning), and measured quality (acceptance rate, citation accuracy, backtests, time saved).

---

## 2. Challenge fit

| Requirement | How Carmine meets it |
|---|---|
| One concrete step of an entrepreneurial project | Risk and assumption stress-testing (ideation through investor preparation) |
| Measurable time saved | Self-reported baseline (Google Form) vs. app-logged time; timed teammate run as a sanity check (section 10) |
| Human firmly in charge | Nothing changes status without a founder verdict; forced written rebuttals on high-severity items; all overrides logged |
| Free models only | Gemini free tier, Groq free tier, local open-weight models, local embeddings (section 8) |
| Rewards critical thinking | The entire product is built around challenging the founder's own beliefs |
| Continuous use, not one-off | Weekly runs, persistent risk register, reopening of dismissed risks on new evidence |
| At least two outside testers, unassisted | Tester protocol in section 11 |
| Log of every model and tool | Built into the system (section 9, `llm_calls` table) |

---

## 3. Users and the task being replaced

**Primary user:** an early-stage founder (student, side-project, pre-seed) with a real idea and real assumptions.

**Manual version of the task:** research reasons the idea might fail, track competitors and platform risks, check regulations, sanity-check numbers, and rehearse investor questions. Roughly 6-10+ hours per week if done properly (to be validated by our baseline data), which is why most founders do it once or never.

**What Carmine produces instead:** a weekly queue of the top objections, each with a verified source, which the founder reviews in about 15-25 minutes.

---

## 4. Scope

### In scope (core)
- Assumption extraction from a pitch or one-pager, with founder confirmation
- Three attack modules: **market and demand**, **competitor and platform risk**, **investor questions**
- Retrieval, objection extraction, and multi-step verification
- Objection queue with the four verdicts, forced rebuttal, and one agent counter-argument
- Persistent risk register and decision log
- Weekly brief
- Authentication (Supabase Auth) with strict per-user data isolation
- Logging and evaluation tooling

### Stretch
- **Failure-pattern module** (post-mortems of similar startups)
- **Regulatory module** (jurisdiction-aware)
- **Unit-economics module** (checks the founder's numbers against public benchmarks)
- **Pitch stress-test report** (investor questions ranked by how weakly the materials answer them)
- **Calibration dashboard** (which dismissed risks later proved valid)
- Backtest against a failed startup's pre-failure materials

### Out of scope
- Making decisions for the founder
- Outreach, emailing, or any action on the outside world
- Scraping personal data about individuals
- Anything requiring paid APIs at runtime

---

## 5. How it works

### Setup (once per startup)
1. **Onboarding.** The founder enters a startup profile (idea, target customer, business model, pricing, market, geography) and optionally pastes a one-pager or deck text.
2. **Assumption extraction.** An LLM extracts 3-10 assumptions as structured items ("SMEs in India will pay 500 INR/month"). **Checkpoint 0:** the founder edits, adds, removes, and confirms them.

### Weekly loop (automated)
3. **Attack planning.** For each assumption and each active module, generate search queries designed to disprove it.
4. **Retrieval.** Run searches (Hacker News Algolia API, Reddit API, RSS, DuckDuckGo), fetch pages, clean text (trafilatura), and cache everything by URL and content hash. Skip anything already seen.
5. **Passage selection.** Chunk the text, embed locally, and keep only the passages most relevant to the assumption.
6. **Objection extraction.** A small, fast model returns JSON: the objection, an exact supporting quote, the source URL, and the targeted assumption.
7. **Verification** (the core of the system):
   - **Exact-quote check:** the quote must appear in the fetched page text (plain string match; catches fabrications cheaply).
   - **Support check:** a different model family (or a local NLI model as a pre-filter) judges whether the quote actually supports the objection.
   - **Recency and relevance check:** the source date and topical match.
   - Failures are dropped or marked low-confidence. Low-confidence items are shown as such, never hidden or inflated.
8. **Dedupe and link.** Cluster near-duplicates with local embeddings, attach each objection to its assumption, and compare against the existing register. New evidence on a previously dismissed risk **reopens** it.
9. **Rank.** Severity times evidence strength, capped at the top N per week to protect the founder's time.
10. **Queue.** Cards appear in the founder's review screen.

### Human checkpoint
11. **Verdicts.** For each card the founder chooses one:
    - **Accept**: a real risk; add to the register and assign a response (pivot, mitigate, test).
    - **Rebut**: not a real risk; a written reason is **required** on high-severity items.
    - **Investigate**: unclear; creates a validation task.
    - **Dismiss**: irrelevant or wrong; feeds back so similar noise is suppressed.
12. **One counter-argument.** After a rebuttal, the agent may respond once with new evidence or a counter-argument. The founder then has the final say and the loop stops.
13. **Register and decision log** update with verdict, reasoning, time spent, and timestamps.

### Outputs
14. **Weekly brief:** what is new, what changed, and the top 3 to act on.
15. **Pitch stress-test** (stretch): hard investor questions ranked by how weakly the founder's materials answer them.
16. **Calibration view** (stretch): of the risks the founder dismissed, how many later turned out valid?

### Logging (throughout)
Every model call, tool call, cache hit, and UI interaction is logged with timestamps (section 9).

---

## 6. Human checkpoints

| # | Checkpoint | What the human decides | What the agent may not do |
|---|---|---|---|
| 0 | Assumption confirmation | Which beliefs are being tested | Run attacks on unconfirmed assumptions |
| 1 | Objection verdicts | Accept / rebut / investigate / dismiss | Change a risk's status itself |
| 2 | Forced rebuttal | Written reasoning on high-severity items | Allow a silent dismissal of a critical risk |
| 3 | Counter-argument limit | Final say after one agent response | Keep arguing past one round |
| 4 | Output review | Which findings go into briefs or exports | Export anything the founder has not approved |

Design principles:
- The agent argues; the founder decides.
- Every objection carries a source. No source, no card.
- High acceptance of cards means the agent is useful. Very low acceptance means it is noise, and we treat that as a bug.
- Every override and rebuttal is logged, which also provides evidence that the human stayed in charge.

---

## 7. Attack modules

Each module is an independent agent with its own queries and sources, so teammates can own one each.

| Module | Looks for | Sources | Priority |
|---|---|---|---|
| Market and demand | Evidence customers will not want or pay for this; free alternatives | Reddit, reviews, forums, HN, app-store complaints | Core |
| Competitor and platform risk | Competitor launches, pricing moves, hiring signals, big platforms absorbing the feature | Competitor sites, changelogs, job boards, news, RSS | Core |
| Investor questions | The hard questions the materials do not answer | Founder materials plus other modules' findings | Core |
| Failure patterns | Why similar startups failed, and whether the same causes apply | Post-mortems, news, HN threads | Stretch |
| Regulatory | Laws and compliance requirements that could break the model | Government sites, public registries | Stretch |
| Unit economics | Unrealistic CAC, pricing, or margin assumptions | Public benchmarks, filings | Stretch |

Honesty rule: when a niche market has thin evidence, the card says "low evidence found" instead of inventing an objection.

---

## 8. Technology

> Free-tier limits and model lineups change often. Confirm real limits in each provider's console on day one. Figures below come from third-party trackers reading provider docs in Sept-Oct 2026.

### Models and providers
| Role | Choice | Notes |
|---|---|---|
| Bulk extraction, query generation | Gemini Flash-Lite class (AI Studio free tier) | Per-model free limits are shown only in the AI Studio console. Free-tier data may be used by Google to improve products outside the EEA, CH, and UK: **tell testers** |
| Verification (different family on purpose) | gpt-oss-120b on Groq free plan | Sample free limits: 30 RPM, 1K RPD, 8K TPM, 200K TPD, **per organization** (shared by teammates). Cached tokens do not count |
| Final ranking and weekly brief | Gemini Flash (full) | Runs rarely |
| Embeddings, dedupe, matching | Hosted pipeline: Gemini embedding model (free tier). Dev and offline eval: local bge-small or MiniLM (sentence-transformers) | The Render free web service (about 512 MB RAM, 0.1 CPU) cannot host a local embedding model comfortably, so embedding runs in the weekly job, not on the web service |
| Optional NLI pre-filter | Small local NLI cross-encoder from Hugging Face | Cheap first pass before an LLM call |
| Dev and offline eval | Ollama (e.g. llama3.1:8b) | Weak at strict JSON; dev use only |
| Fallback | OpenRouter `:free` models | 20 RPM and 50 requests/day unless $10 of credits were ever bought. Treat as emergency only; buying credits conflicts with the rules |

### Application stack
- **Orchestration:** plain Python with Pydantic structured outputs and a database-backed job state machine. No LangChain. LangGraph is optional and not required, because the human checkpoint is asynchronous.
- **LLM access:** one OpenAI-compatible client, swapping `base_url` per provider, with a fallback chain (Gemini, then Groq, then local).
- **Backend:** FastAPI
- **Database:** **Turso** (hosted SQLite / libSQL) in production, plain local `.db` files in development. Same SQL in both.
- **Vector similarity:** cosine similarity in numpy at our scale (hundreds to thousands of objections), so no vector index is needed on the server.
- **Auth:** **Supabase Auth** (Google sign-in and email magic link). The React app signs in with `supabase-js` and sends the access token to FastAPI, which verifies the JWT on every request and uses the user ID as the owner key for all data.
- **Tester access:** testers sign up and log in like any founder. The baseline Google Form asks for the email they sign in with, which joins their form answers to their session logs.
- **Frontend:** React + Vite (decided)
- **Retrieval:** HN Algolia API, Reddit API (check current terms), RSS, DuckDuckGo search, trafilatura
- **Scheduling and heavy work:** GitHub Actions cron (or a teammate's machine) runs the weekly pipeline (fetching, embedding, extraction, verification) and writes to Turso. Render's free tier has no background workers, and the web service is too small for this work.
- **Hosting:** **Render free tier** for the React static site and the FastAPI web service (decided). Fallback if Render cannot cope: Google Cloud Run, with the same Turso database (Cloud Run's local filesystem should not be relied on either; verify before depending on it).

### Deployment architecture

```
Browser (React + Vite, Render static site)
   |  Supabase login -> access token
   v
FastAPI web service (Render free)  --verifies JWT-->  Supabase Auth
   |  reads/writes (filtered by user_id)
   v
Turso (hosted SQLite)  <---- writes ----  Weekly pipeline (GitHub Actions cron)
                                             |-- search + fetch + cache
                                             |-- embeddings (Gemini)
                                             |-- extraction + verification (Gemini, Groq)
```

### Hosting facts that shaped these choices
> Free tiers change. Figures come from third-party trackers and provider docs read in Sept-Nov 2026. Confirm in each dashboard.

- **Render free web service:** ephemeral filesystem (a local SQLite file is lost on every redeploy, restart, or spin-down), no persistent disk, spins down after 15 minutes idle and takes about a minute to wake, about 512 MB RAM and 0.1 CPU (one source says 256 MB; check the dashboard), 750 free instance hours per month. Free Render Postgres expires after 30 days, so we do not use it. The 1 GB instance is a paid plan.
- **Turso free plan:** 5 GB storage, 500M rows read and 10M rows written per month. Hosted SQLite, so data survives Render restarts. Turso has no row-level security, so user isolation is enforced in our own code.
- **Supabase free plan:** 50,000 monthly active users, two free projects, 500 MB database (we use it for auth only). Free projects pause after 7 days of inactivity and need manual reactivation, which would break login. Mitigation: a daily keep-alive request from GitHub Actions (verify it counts as activity) and a manual check before every tester session.
- **Cold start:** warm the Render service a few minutes before each session.

### Rate-limit strategy
- Cache everything by content hash; reprocess only what is new.
- Request queue with exponential backoff and a hard cap on retries (failed calls can still burn quota).
- Short prompts: send only relevant passages, never whole pages. Keep prompt prefixes stable to benefit from caching.
- Teammates use their own keys for development. The shared key is reserved for tester sessions and the demo.
- Run the weekly job ahead of time, never live during a session.
- Log quota usage so we can show the budget in the writeup.

---

## 9. Data model (SQLite sketch)

```
users(id,                                                     -- Supabase user id (JWT `sub`)
      email, role,                                            -- role: founder | team
      created_at)

startups(id, owner_user_id, name, profile_json, created_at)

assumptions(id, startup_id, text, category, status,          -- status: proposed | confirmed | retired
            confirmed_at, created_at)

sources(id, url, domain, fetched_at, published_at, content_hash, text_path)

evidence(id, source_id, quote, quote_verified BOOL,           -- exact-match result
         support_score, support_model, recency_ok BOOL)

objections(id, startup_id, assumption_id NULLABLE,            -- NULL = general risk (not tied to one assumption)
           module, text, severity,                            -- severity: low | medium | high | critical
           confidence, status, first_seen_run, last_seen_run, -- status: new | surfaced | accepted | rebutted |
           created_at)                                        --         investigating | dismissed | reopened

objection_evidence(objection_id, evidence_id)

verdicts(id, objection_id, verdict, reason, response_plan,
         time_spent_ms, decided_at)

counter_arguments(id, verdict_id, text, new_evidence_ids, created_at)

validation_tasks(id, objection_id, description, status, created_at)

runs(id, startup_id, started_at, finished_at, new_sources, new_objections)

llm_calls(id, run_id, provider, model, purpose, tokens_in, tokens_out,
          cache_hit BOOL, latency_ms, error, created_at)      -- the required model/tool log

tool_calls(id, run_id, tool, target, cache_hit BOOL, latency_ms, error, created_at)

sessions(id, user_id, started_at, ended_at, active_ms)

ui_events(id, session_id, event, objection_id, ts_ms)         -- card shown, verdict, rebuttal start/end, idle
```

**Objection shape (agreed):** `text`, `quote`, `source_url`, `assumption` (nullable), `severity`, `confidence`. A null assumption means a general risk (typical for the investor-questions and failure-pattern modules); the queue and register group these under "General". Because an objection may have no assumption, it carries its own `startup_id`, which is what the isolation checks use.

### API endpoints

All endpoints require a valid Supabase JWT and are scoped to the signed-in user's own data, except `/health`. The weekly pipeline writes to Turso directly and has no public endpoints.

| Area | Method and path | Purpose |
|---|---|---|
| Health | `GET /health` | Public; used to warm Render and for the Supabase keep-alive |
| Me | `GET /me` | Current user and role (founder or team) |
| Startups | `POST /startups` | Create a startup from the onboarding profile |
| | `GET /startups` | List my startups |
| | `GET /startups/{id}` | One startup |
| | `PATCH /startups/{id}` | Edit the profile |
| | `DELETE /startups/{id}` | Delete the startup and all its data |
| Assumptions | `POST /startups/{id}/assumptions/extract` | Extract proposed assumptions from pasted text (returns proposals only) |
| | `GET /startups/{id}/assumptions` | List assumptions |
| | `POST /startups/{id}/assumptions` | Add one manually |
| | `PATCH /assumptions/{id}` | Edit, confirm, or retire (checkpoint 0) |
| Runs | `POST /startups/{id}/runs` | Start a run (rate-limited; the weekly job does the same) |
| | `GET /startups/{id}/runs` | Run history |
| | `GET /runs/{id}` | Status and progress |
| Objections | `GET /startups/{id}/objections` | Queue and register; filters: `status`, `module`, `assumption_id` (or `general`), `severity`, pagination |
| | `GET /objections/{id}` | Detail with evidence, sources, and verdict history |
| | `POST /objections/{id}/verdict` | accept, rebut, investigate, or dismiss; rejects a missing reason on high and critical severity; records `time_spent_ms` |
| | `POST /objections/{id}/counter` | Request the agent's single counter-argument (second call is refused) |
| Validation tasks | `GET /startups/{id}/validation-tasks` | List tasks created by "investigate" |
| | `PATCH /validation-tasks/{id}` | Update status |
| Briefs | `POST /startups/{id}/briefs` | Generate a weekly brief on demand |
| | `GET /startups/{id}/briefs` | List briefs |
| | `GET /briefs/{id}` | One brief |
| Export | `GET /startups/{id}/register/export` | Risk register as CSV or Markdown |
| Telemetry | `POST /sessions` | Start a session |
| | `PATCH /sessions/{id}` | End a session |
| | `POST /events` | Batch of UI events (card shown, verdict start and end, idle) |
| Team only | `GET /admin/metrics` | Aggregate evaluation numbers (acceptance rate, time per card, per module) |
| | `GET /admin/export` | Anonymized sessions and verdicts as CSV for the repo |
| Stretch | `POST /startups/{id}/stress-test`, `GET /startups/{id}/calibration` | Pitch stress-test and calibration view |

**Isolation rule:** every query that touches founder data filters by the authenticated user's ID (through `startups.owner_user_id`). Turso has no row-level security, so this is enforced in the API layer and covered by automated tests that try to read another user's startup, assumptions, objections, and verdicts and must fail.

Timing for the time-saved report comes from `sessions`, `ui_events`, and `verdicts.time_spent_ms`, recorded **server-side**, with idle time (tab inactive 60+ seconds) marked.

---

## 10. Evaluation plan

All protocols are written down **before** running any session and are not changed afterward.

### Definition of a "valid risk" (blind-scored)
1. The source exists and the quote actually appears in it.
2. The quote supports the objection (not just topically related).
3. It is relevant to the named assumption.
4. It is specific rather than generic ("customers might not pay" does not count).

Separate tester rating per card: **new to me / useful / obvious / wrong**.

### Metrics
| Metric | How measured |
|---|---|
| Citation accuracy | Hand-check 100+ objections: does the source support the claim? |
| Hallucination / fabricated-source rate | Share of objections failing the exact-quote check before verification vs. after |
| Acceptance rate | Accept + investigate vs. dismiss, overall and per module |
| Novelty | Share of cards rated "new to me" |
| Precision of verification | Plant known-bad objections (fake quotes, mismatched sources) and measure the catch rate |
| Plain-LLM comparison | Same startup through a plain chatbot prompt vs. Carmine, on citation accuracy and acceptance |
| Backtest (stretch) | Feed a failed startup's pre-failure materials and check whether the cause of failure is flagged |
| Reopen accuracy | When a dismissed risk is reopened on new evidence, how often does the founder accept it? |
| Cost of the tool | Minutes of founder time spent on review. If it costs more than it saves, we say so |

### Time-saved report
**Before (baseline), self-reported via Google Form:** how long the last proper risk check took, a breakdown (searching, reading, writing up), best/typical/worst case, and how long ago it was. Founders who have never done one give a hypothetical estimate, which is labeled as such.

**Sanity check:** one or two teammates time a manual version of the task. If testers' estimates and our timed run roughly agree, the estimate is more credible. If they differ, **headline the conservative number**.

**After, measured:** app logs. Total active time = setup + queue review + rebuttals, not just runtime. Agent runtime is reported separately.

**Headline metric:** minutes per valid, verified risk (manual vs. agent plus review), shown alongside quality numbers. Weekly refresh time is reported separately as the recurring saving.

**Reporting rules:** publish every session (not just the average), use medians and ranges, state n, label self-reported vs. logged, and note limitations (small sample, student testers). Publish anonymized raw data in the repo. Every number on the slide must be traceable to a log, recording, or data file. If it cannot be, cut it.

---

## 11. Tester protocol

**Target:** at least 4-5 outside testers (the rules require at least two, and some will drop out). Testers must not be teammates.

**Who counts:** student founders with real projects, people from other teams in the challenge, E-cell and startup-club members. Role-players using a documented case study are acceptable only if **labeled as such** and reported separately from real-idea testers.

**Session (~25 minutes, plus a ~5 minute follow-up a week later)**
1. **Before (async, ~5 min):** consent plus Google Form baseline plus their 3-5 core assumptions. We run the agent beforehand, so the queue is ready.
2. **Intro (2 min):** one-page instructions, then we stay quiet.
3. **Queue review (12-15 min):** top 8-10 cards by severity, with verdicts. Time per card is logged.
4. **One rebuttal flow (3 min):** forced rebuttal and counter-argument on one high-severity card.
5. **Survey (3-5 min):** rate each card (new / useful / obvious / wrong), a few questions, one quote.
6. **Follow-up (a week later, ~5 min):** open the weekly brief and review only what is new. This is our continuous-use evidence.

**Rules**
- Testers use it unassisted, including signing up. Screen-record with consent and note where they get stuck.
- Before each session: warm the Render service and confirm the Supabase project is not paused.
- Do not ask baseline questions after they have used the tool (anchoring).
- Do not state our hypothesis in forms.
- Counterbalance order where we also run a scaled-down manual task (half do manual first, half do agent first), and report both.
- Tell testers how their data is handled, let them anonymize, and get consent for recording and quoting.
- Keep a roster (name or role, type of founder, idea stage, session date).

### Google Form (baseline) fields
1. Consent: recording and anonymous quoting, plus the email you will sign in to Carmine with (used to match your answers to your session logs)
2. Who you are: real startup / side project / idea stage, and how long
3. Have you ever done a proper check of what could make your idea fail? (never / once / regularly)
4. If yes: minutes the last one took, and how long ago
5. Breakdown: minutes searching, reading, writing up
6. Best / typical / worst-case time to do it properly
7. How often would you do it if it were easy?
8. Your 3-5 core assumptions (or upload a one-pager)

---

## 12. Privacy, ethics, and limits

- **Access control:** every founder sees only their own data. Authentication via Supabase, per-user filtering in the API, and automated cross-user access tests (section 9).
- **Tester data:** their startup ideas are sensitive. Store minimally, anonymize in published data, allow deletion on request, and disclose that Gemini free-tier inputs may be used by Google outside the EEA, CH, and UK.
- **Retrieval:** use public pages and APIs, respect robots.txt and site terms, and avoid personal data about individuals. No bulk contacting.
- **No fabricated evidence:** unverified claims are flagged or dropped, never presented as fact.
- **No false authority:** Carmine surfaces risks. It does not predict success or failure and does not give legal or financial advice. State this in the UI.
- **Bias and noise:** the agent can overweight what is easy to find. The UI shows evidence strength and says "low evidence found" where applicable.
- **Honest reporting:** small samples and student testers are stated as limitations.

---

## 13. Team and workstreams

Fill in owners. Each stream should have a clear deliverable.

| Workstream | Deliverable | Owner |
|---|---|---|
| Retrieval and connectors | Cached search and fetch layer (HN, Reddit, RSS, DDG) | TODO |
| Extraction pipeline | Assumption extraction, query planning, objection extraction | TODO |
| Verification | Exact-quote check, support check, NLI pre-filter, planted-error tests | TODO |
| Dedupe, ranking, register | Embeddings, clustering, reopen logic, risk register | TODO |
| Attack modules | Market, competitor/platform, investor questions (then stretch modules) | TODO |
| Backend and scheduling | FastAPI, SQLite schema, job state machine, weekly cron | TODO |
| Frontend | Onboarding, objection queue, forced-rebuttal flow, register, brief | TODO |
| Evaluation | Gold set labeling, blind scoring, plain-LLM comparison, backtest | TODO |
| Tester study and demo | Recruiting, forms, session logistics, recordings, 3-minute demo | TODO |

---

## 14. Milestones

Map these to the real deadline (`TODO: submission date`).

| Phase | Goal | Done when |
|---|---|---|
| 0. Foundations | Repo, schema on Turso, LLM client with fallbacks and logging, free-tier limits confirmed, Render deploy skeleton (React + FastAPI), Supabase login working end to end | A call to each provider is logged to `llm_calls`, and a logged-in user can load an empty queue from the hosted app |
| 1. Vertical slice | One module end to end (retrieve, extract, verify) on 3 assumptions, no UI | Verified objections with real sources land in the DB |
| 2. Human loop | Card queue UI, four verdicts, forced rebuttal, one counter-argument | A founder can complete a full review |
| 3. Continuity | Risk register, weekly GitHub Actions pipeline, reopen logic, weekly brief, Supabase keep-alive | A second run shows only what changed |
| 4. Breadth | Remaining core modules (then stretch) | Three core modules live |
| 5. Evidence | Gold set done, plain-LLM comparison, tester sessions, time-saved report | Numbers and recordings in hand |
| 6. Submission | 3-minute demo, templates, repo cleanup, anonymized data | Submitted on Devpost |

**Start immediately and in parallel:** recruiting testers, writing the protocol and forms, and labeling the gold set. These are the long-lead items.

---

## 15. Demo plan (3 minutes)

1. A founder's idea goes in; assumptions are extracted and confirmed.
2. The objection queue appears with sourced cards, and one is shown being caught by verification (a fabricated quote dropped).
3. The founder accepts one, rebuts another (the agent counters once), and sends a third to investigate.
4. The risk register updates, and the weekly brief shows what changed, including a reopened dismissed risk.
5. Side by side: the same startup through a plain chatbot (unverifiable or invented sources, no memory) vs. Carmine.
6. The numbers: time per valid risk (manual vs. agent), citation accuracy, acceptance rate, tester count, and limitations.

---

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Noisy or generic objections | Source required, verification pass, specificity rubric, acceptance rate tracked as a quality metric |
| Weak sources for niche markets | "Low evidence found" cards instead of invented objections |
| Looks like a chatbot wrapper | Lead with the register, verification, scheduling, checkpoint, and measured results |
| Free-tier rate limits during demo or sessions | Pre-run jobs, caching, fallback chain, per-teammate dev keys |
| Shared Groq org quota exhausted | Reserve Groq for verification only; monitor usage |
| Hard to find real founders | Start recruiting now; label role-players honestly and report separately |
| Weak time-saved baseline | Self-report plus timed teammate run plus conservative headline number |
| Scope creep across six modules | Ship three modules deeply; the rest are stretch |
| Scraping brittleness | Prefer APIs and feeds; fail gracefully; cache aggressively |
| Render free tier restarts, spins down, or loses local files | No local state: all data in Turso; heavy work in the weekly job; warm the service before sessions; Cloud Run as fallback |
| Supabase project pauses after 7 days idle (breaks login) | Daily keep-alive from GitHub Actions; manual check before sessions |
| One user seeing another's data (no row-level security in Turso) | Per-user filtering in the API plus automated cross-user access tests |
| Turso or Supabase free limits change | Check limits on day one; keep SQL portable; data volume is small |
| Privacy complaints from testers | Minimal data, consent, anonymization, disclosure of provider data use |

---

## 17. Submission checklist

- [ ] Working hosted link
- [ ] 3-minute demo video
- [ ] Time-saved report (before and after, measured or estimated, with method stated)
- [ ] Log of every model and tool used
- [ ] At least two outside testers who used it unassisted (roster, recordings with consent, survey results)
- [ ] Evaluation results including failures and limitations
- [ ] Anonymized raw data and protocol in the repo
- [ ] Devpost templates completed

---

## 18. Decisions

### Made
- **Frontend:** React + Vite
- **Hosting:** Render free tier (static site plus FastAPI web service); Google Cloud Run as fallback if Render cannot cope
- **Database:** Turso (hosted SQLite), because Render's free filesystem is ephemeral
- **Auth:** Supabase Auth (founders and the team sign in themselves)
- **Heavy work:** weekly pipeline on GitHub Actions cron, not on the web service

### Still open
- Which two stretch modules to attempt first
- Whether to include a scaled-down manual task in sessions (stronger baseline, longer sessions) or rely on self-report plus a teammate timing
- Whether to attempt the backtest against a failed startup, and which case to use

---

## Appendix: glossary (quick)

- **Assumption:** a belief about the business that has not been proven.
- **Red team:** a group (here, an agent) whose job is to attack a plan to find its weaknesses.
- **Risk register:** a living list of known risks with status, reasoning, and evidence.
- **Precision / recall:** of the things flagged, how many were right / of the real ones, how many were caught.
- **Backtest:** running the system on past cases with known outcomes.
- **Gold set:** human-labeled examples used to grade the agent.
- **Hallucination:** an AI stating something false as if it were fact.
- **Entailment / NLI:** judging whether one text actually supports another.
- **Rate limit:** a cap on requests or tokens per minute or day on a free API.
