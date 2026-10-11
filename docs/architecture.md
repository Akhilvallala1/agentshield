# AgentShield: Architecture

> A guardrail layer for agent-to-agent traffic that rewrites itself.
> Built at the Harness Engineering & Model Wrangling #SFTechWeek Hackathon, Oct 11 2026.

Problem statement: **Statement 1, Recursive Harnessing.** AgentShield evolves its own rules, context policies, guardrails, and agent access based on what it observes, and adapts per agent pair and per domain.

Target prizes: overall podium + **Raindrop RSI Prize** (recursive self improvement).

---

## 0. Instructions for Claude Code (read first)

- Also read `docs/event-guide.md` for the hackathon rules. Anything that breaks those rules is out of scope.
- Build in the order of Section 9. Get each milestone working end to end before starting the next.
- Python 3.11+. Keep it simple: plain modules, no frameworks beyond what is listed in Section 8.
- **All data is synthetic** (Faker + hand-written fixtures). Never use real PII.
- **Never store raw PII in MongoDB** outside the `vault` collection. Incidents store redacted excerpts, entity types, and hashes only.
- **Clean room:** this project is written from scratch today. Do not import, copy, or reference code from any other private codebase.
- The primary interface is the **terminal** (Rich). There is a small trace viewer, but it is not the product. No Streamlit.
- All persistence goes to the **hackathon MongoDB Atlas Sandbox cluster** (required for finalist eligibility). Connection string comes from `MONGODB_URI`.
- Every LLM prompt lives in `agentshield/prompts/` as a `.md` file, not inline strings.

---

## 1. The idea in one paragraph

Agents now pass data to each other (A2A). Static PII filters miss anything they were not written for: custom policy numbers, internal claim IDs, employee badge formats, wallet addresses, quasi-identifiers. AgentShield sits between agents. The **inline path is fast and cheap** (compiled rules + NER). An **async LLM auditor** reviews traffic after the fact, finds what slipped through, and a **rule synthesizer** turns each miss into a new, tested, deterministic rule. A human approves it, MongoDB change streams hot-load it into the live gateway, and the eval suite proves recall went up. Expensive LLM judgment gets **distilled into cheap compiled rules**, generation after generation.

---

## 2. System diagram

```
                ┌──────────────────────── INLINE PATH (fast, <50ms) ─────────────────────────┐
                │                                                                            │
 Intake Agent ──┼─▶ AgentShield Gateway ──▶ L1 Active Rules ──▶ L2 NER ──▶ Redact/Tokenize ──┼─▶ Claims Agent
   (caller)     │        ▲     │              (from Atlas)      (Presidio)   (per playbook)   │   (callee)
                │        │     │                                                            │
                │        │     └── response path: same pipeline on the way back ◀───────────┼── response
                └────────┼───────────────────────────────────────────────────────────────────┘
                         │ hot reload via change stream
                         │
 ┌───────────────────────┴──────── LEARNING LOOP (async) ─────────────────────────────────────┐
 │                                                                                            │
 │  traces ──▶ LLM Auditor ──▶ incident (episodic) ──▶ Rule Synthesizer ──▶ Validator ──▶ HITL │
 │               finds residual       + vector search        proposes regex     runs evals    approve
 │               PII in forwarded       similar past         + test cases       FP / recall     │
 │               payloads               incidents                                               │
 │                                                                                 │           │
 │                                     rules (active, versioned) ◀──────────────────┘           │
 │                                     playbooks (procedural) updated                           │
 │                                     taxonomy (domain terms) updated                          │
 │                                     evals (generation N metrics) appended                    │
 └────────────────────────────────────────────────────────────────────────────────────────────┘

                          All state lives in the MongoDB Atlas Sandbox cluster.
```

---

## 3. Components

### 3.1 Demo agents (`demo_agents/`)
Two small agents so there is real A2A traffic to protect. Domain: **insurance claims** (avoids anything that looks like medical advice).

- **Intake Agent**: takes a messy customer message, summarizes it, sends it on to the Claims Agent.
- **Claims Agent**: looks up claim status and replies. It should never need the customer's SSN, full card number, or badge ID.

Both are thin LLM wrappers. They exist to generate traffic, not to be impressive.

### 3.2 Gateway (`agentshield/gateway.py`)
Single entry point: `POST /a2a/forward {from_agent, to_agent, message, session_id}`.

