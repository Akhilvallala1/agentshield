# AgentShield

A guardrail layer for agent-to-agent (A2A) traffic that rewrites itself.

Static PII filters miss anything they were not written for: policy numbers, claim IDs, badge formats, wallet
addresses. AgentShield sits between agents. The inline path is fast and cheap (compiled regex rules + Presidio
NER, no LLM). An async LLM auditor reviews forwarded traffic, finds what slipped through, and a synthesizer turns
each miss into a new regex rule. A validator gates it on hard metrics (examples, false positives on 500 clean
messages, recall/precision on a labeled eval set), a human approves it in the terminal, and a MongoDB change
stream hot-loads it into the live gateway. Each approval writes a new eval generation, so recursive
self-improvement is measured, not claimed.

Built for Statement 1 (Recursive Harnessing) at the Harness Engineering & Model Wrangling #SFTechWeek Hackathon.

## Built today (Oct 11 2026)

Everything in this repo was written at the event. See `git log` for the per-milestone commits:

- M0 Setup: Atlas collections, indexes, vector search indexes, synthetic data, smoke test
- M1 Inline gateway: L1 rules + Presidio + playbooks + reversible token vault + traces
- M2 Evals gen 0: overlap-scored eval set, clean corpus, generational eval table
- M3 Auditor + incidents: LLM auditor, shape-redacted incidents, Voyage embeddings, vector search
- M4 Synthesizer + validator + approval CLI: retry loop on validator feedback
- M5 Change stream hot reload + eval generation N+1
- M6 Rule retirement: the gateway counts live hits per rule; the auditor judges each hit in context
  (shape only, never the raw value, passed as untrusted data); rules over 20% false positives on 5+ hits
  from 2+ independent sessions are proposed for retirement, and on human approval demoted to shadow,
  removed from the live gateway via change stream, and a refinement incident + eval generation is written.
  The harness prunes itself, not just grows.

## MongoDB Atlas usage

`rules` (versioned, change-stream hot reload), `incidents` (episodic memory, Atlas Vector Search),
`playbooks` (procedural), `taxonomy` (taxonomic, vector indexed), `agent_profiles` (semantic),
`vault` (TTL), `traces`, `evals` (one doc per generation), `eval_set`, `corpus_clean`, `counters`.

## Run it

    uv sync && uv run python -m spacy download en_core_web_sm
    cp .env.example .env   # fill in Atlas + OpenAI + Voyage
    uv run python scripts/smoke_atlas.py
    uv run python scripts/seed.py --reset
    uv run python scripts/run_evals.py
    ./scripts/demo_layout.sh

Demo flow: `demo send` → `demo audit` → `demo propose` → `approve` → `demo send` (now caught)
→ `demo drift` (product codes that look like policy numbers) → `demo retire` (retirement proposed)
→ `approve` (retirement approved, rule pruned live) → `demo lineage`.

All data is synthetic (Faker + fixtures). Raw values exist only in the TTL'd `vault`; incidents store shapes and hashes.