Pipeline per message, both directions:
1. **L1 Active Rules**: regex rules loaded from `rules` where `status: "active"` and scope matches the agent pair or domain. Held in memory, refreshed by change stream.
2. **L2 NER**: Presidio Analyzer (spaCy `en_core_web_sm` for speed) for standard entities (PERSON, EMAIL, PHONE, SSN, CREDIT_CARD, etc.).
3. **Playbook lookup**: `playbooks` for this agent pair says what each entity type becomes: `allow`, `mask`, `tokenize`, `generalize` (e.g. full DOB → year only), or `block`.
4. **Transform**: apply. Tokens look like `<<POLICY_NUM_7f3a>>`. Token mapping goes to `vault` (TTL 1h) so the response path can re-hydrate for the original caller if the playbook allows.
5. **Trace**: write a `traces` doc (detections, rule versions hit, latency, redacted payload hash).

Inline path never calls an LLM. Latency budget: under 50ms excluding the downstream agent.

### 3.3 Auditor (`agentshield/learning/auditor.py`)
Async worker. Pulls recent `traces` (the **forwarded, already-redacted** payload) and asks an LLM: *is there any remaining personal or sensitive identifier here?* Returns structured findings: span, entity type guess, reasoning, confidence.

Each confirmed finding becomes an **incident**. The raw span is never stored; the incident stores a redacted excerpt with the span replaced by a shape placeholder (e.g. `INS-AA-0000-A`), the entity type, and a SHA-256 of the span.

### 3.4 Rule Synthesizer (`agentshield/learning/synthesizer.py`)
Input: the new incident + top-k similar past incidents (Atlas Vector Search) + current taxonomy for the domain.

LLM output (strict JSON):
```json
{
  "entity_type": "INSURANCE_POLICY_NUMBER",
  "pattern": "\\bINS-[A-Z]{2}-\\d{4}-[A-Z]\\b",
  "rationale": "...",
  "positive_examples": ["INS-AZ-4471-K", "INS-TX-0092-B", "..."],
  "negative_examples": ["INSTANT-RESULT", "IN-AZ-4471", "..."],
  "taxonomy_term": {"domain": "insurance", "term": "policy number", "definition": "..."},
  "playbook_suggestion": {"agent_pair": "intake->claims", "action": "tokenize"}
}
```
Generalize from the shape, not the literal value. Prefer anchored, bounded patterns.

### 3.5 Validator (`agentshield/learning/validator.py`)
Hard metric gates before a human ever sees the rule:
1. Regex compiles and has no catastrophic backtracking (timeout test on a 10KB string).
2. Matches 100% of `positive_examples`, 0% of `negative_examples`.
3. Run against `corpus_clean` (500+ synthetic messages with no PII): **false positive rate must be < 1%**.
4. Run the full eval suite with the candidate rule added: **recall must go up, precision must not drop more than 1 point**.

Fail → the synthesizer gets the failure report and retries (max 3). This retry loop is part of the recursion and worth showing.

### 3.6 Human approval (`agentshield/cli/approve.py`)
Rich terminal panel: incident excerpt, proposed pattern, test results, eval delta (recall before → after, FP rate). Keys: `[a]pprove`, `[r]eject`, `[e]dit`. Approval writes `status: "active"`, `approved_by`, increments version, links `source_incident_id`.

If Atlas Agent Engine is available in the sandbox (see 3.9), also push the pattern as an Agent Engine **content guardrail** with action `modify`, so the platform enforces it for every agent, not only traffic through the gateway.

### 3.7 Hot reload (`agentshield/rules_cache.py`)
The gateway opens a **change stream** on `rules`. Any insert/update to an active rule refreshes the in-memory rule set within a second. No restart. This is the visible "the harness just changed itself" moment in the demo.

```python
with db.rules.watch([{"$match": {"operationType": {"$in": ["insert", "update", "replace"]}}}],
                    full_document="updateLookup") as stream:
    for change in stream:
        cache.upsert(change["fullDocument"])
```

### 3.8 Rule retirement (self-improvement in both directions)
A nightly-style job (triggered manually in the demo) checks each active rule's live stats. Rules whose FP rate on live traffic exceeds the threshold get demoted to `status: "shadow"` (log only) and an incident is opened for refinement. The harness prunes itself, not just grows.

### 3.9 Atlas Agent Engine integration (decide in the first 30 minutes)
Check whether the hackathon sandbox exposes Agent Engine (public preview).

**If yes:**
- Run AgentShield as an A2A-enabled agent (`agent.yaml` with an `a2a:` block). Intake calls Shield, Shield calls Claims via `invoke_agent()`.
- Set Claims Agent `a2a.allowed_callers` to **only** the Shield workspace. Direct Intake → Claims calls get a 403. Show this in the demo: bypass is impossible at the platform level.
- Push approved rules as Agent Engine content guardrails.
- A2A calls show up nested in the Agent Engine trace panel for free.

**If no (or flaky):** the FastAPI gateway is the transport and everything else is unchanged. Do not burn more than 45 minutes on Agent Engine setup. The learning loop on the Atlas cluster is the core of the project either way.

---

## 4. Memory model (mapped to the four memory types)

| Memory type | Collection | What it holds | Why it matters |
|---|---|---|---|
| **Episodic** | `incidents` | Each leak the auditor found: what, where, which detector missed it, how it was resolved | The raw experience the harness learns from |
| **Procedural** | `playbooks` | Per agent pair: entity type → action (allow, mask, tokenize, generalize, block) | How the harness behaves for a specific use case |
| **Taxonomic** | `taxonomy` | Domain PII terms and definitions (insurance: policy number, claim ID, adjuster badge) | Shared domain knowledge, makes synthesis smarter over time |
| **Semantic** | `agent_profiles` | Facts about each agent: role, what it legitimately needs, risk tier | Context for playbook decisions |

If Agent Engine memory is available, mirror incidents with `save_episode`, playbooks with `save_procedure`, and taxonomy with `save_taxonomic`. Atlas collections remain the source of truth.

---

## 5. Data model (Atlas Sandbox)

Database: `agentshield`

```js
// rules
{ _id, rule_id: "R-0007", version: 2, entity_type: "INSURANCE_POLICY_NUMBER",
  kind: "regex", pattern: "...", status: "proposed" | "shadow" | "active" | "retired",
  scope: { domain: "insurance", agent_pair: "intake->claims" | "*" },
  source_incident_id: "I-0012", parent_rule_id: null,
  generation: 3, created_by: "synthesizer", approved_by: "akhil",
  stats: { live_hits: 0, live_fp: 0 }, created_at, updated_at }

// incidents  (episodic)
{ _id, incident_id: "I-0012", ts, agent_pair: "intake->claims", direction: "request",
  entity_type_guess: "INSURANCE_POLICY_NUMBER", shape: "INS-AA-0000-A",
  span_sha256: "...", excerpt_redacted: "...customer with policy <<SHAPE:INS-AA-0000-A>> called...",
  missed_by: ["L1", "L2"], auditor_confidence: 0.94,
  resolution: { status: "open" | "rule_proposed" | "rule_active" | "dismissed", rule_id: "R-0007" },
  embedding: [ ... ] }

// playbooks  (procedural)
{ _id, agent_pair: "intake->claims", version: 4,
  actions: { SSN: "block", CREDIT_CARD: "mask", INSURANCE_POLICY_NUMBER: "tokenize",
             PERSON: "tokenize", DATE_OF_BIRTH: "generalize" },
  updated_from_incident: "I-0012" }

// taxonomy  (taxonomic)
{ _id, domain: "insurance", term: "policy number", definition: "...", shape_examples: ["INS-AA-0000-A"], embedding: [ ... ] }

// agent_profiles  (semantic)
{ _id, agent_id: "claims", role: "...", needs: ["claim_id", "policy_status"], risk_tier: "medium" }

// vault  (TTL index on expires_at)
{ _id, token: "<<POLICY_NUM_7f3a>>", session_id, entity_type, value, expires_at }

// traces
{ _id, request_id, session_id, agent_pair, direction, detections: [ {entity_type, layer, rule_id, rule_version} ],
  payload_redacted, latency_ms, audited: false, ts }

// evals
{ _id, generation: 3, ts, rule_set_hash, recall: 0.91, precision: 0.97, fp_rate: 0.004,
  by_entity: { INSURANCE_POLICY_NUMBER: { recall: 1.0 }, ... }, triggered_by_rule: "R-0007" }

// corpus_clean   (negatives for FP testing)   and   eval_set (labeled spans)
```

**Indexes**
- `rules`: `{status: 1, "scope.agent_pair": 1}`
- `traces`: `{audited: 1, ts: -1}`
- `vault`: TTL on `expires_at`
- `incidents` and `taxonomy`: **Atlas Vector Search** index on `embedding` (Voyage embeddings; use Atlas automated embeddings if enabled in the sandbox, otherwise call the Voyage API)

```json
{ "fields": [
  { "type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine" },
  { "type": "filter", "path": "agent_pair" },
  { "type": "filter", "path": "entity_type_guess" }
]}
```
(Match `numDimensions` to the Voyage model you actually use.)

---

## 6. The recursive loop, step by step

```
gen N rule set ──▶ traffic ──▶ auditor finds miss ──▶ incident
      ▲                                                  │
      │                                    vector search similar incidents + taxonomy
      │                                                  │
      │                                           synthesizer proposes rule
      │                                                  │
      │                                  validator: compile, examples, FP < 1%, eval delta
      │                                         │ fail → retry with report (≤3)
      │                                         ▼ pass
      │                                   human approves in terminal
      │                                         │
      └──── change stream hot-reload ◀── rule active, playbook + taxonomy updated, evals gen N+1
```

Hard metric signals used at every step: regex test pass rate, FP rate on clean corpus, recall/precision on eval set, live hit/FP counts, inline latency.

---

## 7. Eval suite

- `eval_set`: ~300 synthetic messages with labeled spans. Include **standard** entities (names, emails, SSNs, cards) and **novel** entities the baseline does not know:
  - insurance policy numbers (`INS-AZ-4471-K`)
  - internal claim IDs (`CLM-2026-000913`)
  - adjuster badge IDs (`ADJ#77-1043`)
  - crypto wallet addresses
  - quasi-identifiers ("the only Tesla Cybertruck owner on Elm St")
- `corpus_clean`: ~500 synthetic messages with no PII but lots of look-alikes (SKUs, ticket numbers, version strings).
- `scripts/run_evals.py --generation N` writes to `evals` and prints a Rich table: per-entity recall, overall precision, FP rate, delta vs previous generation.

Gen 0 should score well on standard entities and badly on novel ones. Each approved rule should visibly move one row.

---

## 8. Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Gateway | FastAPI + Uvicorn |
| Database | MongoDB Atlas **Sandbox** cluster, `pymongo` |
| Vector search | Atlas Vector Search + Voyage AI embeddings |
| Hot reload | MongoDB change streams |
| NER | Microsoft Presidio (analyzer + anonymizer), spaCy `en_core_web_sm` |
| LLM (auditor, synthesizer, demo agents) | Claude via Anthropic SDK, model set in `.env` |
| Agent runtime (optional) | Atlas Agent Engine SDK (LangGraph) if available in sandbox |
| Terminal UI | Rich |
| Synthetic data | Faker + hand-written fixtures |
| Config | `.env` + `pydantic-settings` |

`.env.example`
```
MONGODB_URI=
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
LLM_MODEL=
FP_THRESHOLD=0.01
AGENT_ENGINE_ENABLED=false
```

---

## 9. Build plan (submissions due 5:00 PM)

| Time | Milestone | Done when |
|---|---|---|
| 10:50 – 11:30 | **M0 Setup**: repo, sandbox cluster connected, collections + indexes, synthetic data generators, `eval_set` + `corpus_clean` seeded. Check Agent Engine availability. | `python scripts/seed.py` populates Atlas |
| 11:30 – 12:30 | **M1 Inline gateway**: L1 rules + L2 Presidio + playbooks + vault + traces. Demo agents talking through it. | Intake → Shield → Claims works; traces in Atlas |
| 12:30 – 1:00 | **M2 Evals gen 0**: `run_evals.py` baseline table | Novel entities show low recall |
| 1:00 – 2:00 | **M3 Auditor + incidents**: async auditor, redacted incidents, embeddings, vector search for similar incidents | Planted leak produces an incident |
| 2:00 – 3:00 | **M4 Synthesizer + validator + approval CLI** | Proposed rule passes gates, approved in terminal |
| 3:00 – 3:30 | **M5 Change stream hot reload + eval gen N+1** | Rerun catches the leak with no restart; recall row moves |
| 3:30 – 4:15 | **M6 Stretch**: Agent Engine A2A + allowed_callers + guardrail push, OR rule retirement, OR a minimal trace viewer page | Pick one, only if M0–M5 are solid |
| 4:15 – 4:45 | **Record 1-minute demo video**, README, make repo public | Video uploaded |
| 4:45 – 5:00 | Submit, double-check links and team members | Submitted |

**Cut lines if behind:** drop M6 entirely. Then drop the playbook "generalize" action. Never cut M4/M5, they are the project.

---

## 10. Repo layout

```
agentsheild/               # repo root
  README.md                 # what it is, what was built today, how to run
  CLAUDE.md                 # pointer for Claude Code
  docs/
    architecture.md         # this file
    event-guide.md          # hackathon rules, judging, schedule
  .env.example
  pyproject.toml
  agentshield/
    config.py
    db.py                   # Atlas client, collection handles, index creation
    gateway.py              # FastAPI app, /a2a/forward
    pipeline.py             # L1, L2, playbook, transform
    rules_cache.py          # in-memory rules + change stream watcher
    vault.py
    learning/
      auditor.py
      synthesizer.py
      validator.py
      retirement.py
      embeddings.py         # Voyage
    cli/
      approve.py            # Rich approval panel
      demo.py               # scripted demo runner
    prompts/
      auditor.md
      synthesizer.md
  demo_agents/
    intake.py
    claims.py
  scripts/
    seed.py                 # synthetic data, eval_set, corpus_clean, base playbooks
    run_evals.py
  agent_engine/             # only if 3.9 is a yes
    shield/agent.yaml
    claims/agent.yaml
```

---

## 11. Demo script (3 minutes live, 1 minute video)

1. **0:00 Problem (20s):** Agents pass data to each other. Static filters miss anything they were not written for. Show gen 0 eval table: names and SSNs fine, policy numbers and badge IDs at ~0% recall.
2. **0:20 Leak (30s):** Intake sends a claim containing `INS-AZ-4471-K` and an adjuster badge. It reaches the Claims Agent unredacted.
3. **0:50 Learn (40s):** Auditor flags it. Synthesizer proposes a rule using two similar past incidents. Validator: 10/10 positives, 0/10 negatives, FP 0.2% on 500 clean messages, recall +12 points.
4. **1:30 Approve + evolve (30s):** Approve in terminal. Change stream fires, gateway reloads live.
5. **2:00 Proof (30s):** Rerun the same message: tokenized. Run evals: generation 1 row. Show rule lineage in Atlas: rule → incident → eval.
6. **2:30 Close (30s):** (If Agent Engine) direct Intake → Claims call gets a 403, only the Shield can reach it. The harness turns expensive LLM judgment into cheap compiled rules, and keeps doing it.

---

## 12. How this maps to judging

| Criterion | Weight | What earns it |
|---|---|---|
| Technical Demo | 35% | Live loop: leak → incident → rule → approve → hot reload → caught. Real Atlas data on screen. |
| Implementation Difficulty | 30% | Validator with hard metric gates, vector-search-informed synthesis, change-stream hot reload, reversible tokenization vault, generational evals. Not a few prompts away. |
| Impact | 20% | A2A traffic is the next PII leak surface; every multi-agent system needs this. |
| Creativity | 15% | Distilling LLM judgment into compiled, tested rules; the harness grows and prunes its own guardrails. |
| Raindrop RSI Prize | bonus | Generation-over-generation eval table is direct evidence of recursive self improvement. |

---

## 13. Rules compliance checklist

- [ ] Built on the hackathon **Atlas Sandbox** cluster (finalist requirement)
- [ ] Repo is **public** before submitting
- [ ] README has a **"Built today"** section; all commits dated Oct 11 2026
- [ ] Demo shows only work built today
- [ ] Synthetic data only, no third-party code or data without rights
- [ ] Not a dashboard product, not Streamlit, not basic RAG
- [ ] 1-minute demo video uploaded, all team members added to submission

## 14. Git setup (personal identity, repo-local)

```bash
cd ~/Desktop/Hackathon/MangoDB/agentsheild
git init
git config user.name "Akhil Vallala"
git config user.email "akhilvallala0115@gmail.com"   # local only, do not use --global
```
Push to the personal GitHub account and make the repo public before submitting.
