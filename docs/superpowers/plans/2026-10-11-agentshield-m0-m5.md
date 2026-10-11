# AgentShield M0–M5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working AgentShield learning loop on the hackathon Atlas cluster: a leak gets through the gateway, the auditor turns it into an incident, the synthesizer proposes a regex rule, the validator gates it, a human approves it in the terminal, the gateway hot-reloads it, and the eval table shows recall going up.

**Architecture:** Plain Python modules. A pure `pipeline.run()` (L1 regex rules + L2 Presidio + playbook transform) is shared by the FastAPI gateway, the evals, and the validator. All state lives in MongoDB Atlas; the gateway keeps active rules in memory and refreshes them from a change stream. LLM calls (OpenAI) only happen off the inline path: auditor, synthesizer, demo agents.

**Tech Stack:** Python 3.12 via `uv`, FastAPI + Uvicorn, pymongo, Presidio Analyzer + spaCy `en_core_web_sm`, OpenAI SDK (Structured Outputs), Voyage embeddings over HTTP (`httpx`), Rich, Faker, pydantic-settings, pytest.

**Spec:** `docs/architecture.md` (Sections 0–14) plus the Section 15 addendum, which wins on conflict. Rules: `docs/event-guide.md`.

## Global Constraints

- Submissions due **5:00 PM PDT, Oct 11 2026**. Commit at least once per task; all commits dated today.
- Python **3.11+** (we pin 3.12). Run everything from the repo root (`agentsheild/`) with `uv run ...` so `.env` is found.
- All persistence goes to the hackathon Atlas cluster (**SFTW org, Cluster0, M10**). Database name `agentshield`.
- **Synthetic data only** (Faker + fixtures). **Never store raw PII in MongoDB outside `vault`.** Incidents store shape-redacted excerpts, entity types, and SHA-256 hashes only.
- Clean room: no code copied from other private codebases.
- Interface is the terminal (Rich). No Streamlit, no dashboard.
- Every LLM prompt lives in `agentshield/prompts/*.md`, never inline.
- Inline path never calls an LLM. Latency budget < 50 ms excluding the downstream agent.
- Secrets only in `.env` (gitignored). Never print or commit them.
- LLM provider is **OpenAI** (`LLM_API_KEY`), all calls via `agentshield/llm.py`. Default model `gpt-5.6-luna`.
- Embeddings: Voyage `voyage-4-large`, **1024** dims, must equal the vector index `numDimensions`.
- Validator gates (3.5 + 15.2): compiles; no catastrophic backtracking (10 KB strings, 1 s timeout); 100% positives, 0% negatives; candidate's own FP rate on `corpus_clean` **< 1%**; recall up and precision drop **≤ 1 point**; max **3** synthesis attempts.
- Git identity is repo-local (`akhilvallala0115@gmail.com`); `gh` active account must be `Akhilvallala1`.
- Cut lines if behind: drop M6, then the `generalize` action. Never cut M4/M5.

## Review Focus

1. **Auditor returns a span that is not in the text** (LLM hallucination): it must be dropped, never turned into an incident. Test in Task 12.
2. **Raw PII leaking into `incidents`** via the excerpt (the flagged span, or a second flagged span in the same message): every flagged span must be shape-replaced. Test in Task 11.
3. **Overlapping detections** (an L1 rule and Presidio both hit the same or overlapping text): transform must not corrupt the message or double-replace. Test in Task 5.
4. **Synthesizer returns a pattern that hangs** (`(a+)+$`) or one that matches everything (`.*`): validator rejects both without hanging the process. Test in Task 13.
5. **Password with special characters** (`@`, `:`, `/`) in `MONGODB_PASSWORD`: the assembled URI must still connect. Test in Task 1.

---

## File Structure

```
agentsheild/
  pyproject.toml                 # deps, package config (Task 1)
  .env / .env.example            # already exist
  agentshield/
    __init__.py
    config.py                    # Settings + URI assembly (Task 1)
    db.py                        # Mongo client, indexes, vector indexes, counters (Task 2)
    embeddings.py                # Voyage over HTTP (Task 2)
    synth_data.py                # Faker generators: eval_set, corpus_clean, fixtures (Task 3)
    types.py                     # Rule, Detection, PipelineResult (Task 5)
    pipeline.py                  # pure detect/transform/run (Task 5)
    ner.py                       # Presidio wrapper with cache (Task 6)
    rules_cache.py               # in-memory active rules + change stream (Task 7)
    vault.py                     # token store + rehydrate (Task 7)
    llm.py                       # OpenAI wrapper, JSON schema outputs, record/replay (Task 8)
    prompts.py                   # load_prompt() (Task 8)
    gateway.py                   # FastAPI /a2a/forward (Task 9)
    scoring.py                   # overlap scoring (Task 10)
    evals.py                     # evaluate() + run_generation() (Task 10)
    learning/
      __init__.py
      incidents.py               # shape_of, redact_excerpt, similar_incidents (Task 11)
      auditor.py                 # audit_trace, audit_pending (Task 12)
      validator.py               # ValidationContext, validate (Task 13)
      synthesizer.py             # synthesize, propose_rule (Task 14)
    cli/
      __init__.py
      approve.py                 # Rich approval panel (Task 15)
      demo.py                    # scripted demo runner (Task 16)
    prompts/
      intake.md claims.md auditor.md synthesizer.md   # (Tasks 8, 12, 14)
  demo_agents/
    __init__.py
    fixtures.py                  # golden leak message (Task 8)
    intake.py claims.py registry.py                    # (Task 8)
    recordings/                  # LLM record/replay files (Task 8)
  scripts/
    smoke_atlas.py               # capability check (Task 2)
    seed.py                      # seeds Atlas (Task 4)
    run_evals.py                 # eval table (Task 10)
    demo_layout.sh               # tmux layout (Task 16)
  tests/
    test_config.py test_synth_data.py test_pipeline.py test_rules_cache.py
    test_scoring.py test_incidents.py test_auditor.py test_validator.py test_synthesizer.py
  README.md                      # (Task 16)
```

Time budget: M0 Tasks 1–4 → 12:30, M1 Tasks 5–9 → 1:30, M2 Task 10 → 1:50, M3 Tasks 11–12 → 2:40, M4 Tasks 13–15 → 3:40, M5 Task 16 → 4:15, then video + submit.

---

## Milestone M0: Setup

### Task 1: Project scaffold and config

**Files:**
- Create: `pyproject.toml`, `agentshield/__init__.py`, `agentshield/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `agentshield.config.Settings` (fields below), `Settings.resolved_mongodb_uri() -> str`, `get_settings() -> Settings` (cached).

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "agentshield"
version = "0.1.0"
description = "Self-evolving guardrail layer for agent-to-agent traffic"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn>=0.30",
  "pymongo>=4.10",
  "presidio-analyzer>=2.2",
  "spacy>=3.7",
  "openai>=1.50",
  "httpx>=0.27",
  "rich>=13.7",
  "faker>=30",
  "pydantic-settings>=2.4",
]

[dependency-groups]
dev = ["pytest>=8", "pip"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["agentshield", "demo_agents"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Install (start this first; spaCy and Presidio are slow)**

```bash
mkdir -p agentshield/learning agentshield/cli agentshield/prompts demo_agents/recordings scripts tests
touch agentshield/__init__.py agentshield/learning/__init__.py agentshield/cli/__init__.py demo_agents/__init__.py tests/__init__.py demo_agents/recordings/.gitkeep
uv python pin 3.12
uv sync
uv run python -m spacy download en_core_web_sm
```
Expected: `uv sync` resolves without errors; spaCy prints `✔ Download and installation successful`.

- [ ] **Step 3: Write the failing test** `tests/test_config.py`

```python
from urllib.parse import unquote

import pytest

from agentshield.config import Settings


def make(**kw):
    return Settings(_env_file=None, **kw)


def test_full_uri_wins():
    s = make(mongodb_uri="mongodb+srv://u:p@h/", mongodb_host="other")
    assert s.resolved_mongodb_uri() == "mongodb+srv://u:p@h/"


def test_assembles_from_parts_and_escapes_password():
    s = make(mongodb_host="cluster0.abc.mongodb.net", mongodb_user="me", mongodb_password="p@ss:w/rd")
    uri = s.resolved_mongodb_uri()
    assert uri.startswith("mongodb+srv://me:")
    assert "@cluster0.abc.mongodb.net/" in uri
    creds = uri.split("//", 1)[1].rsplit("@", 1)[0]
    assert unquote(creds.split(":", 1)[1]) == "p@ss:w/rd"
    assert creds.count("@") == 0


def test_missing_parts_raises_clear_error():
    with pytest.raises(ValueError, match="MONGODB_HOST"):
        make(mongodb_user="me", mongodb_password="x").resolved_mongodb_uri()
```

- [ ] **Step 4: Run it to make sure it fails**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'agentshield.config'`

- [ ] **Step 5: Implement** `agentshield/config.py`

```python
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = ""
    mongodb_host: str = ""
    mongodb_user: str = ""
    mongodb_password: str = ""
    mongodb_db: str = "agentshield"

    llm_api_key: str = ""
    llm_model_reasoning: str = "gpt-5.6-luna"
    llm_model_fast: str = "gpt-5.6-luna"
    llm_record: bool = False
    llm_replay: bool = False

    voyage_api_key: str = ""
    voyage_base_url: str = "https://api.voyageai.com/v1"
    voyage_model: str = "voyage-4-large"
    embedding_dim: int = 1024

    fp_threshold: float = 0.01
    approver: str = "akhil"
    gateway_url: str = "http://127.0.0.1:8765"

    def resolved_mongodb_uri(self) -> str:
        if self.mongodb_uri:
            return self.mongodb_uri
        if not (self.mongodb_host and self.mongodb_user and self.mongodb_password):
            raise ValueError(
                "Set MONGODB_URI, or MONGODB_HOST + MONGODB_USER + MONGODB_PASSWORD in .env"
            )
        user = quote_plus(self.mongodb_user)
        password = quote_plus(self.mongodb_password)
        return (
            f"mongodb+srv://{user}:{password}@{self.mongodb_host}/"
            "?retryWrites=true&w=majority&appName=agentshield"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_config.py -q`
Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .python-version agentshield demo_agents tests
git commit -m "feat: project scaffold and settings with Mongo URI assembly"
```

---

### Task 2: Atlas client, indexes, embeddings, smoke test

**Files:**
- Create: `agentshield/db.py`, `agentshield/embeddings.py`, `scripts/smoke_atlas.py`

**Interfaces:**
- Consumes: `get_settings()`.
- Produces: `get_db() -> pymongo.database.Database`; `next_id(db, name: str, prefix: str) -> str` (e.g. `"R-0007"`); `ensure_indexes(db, dim: int) -> None`; `wait_for_search_index(coll, name: str, timeout: float = 180) -> bool`; `INCIDENTS_VEC = "incidents_vec"`, `TAXONOMY_VEC = "taxonomy_vec"`; `embed(texts: list[str], input_type: str = "document") -> list[list[float]]`.

Needs a live cluster, so this task is verified by the smoke script, not unit tests.

- [ ] **Step 1: Implement** `agentshield/db.py`

```python
import time
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

from agentshield.config import get_settings

INCIDENTS_VEC = "incidents_vec"
TAXONOMY_VEC = "taxonomy_vec"


@lru_cache
def get_db() -> Database:
    s = get_settings()
    client = MongoClient(s.resolved_mongodb_uri(), serverSelectionTimeoutMS=10_000, appname="agentshield")
    return client[s.mongodb_db]


def next_id(db: Database, name: str, prefix: str) -> str:
    doc = db.counters.find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return f"{prefix}-{doc['seq']:04d}"


def ensure_indexes(db: Database, dim: int) -> None:
    db.rules.create_index([("status", ASCENDING), ("scope.agent_pair", ASCENDING)])
    db.rules.create_index("rule_id", unique=True)
    db.traces.create_index([("audited", ASCENDING), ("ts", DESCENDING)])
    db.vault.create_index("expires_at", expireAfterSeconds=0)
    db.vault.create_index([("token", ASCENDING), ("session_id", ASCENDING)])
    db.incidents.create_index("incident_id", unique=True)
    db.incidents.create_index("span_sha256")
    db.evals.create_index("generation")
    db.playbooks.create_index("agent_pair", unique=True)
    db.taxonomy.create_index([("domain", ASCENDING), ("term", ASCENDING)], unique=True)
    _ensure_vector_index(db.incidents, INCIDENTS_VEC, dim, ["agent_pair", "entity_type_guess"])
    _ensure_vector_index(db.taxonomy, TAXONOMY_VEC, dim, ["domain"])


def _ensure_vector_index(coll: Collection, name: str, dim: int, filters: list[str]) -> None:
    if coll.name not in coll.database.list_collection_names():
        coll.database.create_collection(coll.name)
    if any(ix["name"] == name for ix in coll.list_search_indexes()):
        return
    fields = [{"type": "vector", "path": "embedding", "numDimensions": dim, "similarity": "cosine"}]
    fields += [{"type": "filter", "path": f} for f in filters]
    coll.create_search_index(SearchIndexModel(definition={"fields": fields}, name=name, type="vectorSearch"))


def wait_for_search_index(coll: Collection, name: str, timeout: float = 180) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for ix in coll.list_search_indexes(name):
            if ix.get("queryable"):
                return True
        time.sleep(3)
    return False
```

- [ ] **Step 2: Implement** `agentshield/embeddings.py`

```python
import httpx

from agentshield.config import get_settings


def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    s = get_settings()
    resp = httpx.post(
        f"{s.voyage_base_url.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {s.voyage_api_key}"},
        json={"input": texts, "model": s.voyage_model, "input_type": input_type},
        timeout=30,
    )
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]
```

- [ ] **Step 3: Implement** `scripts/smoke_atlas.py`

```python
"""Checks every Atlas and API capability AgentShield depends on (addendum 15.11)."""
import threading
import time

import httpx
from rich.console import Console

from agentshield.config import get_settings
from agentshield.db import get_db, wait_for_search_index
from pymongo.operations import SearchIndexModel

console = Console()


def check(name, fn):
    try:
        detail = fn()
        console.print(f"[green]PASS[/] {name}" + (f"  [dim]{detail}[/]" if detail else ""))
        return True
    except Exception as e:  # noqa: BLE001 - smoke test reports everything
        console.print(f"[red]FAIL[/] {name}: {type(e).__name__}: {e}")
        return False


def main():
    s = get_settings()
    db = get_db()
    db.drop_collection("_smoke")
    scratch = db["_smoke"]

    check("connect + ping", lambda: db.command("ping"))
    check("insert + read", lambda: scratch.insert_one({"x": 1}).inserted_id and scratch.find_one({"x": 1})["x"])

    def change_stream():
        seen = []
        with scratch.watch(max_await_time_ms=2000) as stream:
            t = threading.Timer(1.0, lambda: scratch.insert_one({"y": 2}))
            t.start()
            for change in stream:
                seen.append(change["operationType"])
                break
        return f"saw {seen}"

    check("change stream", change_stream)
    check("TTL index", lambda: scratch.create_index("expires_at", expireAfterSeconds=0))

    def vector_search():
        dim = 4
        scratch.create_search_index(SearchIndexModel(
            definition={"fields": [{"type": "vector", "path": "v", "numDimensions": dim, "similarity": "cosine"}]},
            name="smoke_vec", type="vectorSearch"))
        scratch.insert_one({"v": [0.1, 0.2, 0.3, 0.4]})
        t0 = time.monotonic()
        if not wait_for_search_index(scratch, "smoke_vec", timeout=180):
            raise TimeoutError("index never became queryable")
        res = list(scratch.aggregate([{"$vectorSearch": {"index": "smoke_vec", "path": "v",
                    "queryVector": [0.1, 0.2, 0.3, 0.4], "numCandidates": 10, "limit": 1}}]))
        return f"{len(res)} hit(s), index ready in {time.monotonic() - t0:.0f}s"

    check("vector search index", vector_search)

    def voyage():
        for base in [s.voyage_base_url, "https://api.voyageai.com/v1", "https://ai.mongodb.com/v1"]:
            r = httpx.post(f"{base.rstrip('/')}/embeddings",
                           headers={"Authorization": f"Bearer {s.voyage_api_key}"},
                           json={"input": ["hello"], "model": s.voyage_model, "input_type": "document"}, timeout=30)
            if r.status_code == 200:
                n = len(r.json()["data"][0]["embedding"])
                if n != s.embedding_dim:
                    raise ValueError(f"dim {n} != EMBEDDING_DIM {s.embedding_dim}")
                return f"works at {base} (dim {n}); set VOYAGE_BASE_URL={base} in .env if different"
        raise RuntimeError(f"Voyage key rejected at all endpoints (last status {r.status_code})")

    check("voyage embeddings", voyage)

    def openai_call():
        from openai import OpenAI
        r = OpenAI(api_key=s.llm_api_key).chat.completions.create(
            model=s.llm_model_reasoning, messages=[{"role": "user", "content": "Reply with: ok"}])
        return r.choices[0].message.content.strip()[:20]

    check("openai chat", openai_call)
    db.drop_collection("_smoke")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it**

Run: `uv run python scripts/smoke_atlas.py`
Expected: seven `PASS` lines. The vector index line can take up to 3 minutes.
If `change stream` fails: hot reload uses the polling fallback built into Task 7 (no code change). If `vector search index` fails: `similar_incidents` falls back to an entity-type filter (built into Task 11). If `voyage` reports a different base URL, add `VOYAGE_BASE_URL=<that url>` to `.env`.

- [ ] **Step 5: Commit**

```bash
git add agentshield/db.py agentshield/embeddings.py scripts/smoke_atlas.py
git commit -m "feat: Atlas client, indexes, Voyage embeddings, capability smoke test"
```

---

### Task 3: Synthetic data generators

**Files:**
- Create: `agentshield/synth_data.py`, `tests/test_synth_data.py`

**Interfaces:**
- Produces: `STANDARD: list[str]`, `NOVEL: list[str]`, `ALL_TYPES: list[str]`; `make_eval_set(n: int = 300, seed: int = 42) -> list[dict]` (docs per 15.1: `msg_id`, `text`, `spans[{start,end,entity_type}]`, `kind`); `make_corpus_clean(n: int = 500, seed: int = 7) -> list[dict]` (`msg_id`, `text`, `lookalike_of`); `HISTORICAL_INCIDENTS: list[dict]`; `DEFAULT_PLAYBOOKS`, `AGENT_PROFILES`, `SEED_TAXONOMY`.

- [ ] **Step 1: Write the failing test** `tests/test_synth_data.py`

```python
import re

from agentshield.synth_data import NOVEL, make_corpus_clean, make_eval_set

NOVEL_RE = {
    "INSURANCE_POLICY_NUMBER": r"^INS-[A-Z]{2}-\d{4}-[A-Z]$",
    "CLAIM_ID": r"^CLM-\d{4}-\d{6}$",
    "ADJUSTER_BADGE": r"^ADJ#\d{2}-\d{4}$",
    "CRYPTO_WALLET": r"^0x[0-9a-f]{40}$",
}


def test_eval_set_spans_point_at_values():
    data = make_eval_set(120)
    assert len(data) == 120
    for ex in data:
        assert ex["spans"], ex
        for sp in ex["spans"]:
            value = ex["text"][sp["start"]:sp["end"]]
            assert value and value == value.strip()
            if sp["entity_type"] in NOVEL_RE:
                assert re.match(NOVEL_RE[sp["entity_type"]], value), (sp, value)


def test_eval_set_is_deterministic_and_covers_novel_types():
    a, b = make_eval_set(80), make_eval_set(80)
    assert a == b
    types = {sp["entity_type"] for ex in a for sp in ex["spans"]}
    assert set(NOVEL) <= types
    assert {ex["kind"] for ex in a} <= {"standard", "novel", "mixed"}


def test_corpus_clean_has_no_real_identifiers():
    corpus = make_corpus_clean(300)
    assert len(corpus) == 300
    for c in corpus:
        for pattern in NOVEL_RE.values():
            assert not re.search(pattern.strip("^$"), c["text"]), c["text"]
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_synth_data.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement** `agentshield/synth_data.py`

```python
"""Synthetic data only. Nothing here is a real person or account."""
import random
import re

from faker import Faker

STANDARD = ["PERSON", "EMAIL", "PHONE", "SSN", "CREDIT_CARD"]
NOVEL = ["INSURANCE_POLICY_NUMBER", "CLAIM_ID", "ADJUSTER_BADGE", "CRYPTO_WALLET"]
ALL_TYPES = STANDARD + NOVEL + ["QUASI_IDENTIFIER"]

STATES = ["AZ", "TX", "CA", "NY", "FL", "WA", "OR", "NV", "CO", "IL"]
QUASI_PHRASES = [
    "the only Tesla Cybertruck owner on Elm St",
    "the retired fire chief who lives above the bakery on 3rd Ave",
    "the twin sisters who run the only bike shop in Mill Valley",
    "the guy with the bright orange 1972 Bronco on Pine Ridge Rd",
]

TEMPLATES = [
    "Customer {PERSON} reports hail damage under policy {INSURANCE_POLICY_NUMBER}. Call back at {PHONE}.",
    "Please check claim {CLAIM_ID} for {PERSON}; adjuster {ADJUSTER_BADGE} visited on Tuesday.",
    "Policyholder email is {EMAIL}, policy {INSURANCE_POLICY_NUMBER}, claim {CLAIM_ID}.",
    "{PERSON} wants the refund sent to wallet {CRYPTO_WALLET} instead of a check.",
    "Verify identity: SSN {SSN}, card on file {CREDIT_CARD}.",
    "Adjuster {ADJUSTER_BADGE} needs the photos for claim {CLAIM_ID} by Friday.",
    "Caller {PERSON} ({EMAIL}) asked about deductible on {INSURANCE_POLICY_NUMBER}.",
    "Reach {PERSON} at {PHONE} or {EMAIL} about the windshield claim.",
    "Payment card {CREDIT_CARD} declined for {PERSON}, please retry.",
    "The claimant is {QUASI_IDENTIFIER}, claim {CLAIM_ID}.",
    "Status update for {CLAIM_ID}: adjuster {ADJUSTER_BADGE} approved the estimate.",
    "Send the payout to {CRYPTO_WALLET}, reference policy {INSURANCE_POLICY_NUMBER}.",
    "{PERSON} gave SSN {SSN} over the phone, policy {INSURANCE_POLICY_NUMBER}.",
    "New FNOL from {PERSON}, phone {PHONE}, vehicle is a 2019 Civic.",
]

CLEAN_TEMPLATES = [
    ("Restock SKU-{ST}-{D4} before the weekend sale.", "INSURANCE_POLICY_NUMBER"),
    ("Form IN-{ST}-{D4} is the state filing template.", "INSURANCE_POLICY_NUMBER"),
    ("Draft INS-{ST}-{D4} of the handbook is ready for review.", "INSURANCE_POLICY_NUMBER"),
    ("The INSTANT-RESULT flag is enabled for build v{V}.", None),
    ("Quarterly report CLM-2026-Q{Q} shows claim volume up {P} percent.", "CLAIM_ID"),
    ("Ticket TKT-{D5} was closed after the deploy.", None),
    ("Use color #{HEX6} for the new claim status badge.", "ADJUSTER_BADGE"),
    ("Room ADJ-{D2} is booked for the adjuster training.", "ADJUSTER_BADGE"),
    ("Order ORD-2026{D4}-{D2} shipped from the Reno warehouse.", "CLAIM_ID"),
    ("Contract hash prefix 0x{HEX8} was logged by the build bot.", "CRYPTO_WALLET"),
    ("Upgrade the claims service to version {V} on Thursday.", None),
    ("Average settlement time dropped to {P} days this quarter.", None),
]

SLOT_RE = re.compile(r"\{([A-Z_0-9]+)\}")


class _Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.f = Faker("en_US")
        self.f.seed_instance(seed)

    def value(self, slot: str) -> str:
        r = self.r
        match slot:
            case "PERSON":
                return f"{self.f.first_name()} {self.f.last_name()}"
            case "EMAIL":
                return self.f.email()
            case "PHONE":
                return f"({r.randint(201, 989)}) 555-{r.randint(0, 9999):04d}"
            case "SSN":
                return f"{r.randint(100, 665)}-{r.randint(10, 99)}-{r.randint(1000, 9999)}"
            case "CREDIT_CARD":
                return self.f.credit_card_number(card_type="visa16")
            case "INSURANCE_POLICY_NUMBER":
                return f"INS-{r.choice(STATES)}-{r.randint(0, 9999):04d}-{r.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}"
            case "CLAIM_ID":
                return f"CLM-{r.choice([2024, 2025, 2026])}-{r.randint(0, 999999):06d}"
            case "ADJUSTER_BADGE":
                return f"ADJ#{r.randint(10, 99)}-{r.randint(1000, 9999)}"
            case "CRYPTO_WALLET":
                return "0x" + "".join(r.choice("0123456789abcdef") for _ in range(40))
            case "QUASI_IDENTIFIER":
                return r.choice(QUASI_PHRASES)
            case "ST":
                return r.choice(STATES)
            case "D2":
                return f"{r.randint(10, 99)}"
            case "D4":
                return f"{r.randint(0, 9999):04d}"
            case "D5":
                return f"{r.randint(10000, 99999)}"
            case "Q":
                return str(r.randint(1, 4))
            case "P":
                return str(r.randint(2, 40))
            case "V":
                return f"{r.randint(1, 9)}.{r.randint(0, 20)}.{r.randint(0, 9)}"
            case "HEX6":
                return "".join(r.choice("0123456789ABCDEF") for _ in range(6))
            case "HEX8":
                return "".join(r.choice("0123456789abcdef") for _ in range(8))
        raise KeyError(slot)

    def fill(self, template: str) -> tuple[str, list[dict]]:
        out, spans, pos = [], [], 0
        for m in SLOT_RE.finditer(template):
            out.append(template[pos:m.start()])
            start = sum(len(p) for p in out)
            value = self.value(m.group(1))
            out.append(value)
            if m.group(1) in ALL_TYPES:
                spans.append({"start": start, "end": start + len(value), "entity_type": m.group(1)})
            pos = m.end()
        out.append(template[pos:])
        return "".join(out), spans


def _kind(spans: list[dict]) -> str:
    types = {s["entity_type"] for s in spans}
    if types <= set(STANDARD):
        return "standard"
    if not types & set(STANDARD):
        return "novel"
    return "mixed"


def make_eval_set(n: int = 300, seed: int = 42) -> list[dict]:
    g = _Gen(seed)
    data = []
    for i in range(n):
        text, spans = g.fill(TEMPLATES[i % len(TEMPLATES)])
        data.append({"msg_id": f"E-{i + 1:04d}", "text": text, "spans": spans, "kind": _kind(spans)})
    return data


def make_corpus_clean(n: int = 500, seed: int = 7) -> list[dict]:
    g = _Gen(seed)
    corpus = []
    for i in range(n):
        template, lookalike = CLEAN_TEMPLATES[i % len(CLEAN_TEMPLATES)]
        text, _ = g.fill(template)
        corpus.append({"msg_id": f"C-{i + 1:04d}", "text": text, "lookalike_of": lookalike})
    return corpus


# Past incidents so vector search has history on the first run (addendum 15.4).
HISTORICAL_INCIDENTS = [
    {"agent_pair": "billing->claims", "entity_type_guess": "INSURANCE_POLICY_NUMBER", "shape": "INS-AA-0000-A",
     "excerpt_redacted": "refund for policy <<SHAPE:INS-AA-0000-A>> was approved last week",
     "resolution": {"status": "dismissed", "rule_id": None}},
    {"agent_pair": "intake->claims", "entity_type_guess": "INSURANCE_POLICY_NUMBER", "shape": "INS-AA-0000-A",
     "excerpt_redacted": "customer quoted <<SHAPE:INS-AA-0000-A>> when asking about roadside cover",
     "resolution": {"status": "dismissed", "rule_id": None}},
    {"agent_pair": "intake->claims", "entity_type_guess": "CLAIM_ID", "shape": "CLM-0000-000000",
     "excerpt_redacted": "follow up on <<SHAPE:CLM-0000-000000>> with the body shop",
     "resolution": {"status": "dismissed", "rule_id": None}},
    {"agent_pair": "claims->payments", "entity_type_guess": "CRYPTO_WALLET",
     "shape": "0x" + "0a" * 20, "excerpt_redacted": "pay out to <<SHAPE:0x0a0a...>> per customer request",
     "resolution": {"status": "dismissed", "rule_id": None}},
]

DEFAULT_PLAYBOOKS = [
    {"agent_pair": "intake->claims", "version": 1,
     "actions": {"SSN": "block", "CREDIT_CARD": "mask", "PERSON": "tokenize", "EMAIL": "tokenize", "PHONE": "tokenize"}},
    {"agent_pair": "claims->intake", "version": 1,
     "actions": {"SSN": "block", "CREDIT_CARD": "mask", "PERSON": "tokenize", "EMAIL": "tokenize", "PHONE": "tokenize"}},
]

AGENT_PROFILES = [
    {"agent_id": "intake", "role": "Summarizes messy customer messages and forwards them to Claims.",
     "needs": ["customer_message"], "risk_tier": "high"},
    {"agent_id": "claims", "role": "Looks up claim status and replies.",
     "needs": ["claim_id", "policy_status"], "risk_tier": "medium"},
]

SEED_TAXONOMY = [
    {"domain": "insurance", "term": "claim ID", "definition": "Internal claim reference, e.g. CLM-YYYY-NNNNNN.",
     "shape_examples": ["CLM-0000-000000"]},
    {"domain": "insurance", "term": "adjuster badge", "definition": "Field adjuster badge number, e.g. ADJ#NN-NNNN.",
     "shape_examples": ["ADJ#00-0000"]},
]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_synth_data.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add agentshield/synth_data.py tests/test_synth_data.py
git commit -m "feat: synthetic eval set, clean corpus, and seed fixtures"
```

---

### Task 4: Seed Atlas

**Files:**
- Create: `scripts/seed.py`

**Interfaces:**
- Consumes: `get_db`, `ensure_indexes`, `embed`, everything from `synth_data`.
- Produces: populated collections `eval_set`, `corpus_clean`, `playbooks`, `agent_profiles`, `taxonomy`, `incidents` (historical, `seeded: true`), and vector indexes. Idempotent: `--reset` drops seeded collections first.

- [ ] **Step 1: Implement** `scripts/seed.py`

```python
import argparse
import hashlib
from datetime import datetime, timezone

from rich.console import Console

from agentshield.config import get_settings
from agentshield.db import INCIDENTS_VEC, TAXONOMY_VEC, ensure_indexes, get_db, next_id, wait_for_search_index
from agentshield.embeddings import embed
from agentshield.synth_data import (AGENT_PROFILES, DEFAULT_PLAYBOOKS, HISTORICAL_INCIDENTS, SEED_TAXONOMY,
                                    make_corpus_clean, make_eval_set)

console = Console()
RESET = ["eval_set", "corpus_clean", "playbooks", "agent_profiles", "taxonomy", "incidents",
         "rules", "traces", "vault", "evals", "counters"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop all AgentShield collections first")
    args = ap.parse_args()
    s, db = get_settings(), get_db()
    now = datetime.now(timezone.utc)

    if args.reset:
        for name in RESET:
            db.drop_collection(name)
        console.print("[yellow]dropped existing collections[/]")

    ensure_indexes(db, s.embedding_dim)

    db.eval_set.delete_many({})
    db.eval_set.insert_many(make_eval_set(300))
    db.corpus_clean.delete_many({})
    db.corpus_clean.insert_many(make_corpus_clean(500))

    for pb in DEFAULT_PLAYBOOKS:
        db.playbooks.replace_one({"agent_pair": pb["agent_pair"]}, {**pb, "updated_from_incident": None}, upsert=True)
    for prof in AGENT_PROFILES:
        db.agent_profiles.replace_one({"agent_id": prof["agent_id"]}, prof, upsert=True)

    tax_vecs = embed([f"{t['term']}: {t['definition']}" for t in SEED_TAXONOMY])
    for t, v in zip(SEED_TAXONOMY, tax_vecs):
        db.taxonomy.replace_one({"domain": t["domain"], "term": t["term"]}, {**t, "embedding": v}, upsert=True)

    if db.incidents.count_documents({"seeded": True}) == 0:
        vecs = embed([f"{h['entity_type_guess']}: {h['excerpt_redacted']}" for h in HISTORICAL_INCIDENTS])
        for h, v in zip(HISTORICAL_INCIDENTS, vecs):
            db.incidents.insert_one({
                **h, "incident_id": next_id(db, "incident", "I"), "ts": now, "direction": "request",
                "span_sha256": hashlib.sha256(h["shape"].encode()).hexdigest(), "missed_by": ["L1", "L2"],
                "auditor_confidence": 0.9, "embedding": v, "seeded": True})

    console.print("waiting for vector indexes to be queryable...")
    ok = wait_for_search_index(db.incidents, INCIDENTS_VEC) and wait_for_search_index(db.taxonomy, TAXONOMY_VEC)
    console.print(f"[green]seeded[/]: eval_set={db.eval_set.count_documents({})} "
                  f"corpus_clean={db.corpus_clean.count_documents({})} "
                  f"incidents={db.incidents.count_documents({})} vector_indexes_ready={ok}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `uv run python scripts/seed.py --reset`
Expected: `seeded: eval_set=300 corpus_clean=500 incidents=4 vector_indexes_ready=True`

- [ ] **Step 3: Verify in Atlas** with `mongosh` or Atlas Data Explorer: database `agentshield` has the collections above; `incidents` docs contain no raw identifiers (only `<<SHAPE:...>>`).

- [ ] **Step 4: Commit**

```bash
git add scripts/seed.py
git commit -m "feat: seed script for eval set, clean corpus, playbooks, taxonomy, historical incidents"
```

---

## Milestone M1: Inline gateway

### Task 5: Core types and pure pipeline

**Files:**
- Create: `agentshield/types.py`, `agentshield/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces:
  - `Rule(rule_id: str, version: int, entity_type: str, pattern: str, agent_pair: str = "*")` with `.compiled: re.Pattern` and `Rule.from_doc(doc: dict) -> Rule`
  - `Detection(entity_type: str, start: int, end: int, layer: str, rule_id: str | None = None, rule_version: int | None = None)` with `.to_dict()`
  - `PipelineResult(text: str, detections: list[Detection], tokens: dict[str, tuple[str, str]], blocked: bool, blocked_types: list[str])`
  - `NER = Callable[[str], list[Detection]]`
  - `pipeline.detect(text, rules, ner) -> list[Detection]`
  - `pipeline.transform(text, detections, actions: dict[str, str], salt: str = "") -> PipelineResult`
  - `pipeline.run(text, rules, actions, ner, salt="") -> PipelineResult`
  - `pipeline.DEFAULT_ACTION = "tokenize"`, `pipeline.TOKEN_RE`

- [ ] **Step 1: Write the failing test** `tests/test_pipeline.py`

```python
from agentshield.pipeline import TOKEN_RE, detect, run, transform
from agentshield.types import Detection, Rule

POLICY = Rule("R-0001", 1, "INSURANCE_POLICY_NUMBER", r"\bINS-[A-Z]{2}-\d{4}-[A-Z]\b")


def fake_ner(text):
    i = text.find("Maria Gonzalez")
    return [Detection("PERSON", i, i + 14, "L2")] if i >= 0 else []


def test_l1_and_l2_detect():
    text = "Maria Gonzalez has policy INS-AZ-4471-K."
    dets = detect(text, [POLICY], fake_ner)
    assert [(d.entity_type, d.layer) for d in dets] == [("PERSON", "L2"), ("INSURANCE_POLICY_NUMBER", "L1")]
    assert dets[1].rule_id == "R-0001" and dets[1].rule_version == 1


def test_overlap_prefers_l1_and_keeps_text_intact():
    text = "policy INS-AZ-4471-K ok"
    ner = lambda t: [Detection("PHONE", 11, 20, "L2")]  # overlaps the policy number
    dets = detect(text, [POLICY], ner)
    assert len(dets) == 1 and dets[0].layer == "L1"
    res = transform(text, dets, {"INSURANCE_POLICY_NUMBER": "tokenize"})
    assert res.text.startswith("policy <<INSURANCE_POLICY_NUMBER_") and res.text.endswith(">> ok")


def test_actions():
    text = "card 4111111111111111 for Maria Gonzalez"
    dets = [Detection("CREDIT_CARD", 5, 21, "L2"), Detection("PERSON", 26, 40, "L2")]
    res = transform(text, dets, {"CREDIT_CARD": "mask", "PERSON": "tokenize"}, salt="s1")
    assert "************1111" in res.text
    token = TOKEN_RE.search(res.text).group(0)
    assert res.tokens[token] == ("PERSON", "Maria Gonzalez")
    assert "Maria" not in res.text


def test_allow_and_default_tokenize():
    text = "Maria Gonzalez INS-AZ-4471-K"
    res = run(text, [POLICY], {"PERSON": "allow"}, fake_ner)
    assert res.text.startswith("Maria Gonzalez <<INSURANCE_POLICY_NUMBER_")


def test_block():
    text = "ssn 123-45-6789"
    res = transform(text, [Detection("SSN", 4, 15, "L2")], {"SSN": "block"})
    assert res.blocked and res.blocked_types == ["SSN"]
    assert "123-45-6789" not in res.text


def test_tokens_stable_per_salt():
    a = transform("x Maria Gonzalez", [Detection("PERSON", 2, 16, "L2")], {}, salt="s")
    b = transform("y Maria Gonzalez", [Detection("PERSON", 2, 16, "L2")], {}, salt="s")
    assert list(a.tokens) == list(b.tokens)


def test_no_detections_passthrough():
    assert run("hello there", [POLICY], {}, lambda t: []).text == "hello there"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement** `agentshield/types.py`

```python
import re
from dataclasses import asdict, dataclass, field
from typing import Callable


@dataclass
class Rule:
    rule_id: str
    version: int
    entity_type: str
    pattern: str
    agent_pair: str = "*"
    compiled: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        self.compiled = re.compile(self.pattern)

    @classmethod
    def from_doc(cls, doc: dict) -> "Rule":
        return cls(doc["rule_id"], doc.get("version", 1), doc["entity_type"], doc["pattern"],
                   doc.get("scope", {}).get("agent_pair", "*"))


@dataclass(frozen=True)
class Detection:
    entity_type: str
    start: int
    end: int
    layer: str
    rule_id: str | None = None
    rule_version: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PipelineResult:
    text: str
    detections: list[Detection]
    tokens: dict[str, tuple[str, str]]
    blocked: bool = False
    blocked_types: list[str] = field(default_factory=list)


NER = Callable[[str], list[Detection]]
```

- [ ] **Step 4: Implement** `agentshield/pipeline.py`

```python
"""Inline path. Pure functions, no I/O, no LLM (addendum 15.3)."""
import hashlib
import re

from agentshield.types import NER, Detection, PipelineResult, Rule

DEFAULT_ACTION = "tokenize"
TOKEN_RE = re.compile(r"<<[A-Z_]+_[0-9a-f]{4}>>")
YEAR_RE = re.compile(r"(19|20)\d{2}")


def _l1(text: str, rules: list[Rule]) -> list[Detection]:
    return [Detection(r.entity_type, m.start(), m.end(), "L1", r.rule_id, r.version)
            for r in rules for m in r.compiled.finditer(text) if m.end() > m.start()]


def _resolve_overlaps(dets: list[Detection]) -> list[Detection]:
    ordered = sorted(dets, key=lambda d: (d.layer != "L1", -(d.end - d.start), d.start))
    kept: list[Detection] = []
    for d in ordered:
        if all(d.end <= k.start or d.start >= k.end for k in kept):
            kept.append(d)
    return sorted(kept, key=lambda d: d.start)


def detect(text: str, rules: list[Rule], ner: NER) -> list[Detection]:
    return _resolve_overlaps(_l1(text, rules) + ner(text))


def _token(entity_type: str, value: str, salt: str) -> str:
    return f"<<{entity_type}_{hashlib.sha256((salt + value).encode()).hexdigest()[:4]}>>"


def _replacement(action: str, entity_type: str, value: str, salt: str, tokens: dict) -> str:
    if action == "allow":
        return value
    if action == "mask":
        return "*" * max(len(value) - 4, 0) + value[-4:] if len(value) > 4 else "****"
    if action == "generalize":
        year = YEAR_RE.search(value)
        return year.group(0) if entity_type == "DATE_OF_BIRTH" and year else f"[{entity_type}]"
    token = _token(entity_type, value, salt)
    tokens[token] = (entity_type, value)
    return token


def transform(text: str, detections: list[Detection], actions: dict[str, str], salt: str = "") -> PipelineResult:
    blocked = sorted({d.entity_type for d in detections if actions.get(d.entity_type) == "block"})
    if blocked:
        return PipelineResult(f"[BLOCKED by AgentShield: message contained {', '.join(blocked)}]",
                              detections, {}, True, blocked)
    tokens: dict[str, tuple[str, str]] = {}
    out = text
    for d in sorted(detections, key=lambda d: d.start, reverse=True):
        action = actions.get(d.entity_type, DEFAULT_ACTION)
        out = out[:d.start] + _replacement(action, d.entity_type, text[d.start:d.end], salt, tokens) + out[d.end:]
    return PipelineResult(out, detections, tokens)


def run(text: str, rules: list[Rule], actions: dict[str, str], ner: NER, salt: str = "") -> PipelineResult:
    return transform(text, detect(text, rules, ner), actions, salt)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add agentshield/types.py agentshield/pipeline.py tests/test_pipeline.py
git commit -m "feat: pure inline pipeline with L1 rules, overlap resolution, playbook actions"
```

---

### Task 6: Presidio NER wrapper

**Files:**
- Create: `agentshield/ner.py`
- Test: `tests/test_pipeline.py` (append one slow test)

**Interfaces:**
- Consumes: `Detection`.
- Produces: `PresidioNER(score_threshold: float = 0.4)` callable `(text) -> list[Detection]` with an internal per-text cache; `get_ner() -> PresidioNER` (cached singleton); `PRESIDIO_TO_LABEL`.

- [ ] **Step 1: Append the failing test** to `tests/test_pipeline.py`

```python
def test_presidio_finds_standard_entities():
    from agentshield.ner import get_ner
    text = "Maria Gonzalez can be reached at maria.g@example.com or (415) 555-0134."
    types = {d.entity_type for d in get_ner()(text)}
    assert {"PERSON", "EMAIL", "PHONE"} <= types
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_pipeline.py::test_presidio_finds_standard_entities -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'agentshield.ner'`

- [ ] **Step 3: Implement** `agentshield/ner.py`

```python
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from agentshield.types import Detection

PRESIDIO_TO_LABEL = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "US_SSN": "SSN",
    "CREDIT_CARD": "CREDIT_CARD",
}


class PresidioNER:
    def __init__(self, score_threshold: float = 0.4):
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        })
        self._analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        self._threshold = score_threshold
        self._cache: dict[str, list[Detection]] = {}

    def __call__(self, text: str) -> list[Detection]:
        if text not in self._cache:
            results = self._analyzer.analyze(text=text, language="en", entities=list(PRESIDIO_TO_LABEL),
                                             score_threshold=self._threshold)
            self._cache[text] = [Detection(PRESIDIO_TO_LABEL[r.entity_type], r.start, r.end, "L2") for r in results]
        return self._cache[text]


@lru_cache
def get_ner() -> PresidioNER:
    return PresidioNER()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: `8 passed` (first run takes a few seconds to load spaCy)

- [ ] **Step 5: Commit**

```bash
git add agentshield/ner.py tests/test_pipeline.py
git commit -m "feat: Presidio NER layer with per-text cache"
```

---

### Task 7: Rules cache with hot reload, and the vault

**Files:**
- Create: `agentshield/rules_cache.py`, `agentshield/vault.py`, `tests/test_rules_cache.py`

**Interfaces:**
- Consumes: `Rule`, `TOKEN_RE`, a pymongo `Database`.
- Produces:
  - `RulesCache(db)`: `.load() -> int`, `.upsert_doc(doc: dict) -> None`, `.rules_for(agent_pair: str) -> list[Rule]`, `.all_active() -> list[Rule]`, `.start_watch() -> None`, `.reload_count: int`, `.on_change: Callable[[str], None] | None`
  - `vault.store_tokens(db, session_id: str, tokens: dict[str, tuple[str, str]], ttl_s: int = 3600) -> None`
  - `vault.rehydrate(db, session_id: str, text: str) -> str`

- [ ] **Step 1: Write the failing test** `tests/test_rules_cache.py`

```python
from agentshield.rules_cache import RulesCache


def doc(rule_id, status="active", pair="*", version=1):
    return {"rule_id": rule_id, "version": version, "entity_type": "X", "pattern": r"\bX\d\b",
            "status": status, "scope": {"agent_pair": pair}}


def test_upsert_and_scope():
    c = RulesCache(db=None)
    c.upsert_doc(doc("R-1"))
    c.upsert_doc(doc("R-2", pair="intake->claims"))
    c.upsert_doc(doc("R-3", pair="billing->claims"))
    assert {r.rule_id for r in c.rules_for("intake->claims")} == {"R-1", "R-2"}
    assert len(c.all_active()) == 3


def test_non_active_status_removes_rule_and_counts_reloads():
    c = RulesCache(db=None)
    events = []
    c.on_change = events.append
    c.upsert_doc(doc("R-1"))
    c.upsert_doc(doc("R-1", status="shadow"))
    assert c.all_active() == []
    assert c.reload_count == 2 and len(events) == 2


def test_version_update_replaces_rule():
    c = RulesCache(db=None)
    c.upsert_doc(doc("R-1", version=1))
    c.upsert_doc(doc("R-1", version=2))
    assert [r.version for r in c.all_active()] == [2]
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_rules_cache.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement** `agentshield/rules_cache.py`

```python
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from pymongo.errors import PyMongoError

from agentshield.types import Rule

log = logging.getLogger("agentshield.rules")


class RulesCache:
    def __init__(self, db):
        self._db = db
        self._rules: dict[str, Rule] = {}
        self._lock = threading.Lock()
        self.reload_count = 0
        self.on_change: Callable[[str], None] | None = None

    def load(self) -> int:
        rules = {d["rule_id"]: Rule.from_doc(d) for d in self._db.rules.find({"status": "active"})}
        with self._lock:
            self._rules = rules
        return len(rules)

    def upsert_doc(self, doc: dict) -> None:
        with self._lock:
            if doc.get("status") == "active":
                self._rules[doc["rule_id"]] = Rule.from_doc(doc)
                msg = f"rule {doc['rule_id']} v{doc.get('version')} ACTIVE ({doc['entity_type']}) -> live"
            else:
                self._rules.pop(doc["rule_id"], None)
                msg = f"rule {doc['rule_id']} now {doc.get('status')} -> removed from live set"
            self.reload_count += 1
        log.info(msg)
        if self.on_change:
            self.on_change(msg)

    def rules_for(self, agent_pair: str) -> list[Rule]:
        with self._lock:
            return [r for r in self._rules.values() if r.agent_pair in ("*", agent_pair)]

    def all_active(self) -> list[Rule]:
        with self._lock:
            return list(self._rules.values())

    def start_watch(self) -> None:
        threading.Thread(target=self._watch, name="rules-watch", daemon=True).start()

    def _watch(self) -> None:
        pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "replace"]}}}]
        try:
            with self._db.rules.watch(pipeline, full_document="updateLookup") as stream:
                log.info("change stream open on rules")
                for change in stream:
                    if change.get("fullDocument"):
                        self.upsert_doc(change["fullDocument"])
        except PyMongoError as e:
            log.warning("change stream unavailable (%s); polling rules every 1s", e)
            self._poll()

    def _poll(self) -> None:
        since = datetime.now(timezone.utc)
        while True:
            time.sleep(1)
            for doc in self._db.rules.find({"updated_at": {"$gt": since}}):
                since = max(since, doc["updated_at"].replace(tzinfo=timezone.utc))
                self.upsert_doc(doc)
```

- [ ] **Step 4: Implement** `agentshield/vault.py`

```python
"""The only collection allowed to hold raw values. TTL-expired after 1h."""
from datetime import datetime, timedelta, timezone

from agentshield.pipeline import TOKEN_RE


def store_tokens(db, session_id: str, tokens: dict[str, tuple[str, str]], ttl_s: int = 3600) -> None:
    if not tokens:
        return
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_s)
    for token, (entity_type, value) in tokens.items():
        db.vault.update_one(
            {"token": token, "session_id": session_id},
            {"$set": {"entity_type": entity_type, "value": value, "expires_at": expires}},
            upsert=True,
        )


def rehydrate(db, session_id: str, text: str) -> str:
    found = set(TOKEN_RE.findall(text))
    if not found:
        return text
    mapping = {d["token"]: d["value"] for d in db.vault.find({"session_id": session_id, "token": {"$in": list(found)}})}
    return TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_rules_cache.py -q`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add agentshield/rules_cache.py agentshield/vault.py tests/test_rules_cache.py
git commit -m "feat: in-memory rules cache with change stream hot reload, token vault"
```

---

### Task 8: LLM wrapper, prompts, demo agents

**Files:**
- Create: `agentshield/llm.py`, `agentshield/prompts.py`, `agentshield/prompts/intake.md`, `agentshield/prompts/claims.md`, `demo_agents/fixtures.py`, `demo_agents/intake.py`, `demo_agents/claims.py`, `demo_agents/registry.py`

**Interfaces:**
- Consumes: `get_settings()`.
- Produces:
  - `llm.complete_json(system: str, user: str, schema: dict, schema_name: str, model: str | None = None) -> dict`
  - `llm.complete_text(system: str, user: str, model: str | None = None) -> str`
  - `prompts.load_prompt(name: str) -> str`
  - `demo_agents.intake.summarize(customer_message: str) -> str`
  - `demo_agents.claims.handle(message: str) -> str`
  - `demo_agents.registry.AGENTS: dict[str, Callable[[str], str]]`
  - `demo_agents.fixtures.GOLDEN_MESSAGE: str`, `GOLDEN_SESSION: str`

- [ ] **Step 1: Implement** `agentshield/prompts.py`

```python
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text()
```

- [ ] **Step 2: Implement** `agentshield/llm.py`

```python
"""Single OpenAI entry point (addendum 15.10). Record/replay for demo safety (15.7)."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from openai import BadRequestError, OpenAI

from agentshield.config import get_settings

RECORDINGS = Path(__file__).resolve().parent.parent / "demo_agents" / "recordings"


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().llm_api_key)


def _call(model: str, messages: list[dict], response_format: dict | None) -> str:
    s = get_settings()
    key = hashlib.sha256(json.dumps([model, messages, response_format], sort_keys=True).encode()).hexdigest()[:16]
    path = RECORDINGS / f"{key}.json"
    if s.llm_replay and path.exists():
        return json.loads(path.read_text())["content"]
    kwargs = {"model": model, "messages": messages}
    if response_format:
        kwargs["response_format"] = response_format
    try:
        resp = _client().chat.completions.create(temperature=0, **kwargs)
    except BadRequestError as e:
        if "temperature" not in str(e):
            raise
        resp = _client().chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    if s.llm_record:
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"model": model, "content": content}, indent=2))
    return content


def complete_json(system: str, user: str, schema: dict, schema_name: str, model: str | None = None) -> dict:
    fmt = {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return json.loads(_call(model or get_settings().llm_model_reasoning, messages, fmt))


def complete_text(system: str, user: str, model: str | None = None) -> str:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return _call(model or get_settings().llm_model_fast, messages, None)
```

- [ ] **Step 3: Write prompts**

`agentshield/prompts/intake.md`:
```markdown
You are the Intake Agent for an insurance company. You receive a messy customer message.
Rewrite it as a short, clear note for the Claims Agent (2-3 sentences).
Keep every identifier exactly as written (policy numbers, claim IDs, badge numbers, names, contact details),
because the Claims Agent needs them to look things up. Do not add facts. Do not give advice.
```

`agentshield/prompts/claims.md`:
```markdown
You are the Claims Agent for an insurance company. You receive a note from the Intake Agent.
Reply in 1-2 sentences with a plausible claim status (for example: received, under review, adjuster assigned, approved).
Refer to people and identifiers exactly as they appear in the note, including placeholders like <<PERSON_ab12>>.
Never ask for SSNs, full card numbers, or badge IDs.
```

- [ ] **Step 4: Implement demo agents**

`demo_agents/fixtures.py`:
```python
# Synthetic. The policy number, badge, and claim ID are the "novel" entities gen 0 misses.
GOLDEN_MESSAGE = (
    "Hi, this is Maria Gonzalez. My car was hit in a parking lot. Policy INS-AZ-4471-K. "
    "Adjuster ADJ#77-1043 came by and said claim CLM-2026-000913 is pending. "
    "You can call me at (415) 555-0134."
)
GOLDEN_SESSION = "demo-session-001"
```

`demo_agents/intake.py`:
```python
from agentshield.llm import complete_text
from agentshield.prompts import load_prompt


def summarize(customer_message: str) -> str:
    return complete_text(load_prompt("intake"), customer_message)
```

`demo_agents/claims.py`:
```python
from agentshield.llm import complete_text
from agentshield.prompts import load_prompt


def handle(message: str) -> str:
    return complete_text(load_prompt("claims"), message)
```

`demo_agents/registry.py`:
```python
from typing import Callable

from demo_agents import claims, intake

AGENTS: dict[str, Callable[[str], str]] = {
    "claims": claims.handle,
    "intake": intake.summarize,
}
```

- [ ] **Step 5: Smoke-check the LLM path**

Run: `uv run python -c "from demo_agents.claims import handle; print(handle('Claim CLM-2026-000913 for <<PERSON_ab12>>: status?'))"`
Expected: a 1–2 sentence status reply mentioning `<<PERSON_ab12>>`.

- [ ] **Step 6: Commit**

```bash
git add agentshield/llm.py agentshield/prompts.py agentshield/prompts demo_agents
git commit -m "feat: OpenAI wrapper with structured outputs and record/replay, demo agents"
```

---

### Task 9: Gateway

**Files:**
- Create: `agentshield/gateway.py`

**Interfaces:**
- Consumes: `get_db`, `get_ner`, `RulesCache`, `pipeline.run`, `vault.store_tokens`, `vault.rehydrate`, `AGENTS`.
- Produces: FastAPI `app` with `POST /a2a/forward` (body `{from_agent, to_agent, message, session_id}` → `{request_id, delivered_message, reply, blocked, detections, latency_ms}`) and `GET /health` → `{active_rules, reloads}`. Writes one `traces` doc per direction.

- [ ] **Step 1: Implement** `agentshield/gateway.py`

```python
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rich.logging import RichHandler

from agentshield.db import get_db
from agentshield.ner import get_ner
from agentshield.pipeline import run
from agentshield.rules_cache import RulesCache
from agentshield.vault import rehydrate, store_tokens
from demo_agents.registry import AGENTS

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(show_path=False)])
log = logging.getLogger("agentshield.gateway")
PLAYBOOK_TTL_S = 5


class ForwardRequest(BaseModel):
    from_agent: str
    to_agent: str
    message: str
    session_id: str


class ForwardResponse(BaseModel):
    request_id: str
    delivered_message: str
    reply: str | None
    blocked: bool
    detections: list[dict]
    latency_ms: float


class State:
    cache: RulesCache
    playbooks: dict[str, tuple[float, dict]] = {}


state = State()


def actions_for(agent_pair: str) -> dict[str, str]:
    hit = state.playbooks.get(agent_pair)
    if hit and time.monotonic() - hit[0] < PLAYBOOK_TTL_S:
        return hit[1]
    doc = get_db().playbooks.find_one({"agent_pair": agent_pair}) or {}
    actions = doc.get("actions", {})
    state.playbooks[agent_pair] = (time.monotonic(), actions)
    return actions


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = get_db()
    get_ner()  # load spaCy before the first request
    state.cache = RulesCache(db)
    log.info("loaded %d active rules", state.cache.load())
    state.cache.start_watch()
    yield


app = FastAPI(title="AgentShield", lifespan=lifespan)


def _shield(text: str, agent_pair: str, direction: str, session_id: str, request_id: str):
    t0 = time.perf_counter()
    res = run(text, state.cache.rules_for(agent_pair), actions_for(agent_pair), get_ner(), salt=session_id)
    latency_ms = (time.perf_counter() - t0) * 1000
    db = get_db()
    store_tokens(db, session_id, res.tokens)
    db.traces.insert_one({
        "request_id": request_id, "session_id": session_id, "agent_pair": agent_pair, "direction": direction,
        "detections": [d.to_dict() for d in res.detections], "payload_redacted": res.text,
        "blocked": res.blocked, "latency_ms": round(latency_ms, 2), "audited": False,
        "ts": datetime.now(timezone.utc),
    })
    return res, latency_ms


@app.post("/a2a/forward", response_model=ForwardResponse)
def forward(req: ForwardRequest) -> ForwardResponse:
    if req.to_agent not in AGENTS:
        raise HTTPException(404, f"unknown agent {req.to_agent}")
    request_id = uuid.uuid4().hex[:12]
    out, latency_ms = _shield(req.message, f"{req.from_agent}->{req.to_agent}", "request", req.session_id, request_id)
    reply = None
    if not out.blocked:
        raw_reply = AGENTS[req.to_agent](out.text)
        back, _ = _shield(raw_reply, f"{req.to_agent}->{req.from_agent}", "response", req.session_id, request_id)
        reply = rehydrate(get_db(), req.session_id, back.text)
    log.info("%s %s->%s detections=%d inline=%.1fms", request_id, req.from_agent, req.to_agent,
             len(out.detections), latency_ms)
    return ForwardResponse(request_id=request_id, delivered_message=out.text, reply=reply, blocked=out.blocked,
                           detections=[d.to_dict() for d in out.detections], latency_ms=round(latency_ms, 2))


@app.get("/health")
def health() -> dict:
    return {"active_rules": len(state.cache.all_active()), "reloads": state.cache.reload_count}
```

- [ ] **Step 2: Run it**

Terminal A: `uv run uvicorn agentshield.gateway:app --port 8765`
Expected log: `loaded 0 active rules`, `change stream open on rules`.

- [ ] **Step 3: Send the golden message** (Terminal B)

```bash
uv run python -c "
import httpx; from demo_agents.fixtures import GOLDEN_MESSAGE as m, GOLDEN_SESSION as s
r = httpx.post('http://127.0.0.1:8765/a2a/forward', json={'from_agent':'intake','to_agent':'claims','message':m,'session_id':s}, timeout=60).json()
print(r['delivered_message']); print(r['latency_ms'], 'ms'); print(r['reply'])"
```
Expected: `Maria Gonzalez` and the phone are tokenized; `INS-AZ-4471-K`, `ADJ#77-1043`, `CLM-2026-000913` pass through **unredacted** (that is the gen 0 leak); inline latency well under 50 ms after warm-up. `traces` in Atlas has 2 new docs with `audited: false`.

- [ ] **Step 4: Commit**

```bash
git add agentshield/gateway.py
git commit -m "feat: FastAPI gateway with both-direction shielding, vault, traces"
```

---

## Milestone M2: Evals gen 0

### Task 10: Scoring, evaluation, generational eval table

**Files:**
- Create: `agentshield/scoring.py`, `agentshield/evals.py`, `scripts/run_evals.py`, `tests/test_scoring.py`

**Interfaces:**
- Consumes: `detect`, `Rule`, `get_ner`, `get_db`.
- Produces:
  - `scoring.score(examples: list[dict], clean: list[dict], predict: Callable[[str], list[Detection]]) -> dict` returning `{"recall", "precision", "fp_rate", "tp", "fp", "fn", "by_entity": {type: {"recall", "tp", "fn"}}}`
  - `evals.evaluate(rules: list[Rule], ner, eval_set: list[dict], corpus: list[dict]) -> dict`
  - `evals.load_eval_data(db) -> tuple[list[dict], list[dict]]`
  - `evals.run_generation(db, triggered_by: str | None = None) -> tuple[dict, dict | None]` (new eval doc, previous eval doc)
  - `evals.print_eval_table(console, current: dict, previous: dict | None) -> None`

- [ ] **Step 1: Write the failing test** `tests/test_scoring.py`

```python
from agentshield.scoring import score
from agentshield.types import Detection

EX = [{"text": "Maria has INS-AZ-4471-K", "spans": [
    {"start": 0, "end": 5, "entity_type": "PERSON"},
    {"start": 10, "end": 23, "entity_type": "INSURANCE_POLICY_NUMBER"}]}]
CLEAN = [{"text": "SKU-AZ-4471 restock"}, {"text": "nothing here"}]


def test_overlap_counts_as_hit_and_type_must_match():
    def predict(t):
        if t.startswith("Maria"):
            return [Detection("PERSON", 0, 4, "L2"), Detection("PHONE", 10, 23, "L2")]
        return []
    m = score(EX, CLEAN, predict)
    assert m["tp"] == 1 and m["fn"] == 1 and m["fp"] == 1
    assert m["by_entity"]["PERSON"]["recall"] == 1.0
    assert m["by_entity"]["INSURANCE_POLICY_NUMBER"]["recall"] == 0.0
    assert m["recall"] == 0.5 and m["precision"] == 0.5


def test_clean_corpus_fp_rate():
    def predict(t):
        return [Detection("X", 0, 3, "L1")] if t.startswith("SKU") else []
    m = score([], CLEAN, predict)
    assert m["fp_rate"] == 0.5 and m["fp"] == 1


def test_each_span_counted_once():
    def predict(t):
        return [Detection("PERSON", 0, 5, "L2"), Detection("PERSON", 1, 4, "L2")]
    m = score([{"text": "Maria x", "spans": [{"start": 0, "end": 5, "entity_type": "PERSON"}]}], [], predict)
    assert m["tp"] == 1 and m["fp"] == 1
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_scoring.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement** `agentshield/scoring.py`

```python
"""Overlap + same-type matching (addendum 15.1)."""
from collections import defaultdict
from typing import Callable

from agentshield.types import Detection


def _ratio(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


def score(examples: list[dict], clean: list[dict], predict: Callable[[str], list[Detection]]) -> dict:
    tp = fp = fn = 0
    per = defaultdict(lambda: {"tp": 0, "fn": 0})
    for ex in examples:
        dets = list(predict(ex["text"]))
        used: set[int] = set()
        for sp in ex["spans"]:
            hit = next((i for i, d in enumerate(dets) if i not in used and d.entity_type == sp["entity_type"]
                        and d.start < sp["end"] and d.end > sp["start"]), None)
            if hit is None:
                fn += 1
                per[sp["entity_type"]]["fn"] += 1
            else:
                used.add(hit)
                tp += 1
                per[sp["entity_type"]]["tp"] += 1
        fp += len(dets) - len(used)
    flagged = 0
    for c in clean:
        dets = predict(c["text"])
        fp += len(dets)
        flagged += bool(dets)
    by_entity = {k: {**v, "recall": _ratio(v["tp"], v["tp"] + v["fn"])} for k, v in sorted(per.items())}
    return {"recall": _ratio(tp, tp + fn), "precision": _ratio(tp, tp + fp), "fp_rate": _ratio(flagged, len(clean)),
            "tp": tp, "fp": fp, "fn": fn, "by_entity": by_entity}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_scoring.py -q`
Expected: `3 passed`

- [ ] **Step 5: Implement** `agentshield/evals.py`

```python
import hashlib
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from agentshield.ner import get_ner
from agentshield.pipeline import detect
from agentshield.scoring import score
from agentshield.types import Rule


def evaluate(rules: list[Rule], ner, eval_set: list[dict], corpus: list[dict]) -> dict:
    return score(eval_set, corpus, lambda text: detect(text, rules, ner))


def load_eval_data(db) -> tuple[list[dict], list[dict]]:
    return list(db.eval_set.find({}, {"_id": 0})), list(db.corpus_clean.find({}, {"_id": 0}))


def run_generation(db, triggered_by: str | None = None) -> tuple[dict, dict | None]:
    rules = [Rule.from_doc(d) for d in db.rules.find({"status": "active"})]
    eval_set, corpus = load_eval_data(db)
    metrics = evaluate(rules, get_ner(), eval_set, corpus)
    previous = db.evals.find_one(sort=[("generation", -1)])
    generation = previous["generation"] + 1 if previous else 0
    rule_set_hash = hashlib.sha256("|".join(sorted(f"{r.rule_id}:{r.version}:{r.pattern}" for r in rules))
                                   .encode()).hexdigest()[:12]
    doc = {"generation": generation, "ts": datetime.now(timezone.utc), "rule_set_hash": rule_set_hash,
           "active_rules": [r.rule_id for r in rules], "triggered_by_rule": triggered_by, **metrics}
    db.evals.insert_one(doc)
    return doc, previous


def _delta(cur: float, prev: float | None) -> str:
    if prev is None:
        return ""
    d = round((cur - prev) * 100, 1)
    return f"[green]+{d}[/]" if d > 0 else (f"[red]{d}[/]" if d < 0 else "[dim]0[/]")


def print_eval_table(console: Console, current: dict, previous: dict | None) -> None:
    gen = current["generation"]
    t = Table(title=f"AgentShield evals, generation {gen}" + (f" (vs {gen - 1})" if previous else ""))
    t.add_column("Entity")
    if previous:
        t.add_column(f"Recall g{gen - 1}", justify="right")
    t.add_column(f"Recall g{gen}", justify="right")
    t.add_column("Δ pts", justify="right")
    for ent, m in current["by_entity"].items():
        prev = previous["by_entity"].get(ent, {}).get("recall") if previous else None
        row = [ent] + ([f"{prev:.2f}" if prev is not None else "-"] if previous else [])
        t.add_row(*row, f"{m['recall']:.2f}", _delta(m["recall"], prev))
    console.print(t)
    p = previous or {}
    console.print(
        f"overall recall [bold]{current['recall']:.3f}[/] {_delta(current['recall'], p.get('recall'))}   "
        f"precision [bold]{current['precision']:.3f}[/] {_delta(current['precision'], p.get('precision'))}   "
        f"clean FP rate [bold]{current['fp_rate']:.3%}[/]   rules: {current['active_rules']}")
```

- [ ] **Step 6: Implement** `scripts/run_evals.py`

```python
from rich.console import Console

from agentshield.db import get_db
from agentshield.evals import print_eval_table, run_generation


def main():
    current, previous = run_generation(get_db())
    print_eval_table(Console(), current, previous)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run gen 0**

Run: `uv run python scripts/run_evals.py`
Expected: generation 0 table. PERSON/EMAIL/PHONE/SSN/CREDIT_CARD recall high (≥ 0.8); INSURANCE_POLICY_NUMBER, CLAIM_ID, ADJUSTER_BADGE, CRYPTO_WALLET, QUASI_IDENTIFIER near **0.00**. If a standard entity is unexpectedly low, print a few misses before moving on (`evaluate` + loop over `eval_set`), since the demo's first beat depends on this table.

- [ ] **Step 8: Commit**

```bash
git add agentshield/scoring.py agentshield/evals.py scripts/run_evals.py tests/test_scoring.py
git commit -m "feat: overlap scoring and generational eval table (gen 0 baseline)"
```

---

## Milestone M3: Auditor and incidents

### Task 11: Incident helpers (shape, redaction, similar incidents)

**Files:**
- Create: `agentshield/learning/incidents.py`, `tests/test_incidents.py`

**Interfaces:**
- Consumes: `INCIDENTS_VEC`.
- Produces:
  - `shape_of(value: str) -> str` (`"INS-AZ-4471-K"` → `"INS-AA-0000-A"`)
  - `redact_excerpt(text: str, spans: list[tuple[int, int]], focus: tuple[int, int], window: int = 80) -> str`
  - `span_hash(value: str) -> str` (SHA-256 hex)
  - `similar_incidents(db, embedding: list[float], exclude_id: str, entity_type: str, k: int = 3) -> list[dict]` (no `embedding` field in results; `score` field when from vector search)

- [ ] **Step 1: Write the failing test** `tests/test_incidents.py`

```python
from agentshield.learning.incidents import redact_excerpt, shape_of, span_hash


def test_shape_keeps_short_uppercase_prefix_only():
    assert shape_of("INS-AZ-4471-K") == "INS-AA-0000-A"
    assert shape_of("CLM-2026-000913") == "CLM-0000-000000"
    assert shape_of("ADJ#77-1043") == "ADJ#00-0000"
    assert shape_of("0xab12") == "0xaa00"
    assert shape_of("Maria Gonzalez") == "Aaaaa Aaaaaaaa"
    assert shape_of("123-45-6789") == "000-00-0000"


def test_redact_excerpt_removes_every_flagged_span():
    text = "Hi this is Maria Gonzalez, policy INS-AZ-4471-K, badge ADJ#77-1043, thanks."
    pol = (text.index("INS"), text.index("INS") + 13)
    badge = (text.index("ADJ"), text.index("ADJ") + 11)
    out = redact_excerpt(text, [pol, badge], focus=pol)
    assert "INS-AZ-4471-K" not in out and "ADJ#77-1043" not in out
    assert "<<SHAPE:INS-AA-0000-A>>" in out and "<<SHAPE:ADJ#00-0000>>" in out


def test_redact_excerpt_window():
    text = "x" * 200 + " INS-AZ-4471-K " + "y" * 200
    s = text.index("INS")
    out = redact_excerpt(text, [(s, s + 13)], focus=(s, s + 13), window=20)
    assert len(out) < 80 and out.startswith("…") and out.endswith("…")


def test_span_hash_is_sha256():
    assert len(span_hash("INS-AZ-4471-K")) == 64
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_incidents.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement** `agentshield/learning/incidents.py`

```python
import hashlib
import re

from pymongo.errors import OperationFailure

from agentshield.db import INCIDENTS_VEC

PREFIX_RE = re.compile(r"^(?:[A-Z]{2,4}(?=[^A-Za-z])|0x)")


def shape_of(value: str) -> str:
    m = PREFIX_RE.match(value)
    keep = m.group(0) if m else ""
    rest = value[len(keep):]
    mapped = "".join("A" if c.isupper() else "a" if c.islower() else "0" if c.isdigit() else c for c in rest)
    return keep + mapped


def span_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def redact_excerpt(text: str, spans: list[tuple[int, int]], focus: tuple[int, int], window: int = 80) -> str:
    out, focus_start, focus_end = text, focus[0], focus[1]
    for start, end in sorted(set(spans), reverse=True):
        repl = f"<<SHAPE:{shape_of(text[start:end])}>>"
        out = out[:start] + repl + out[end:]
        shift = len(repl) - (end - start)
        if start < focus[0]:
            focus_start += shift
            focus_end += shift
        elif (start, end) == focus:
            focus_end = focus_start + len(repl)
    lo, hi = max(0, focus_start - window), min(len(out), focus_end + window)
    return ("…" if lo > 0 else "") + out[lo:hi] + ("…" if hi < len(out) else "")


def similar_incidents(db, embedding: list[float], exclude_id: str, entity_type: str, k: int = 3) -> list[dict]:
    try:
        return list(db.incidents.aggregate([
            {"$vectorSearch": {"index": INCIDENTS_VEC, "path": "embedding", "queryVector": embedding,
                               "numCandidates": 50, "limit": k + 1}},
            {"$set": {"score": {"$meta": "vectorSearchScore"}}},
            {"$match": {"incident_id": {"$ne": exclude_id}}},
            {"$unset": ["embedding", "_id"]},
            {"$limit": k},
        ]))
    except OperationFailure:
        # Fallback (15.11): same entity type, newest first.
        return list(db.incidents.find({"entity_type_guess": entity_type, "incident_id": {"$ne": exclude_id}},
                                      {"embedding": 0, "_id": 0}).sort("ts", -1).limit(k))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_incidents.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add agentshield/learning/incidents.py tests/test_incidents.py
git commit -m "feat: incident shape redaction and vector-search similar incidents"
```

---

### Task 12: Auditor

**Files:**
- Create: `agentshield/learning/auditor.py`, `agentshield/prompts/auditor.md`, `tests/test_auditor.py`

**Interfaces:**
- Consumes: `complete_json`, `load_prompt`, `embed`, `next_id`, `shape_of`, `redact_excerpt`, `span_hash`.
- Produces:
  - `AUDIT_SCHEMA: dict`
  - `audit_text(text: str, llm=complete_json) -> list[dict]` → verified findings `{span, start, end, entity_type, reasoning, confidence}`
  - `audit_pending(db, limit: int = 20, min_confidence: float = 0.7, llm=complete_json, embed_fn=embed) -> list[str]` (new incident IDs). CLI: `python -m agentshield.learning.auditor [--watch]`.

- [ ] **Step 1: Write the failing test** `tests/test_auditor.py`

```python
from agentshield.learning.auditor import audit_text

TEXT = "Maria <<PERSON_ab12>> policy INS-AZ-4471-K and badge ADJ#77-1043"


def fake_llm(findings):
    return lambda system, user, schema, schema_name, model=None: {"findings": findings}


def test_keeps_real_spans_with_offsets():
    out = audit_text(TEXT, llm=fake_llm([
        {"span": "INS-AZ-4471-K", "entity_type": "INSURANCE_POLICY_NUMBER", "reasoning": "r", "confidence": 0.95}]))
    assert out[0]["start"] == TEXT.index("INS") and out[0]["end"] == TEXT.index("INS") + 13


def test_drops_hallucinated_spans_and_tokens():
    out = audit_text(TEXT, llm=fake_llm([
        {"span": "INS-ZZ-0000-Q", "entity_type": "INSURANCE_POLICY_NUMBER", "reasoning": "r", "confidence": 0.9},
        {"span": "<<PERSON_ab12>>", "entity_type": "PERSON", "reasoning": "r", "confidence": 0.9},
        {"span": "", "entity_type": "OTHER", "reasoning": "r", "confidence": 0.9}]))
    assert out == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_auditor.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write** `agentshield/prompts/auditor.md`

```markdown
You audit messages that one AI agent already sent to another, after an automatic redaction pass.
Find any remaining personal or sensitive identifier: anything that identifies a specific person, account,
policy, claim, employee, wallet, or a quasi-identifier that narrows down to one person.

Ignore placeholders that look like <<TYPE_abcd>> or masked values like ****1111; those are already protected.
Ignore generic words, product SKUs, version numbers, dates, and amounts.

For each finding, copy the exact span character for character from the message.
Use one of these entity types: INSURANCE_POLICY_NUMBER, CLAIM_ID, ADJUSTER_BADGE, CRYPTO_WALLET,
PERSON, EMAIL, PHONE, SSN, CREDIT_CARD, QUASI_IDENTIFIER. If none fit, use OTHER_<SHORT_NAME>.
Confidence is 0 to 1. Return an empty list if nothing remains.
```

- [ ] **Step 4: Implement** `agentshield/learning/auditor.py`

```python
import argparse
import time
from datetime import datetime, timezone

from rich.console import Console

from agentshield.db import next_id
from agentshield.embeddings import embed
from agentshield.learning.incidents import redact_excerpt, shape_of, span_hash
from agentshield.llm import complete_json
from agentshield.pipeline import TOKEN_RE
from agentshield.prompts import load_prompt

console = Console()

AUDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {"findings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["span", "entity_type", "reasoning", "confidence"],
        "properties": {"span": {"type": "string"}, "entity_type": {"type": "string"},
                       "reasoning": {"type": "string"}, "confidence": {"type": "number"}}}}},
}


def audit_text(text: str, llm=complete_json) -> list[dict]:
    result = llm(load_prompt("auditor"), f"Message:\n{text}", AUDIT_SCHEMA, "audit_findings")
    verified = []
    for f in result.get("findings", []):
        span = f["span"].strip()
        start = text.find(span) if span else -1
        if start < 0 or TOKEN_RE.fullmatch(span):
            continue  # hallucinated or already-protected span: never becomes an incident
        verified.append({**f, "span": span, "start": start, "end": start + len(span)})
    return verified


def audit_pending(db, limit: int = 20, min_confidence: float = 0.7, llm=complete_json, embed_fn=embed) -> list[str]:
    created = []
    for trace in db.traces.find({"audited": False, "blocked": False}).sort("ts", 1).limit(limit):
        text = trace["payload_redacted"]
        findings = [f for f in audit_text(text, llm) if f["confidence"] >= min_confidence]
        spans = [(f["start"], f["end"]) for f in findings]
        for f in findings:
            digest = span_hash(f["span"])
            if db.incidents.find_one({"span_sha256": digest, "resolution.status": {"$in": ["open", "rule_proposed"]}}):
                continue
            excerpt = redact_excerpt(text, spans, focus=(f["start"], f["end"]))
            incident_id = next_id(db, "incident", "I")
            db.incidents.insert_one({
                "incident_id": incident_id, "ts": datetime.now(timezone.utc), "agent_pair": trace["agent_pair"],
                "direction": trace["direction"], "trace_request_id": trace["request_id"],
                "entity_type_guess": f["entity_type"], "shape": shape_of(f["span"]), "span_sha256": digest,
                "excerpt_redacted": excerpt, "missed_by": ["L1", "L2"], "auditor_confidence": f["confidence"],
                "auditor_reasoning": f["reasoning"], "resolution": {"status": "open", "rule_id": None},
                "embedding": embed_fn([f"{f['entity_type']}: {excerpt}"])[0],
            })
            created.append(incident_id)
            console.print(f"[red]incident {incident_id}[/] {f['entity_type']} shape={shape_of(f['span'])} "
                          f"conf={f['confidence']:.2f}  [dim]{excerpt}[/]")
        db.traces.update_one({"_id": trace["_id"]}, {"$set": {"audited": True, "audit_findings": len(findings)}})
    db.traces.update_many({"audited": False, "blocked": True}, {"$set": {"audited": True, "audit_findings": 0}})
    return created


def main():
    from agentshield.db import get_db
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="poll for unaudited traces every 5s")
    args = ap.parse_args()
    db = get_db()
    while True:
        new = audit_pending(db)
        console.print(f"audited; {len(new)} new incident(s)")
        if not args.watch:
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_auditor.py -q`
Expected: `2 passed`

- [ ] **Step 6: Run against the real trace from Task 9**

Run: `uv run python -m agentshield.learning.auditor`
Expected: 1–3 `incident I-00NN` lines (policy number, badge, claim ID) with shapes like `INS-AA-0000-A`. Check in Atlas that the new incidents' `excerpt_redacted` contains no `INS-AZ-4471-K`.

- [ ] **Step 7: Commit**

```bash
git add agentshield/learning/auditor.py agentshield/prompts/auditor.md tests/test_auditor.py
git commit -m "feat: async LLM auditor that turns residual leaks into redacted incidents"
```

---

## Milestone M4: Synthesizer, validator, approval

### Task 13: Validator

**Files:**
- Create: `agentshield/learning/validator.py`, `tests/test_validator.py`

**Interfaces:**
- Consumes: `Rule`, `evaluate`, `load_eval_data`, `get_ner`, `get_settings`.
- Produces:
  - `ValidationContext(eval_set: list[dict], corpus: list[dict], base_rules: list[Rule], ner, fp_threshold: float = 0.01)` with `ValidationContext.load(db) -> ValidationContext`
  - `ValidationReport(passed: bool, checks: list[dict], metrics: dict)` with `.failures -> list[str]`, `.feedback_text() -> str`, `.to_dict() -> dict`
  - `check_backtracking(pattern: str, timeout: float = 1.0) -> bool`
  - `validate(candidate: dict, ctx: ValidationContext) -> ValidationReport` (candidate keys: `entity_type`, `pattern`, `positive_examples`, `negative_examples`)

- [ ] **Step 1: Write the failing test** `tests/test_validator.py`

```python
from agentshield.learning.validator import ValidationContext, check_backtracking, validate
from agentshield.synth_data import make_corpus_clean, make_eval_set


def ctx():
    return ValidationContext(make_eval_set(140), make_corpus_clean(200), [], ner=lambda t: [], fp_threshold=0.01)


GOOD = {
    "entity_type": "INSURANCE_POLICY_NUMBER",
    "pattern": r"\bINS-[A-Z]{2}-\d{4}-[A-Z]\b",
    "positive_examples": ["INS-AZ-4471-K", "INS-TX-0092-B", "INS-CA-1180-Q"],
    "negative_examples": ["INSTANT-RESULT", "IN-AZ-4471", "INS-AZ-4471", "SKU-AZ-4471"],
}


def test_good_rule_passes_and_raises_recall():
    r = validate(GOOD, ctx())
    assert r.passed, r.failures
    assert r.metrics["recall_after"] > r.metrics["recall_before"]
    assert r.metrics["candidate_fp_rate"] == 0.0


def test_bad_regex_fails_fast():
    r = validate({**GOOD, "pattern": "INS-[A-Z"}, ctx())
    assert not r.passed and r.failures == ["compiles"]


def test_catastrophic_backtracking_rejected_without_hanging():
    assert check_backtracking(r"\bINS-[A-Z]{2}-\d{4}-[A-Z]\b")
    assert not check_backtracking(r"^(a+)+$")


def test_match_everything_rejected_by_fp_gate():
    r = validate({**GOOD, "pattern": r"\w+", "negative_examples": []}, ctx())
    assert not r.passed and "clean_fp_rate" in r.failures


def test_negative_example_match_rejected():
    r = validate({**GOOD, "pattern": r"\bINS-[A-Z]{2}-\d{4}\b"}, ctx())
    assert "negatives" in r.failures
    assert "INS-AZ-4471" in r.feedback_text()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_validator.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement** `agentshield/learning/validator.py`

```python
"""Hard metric gates before a human sees a rule (3.5, 15.2)."""
import multiprocessing as mp
import re
from dataclasses import asdict, dataclass

from agentshield.evals import evaluate, load_eval_data
from agentshield.types import Rule

ADVERSARIAL = ["a" * 10_000, "A" * 5_000 + "!", "0" * 10_000, "-".join(["AA"] * 3_400),
               "INS-" * 2_500, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!" * 300]


def _search_all(pattern: str, ready) -> None:
    rx = re.compile(pattern)
    ready.set()  # imports done; only the search itself counts against the timeout
    for s in ADVERSARIAL:
        rx.search(s)


def check_backtracking(pattern: str, timeout: float = 1.0) -> bool:
    ctx = mp.get_context("spawn")  # fork is unsafe on macOS with pymongo threads
    ready = ctx.Event()
    proc = ctx.Process(target=_search_all, args=(pattern, ready), daemon=True)
    proc.start()
    if not ready.wait(60):
        proc.terminate()
        return False
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return False
    return proc.exitcode == 0


@dataclass
class ValidationContext:
    eval_set: list[dict]
    corpus: list[dict]
    base_rules: list[Rule]
    ner: object
    fp_threshold: float = 0.01

    @classmethod
    def load(cls, db) -> "ValidationContext":
        from agentshield.config import get_settings
        from agentshield.ner import get_ner
        eval_set, corpus = load_eval_data(db)
        rules = [Rule.from_doc(d) for d in db.rules.find({"status": "active"})]
        return cls(eval_set, corpus, rules, get_ner(), get_settings().fp_threshold)


@dataclass
class ValidationReport:
    passed: bool
    checks: list[dict]
    metrics: dict

    @property
    def failures(self) -> list[str]:
        return [c["name"] for c in self.checks if not c["passed"]]

    def feedback_text(self) -> str:
        return "\n".join(f"- {c['name']} FAILED: {c['detail']}" for c in self.checks if not c["passed"])

    def to_dict(self) -> dict:
        return asdict(self)


def validate(candidate: dict, ctx: ValidationContext) -> ValidationReport:
    checks: list[dict] = []
    metrics: dict = {}

    def add(name: str, ok: bool, detail: str) -> bool:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        return ok

    try:
        rx = re.compile(candidate["pattern"])
    except re.error as e:
        add("compiles", False, f"re.error: {e}")
        return ValidationReport(False, checks, metrics)
    add("compiles", True, "ok")

    if not add("no_catastrophic_backtracking", check_backtracking(candidate["pattern"]),
               "finished 10KB adversarial strings within 1s"):
        return ValidationReport(False, checks, metrics)

    pos, neg = candidate["positive_examples"], candidate["negative_examples"]
    pos_hit = [p for p in pos if rx.search(p)]
    neg_hit = [n for n in neg if rx.search(n)]
    metrics["positives"] = f"{len(pos_hit)}/{len(pos)}"
    metrics["negatives_matched"] = f"{len(neg_hit)}/{len(neg)}"
    add("positives", len(pos) >= 3 and len(pos_hit) == len(pos),
        f"matched {len(pos_hit)}/{len(pos)} (need all, at least 3); missed {[p for p in pos if p not in pos_hit]}")
    add("negatives", len(neg_hit) == 0, f"must match none; matched {neg_hit}")

    flagged = [c["text"] for c in ctx.corpus if rx.search(c["text"])]
    fp_rate = len(flagged) / len(ctx.corpus) if ctx.corpus else 0.0
    metrics["candidate_fp_rate"] = round(fp_rate, 4)
    add("clean_fp_rate", fp_rate < ctx.fp_threshold,
        f"{len(flagged)}/{len(ctx.corpus)} clean messages matched ({fp_rate:.2%}, limit {ctx.fp_threshold:.0%}); "
        f"examples: {flagged[:3]}")

    rule = Rule("CANDIDATE", 0, candidate["entity_type"], candidate["pattern"])
    before = evaluate(ctx.base_rules, ctx.ner, ctx.eval_set, [])
    after = evaluate(ctx.base_rules + [rule], ctx.ner, ctx.eval_set, [])
    metrics.update(recall_before=before["recall"], recall_after=after["recall"],
                   precision_before=before["precision"], precision_after=after["precision"],
                   entity_recall_before=before["by_entity"].get(candidate["entity_type"], {}).get("recall", 0.0),
                   entity_recall_after=after["by_entity"].get(candidate["entity_type"], {}).get("recall", 0.0))
    add("eval_delta", after["recall"] > before["recall"] and before["precision"] - after["precision"] <= 0.01,
        f"recall {before['recall']:.3f}->{after['recall']:.3f} (must rise), precision "
        f"{before['precision']:.3f}->{after['precision']:.3f} (may drop at most 0.01); "
        f"entity_type must be one of the labeled types, got {candidate['entity_type']}")

    return ValidationReport(all(c["passed"] for c in checks), checks, metrics)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_validator.py -q`
Expected: `5 passed` (backtracking test takes ~1–2 s)

- [ ] **Step 5: Commit**

```bash
git add agentshield/learning/validator.py tests/test_validator.py
git commit -m "feat: validator with compile, backtracking, example, FP, and eval-delta gates"
```

---

### Task 14: Rule synthesizer with retry loop

**Files:**
- Create: `agentshield/learning/synthesizer.py`, `agentshield/prompts/synthesizer.md`, `tests/test_synthesizer.py`

**Interfaces:**
- Consumes: `complete_json`, `load_prompt`, `similar_incidents`, `validate`, `ValidationContext`, `next_id`.
- Produces:
  - `SYNTH_SCHEMA: dict`
  - `build_user_prompt(incident: dict, similar: list[dict], taxonomy: list[dict], feedback: str | None) -> str`
  - `synthesize(incident, similar, taxonomy, feedback=None, llm=complete_json) -> dict`
  - `propose_rule(db, incident_id: str, max_attempts: int = 3, llm=complete_json, on_attempt=None) -> dict` → `{"status": "proposed", "rule_id", "attempts"}` | `{"status": "failed", "attempts"}` | `{"status": "not_regexable"}`. Proposed rule doc fields: everything in Section 5 `rules` plus `validation`, `attempts`, `rationale`, `positive_examples`, `negative_examples`, `taxonomy_term`, `playbook_suggestion`.
  - CLI: `python -m agentshield.learning.synthesizer [--incident I-0005]` (default: newest open, non-seeded incident).

- [ ] **Step 1: Write the failing test** `tests/test_synthesizer.py`

```python
from agentshield.learning.synthesizer import build_user_prompt

INCIDENT = {"incident_id": "I-0005", "agent_pair": "intake->claims", "entity_type_guess": "INSURANCE_POLICY_NUMBER",
            "shape": "INS-AA-0000-A", "excerpt_redacted": "policy <<SHAPE:INS-AA-0000-A>> was hit"}
SIMILAR = [{"incident_id": "I-0001", "entity_type_guess": "INSURANCE_POLICY_NUMBER", "shape": "INS-AA-0000-A",
            "excerpt_redacted": "refund for policy <<SHAPE:INS-AA-0000-A>>", "score": 0.91}]


def test_prompt_has_shape_context_and_feedback_but_no_raw_values():
    p = build_user_prompt(INCIDENT, SIMILAR, [{"term": "claim ID", "definition": "CLM-YYYY-NNNNNN"}],
                          feedback="- negatives FAILED: matched ['INS-AZ-4471']")
    assert "INS-AA-0000-A" in p and "I-0001" in p and "claim ID" in p
    assert "negatives FAILED" in p
    assert "INS-AZ-4471-K" not in p
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_synthesizer.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write** `agentshield/prompts/synthesizer.md`

```markdown
You write deterministic detection rules for a guardrail that sits between AI agents.
You get one new incident (a leak the inline filters missed), similar past incidents, and the domain taxonomy.
You never see the raw value, only its SHAPE: A = uppercase letter, a = lowercase letter, 0 = digit;
a short uppercase prefix like INS or CLM, and a leading 0x, are kept literally.

Write ONE Python regular expression that matches this kind of identifier in general, not the one value.
- Generalize from the shape. Prefer anchored, bounded patterns with \b and fixed repetition counts like \d{4}.
- No nested quantifiers like (a+)+. No .* or .+.
- Give at least 8 positive examples (realistic, synthetic, all matching) and at least 8 negative examples
  (near misses that must not match: wrong length, missing segment, SKUs, version strings, similar prefixes).
- entity_type: use the incident's entity_type_guess unless it is clearly wrong.
- If the thing cannot be expressed as a regex (for example a descriptive phrase about a person), return
  kind = "not_regexable" with empty pattern and empty example lists.
- playbook_suggestion.action is one of allow, mask, tokenize, generalize, block. Prefer tokenize for
  identifiers the downstream agent may need to reference.
If a previous attempt failed validation, the failure report is included. Fix exactly what it says.
```

- [ ] **Step 4: Implement** `agentshield/learning/synthesizer.py`

```python
import argparse
import json
from datetime import datetime, timezone

from rich.console import Console

from agentshield.db import next_id
from agentshield.learning.incidents import similar_incidents
from agentshield.learning.validator import ValidationContext, validate
from agentshield.llm import complete_json
from agentshield.prompts import load_prompt

console = Console()

SYNTH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "entity_type", "pattern", "rationale", "positive_examples", "negative_examples",
                 "taxonomy_term", "playbook_suggestion"],
    "properties": {
        "kind": {"type": "string", "enum": ["regex", "not_regexable"]},
        "entity_type": {"type": "string"},
        "pattern": {"type": "string"},
        "rationale": {"type": "string"},
        "positive_examples": {"type": "array", "items": {"type": "string"}},
        "negative_examples": {"type": "array", "items": {"type": "string"}},
        "taxonomy_term": {"type": "object", "additionalProperties": False,
                          "required": ["domain", "term", "definition"],
                          "properties": {"domain": {"type": "string"}, "term": {"type": "string"},
                                         "definition": {"type": "string"}}},
        "playbook_suggestion": {"type": "object", "additionalProperties": False,
                                "required": ["agent_pair", "action"],
                                "properties": {"agent_pair": {"type": "string"},
                                               "action": {"type": "string",
                                                          "enum": ["allow", "mask", "tokenize", "generalize", "block"]}}},
    },
}

INCIDENT_FIELDS = ["incident_id", "agent_pair", "entity_type_guess", "shape", "excerpt_redacted"]


def build_user_prompt(incident: dict, similar: list[dict], taxonomy: list[dict], feedback: str | None) -> str:
    payload = {
        "incident": {k: incident.get(k) for k in INCIDENT_FIELDS},
        "similar_past_incidents": [{k: s.get(k) for k in INCIDENT_FIELDS + ["score"]} for s in similar],
        "taxonomy": [{"term": t["term"], "definition": t["definition"]} for t in taxonomy],
    }
    text = json.dumps(payload, indent=2, default=str)
    if feedback:
        text += f"\n\nYour previous attempt failed validation:\n{feedback}"
    return text


def synthesize(incident: dict, similar: list[dict], taxonomy: list[dict], feedback: str | None = None,
               llm=complete_json) -> dict:
    return llm(load_prompt("synthesizer"), build_user_prompt(incident, similar, taxonomy, feedback),
               SYNTH_SCHEMA, "rule_candidate")


def propose_rule(db, incident_id: str, max_attempts: int = 3, llm=complete_json, on_attempt=None) -> dict:
    incident = db.incidents.find_one({"incident_id": incident_id})
    similar = similar_incidents(db, incident["embedding"], incident_id, incident["entity_type_guess"])
    taxonomy = list(db.taxonomy.find({"domain": "insurance"}, {"embedding": 0, "_id": 0}))
    ctx = ValidationContext.load(db)
    attempts, feedback = [], None
    for n in range(1, max_attempts + 1):
        cand = synthesize(incident, similar, taxonomy, feedback, llm)
        if cand["kind"] == "not_regexable":
            db.incidents.update_one({"incident_id": incident_id}, {"$set": {"resolution.status": "needs_human"}})
            return {"status": "not_regexable", "attempts": attempts}
        report = validate(cand, ctx)
        attempt = {"attempt": n, "pattern": cand["pattern"], "passed": report.passed,
                   "failures": report.failures, "metrics": report.metrics}
        attempts.append(attempt)
        if on_attempt:
            on_attempt(attempt, report)
        if report.passed:
            now = datetime.now(timezone.utc)
            rule_id = next_id(db, "rule", "R")
            db.rules.insert_one({
                "rule_id": rule_id, "version": 1, "entity_type": cand["entity_type"], "kind": "regex",
                "pattern": cand["pattern"], "status": "proposed",
                "scope": {"domain": "insurance", "agent_pair": "*"},
                "source_incident_id": incident_id, "parent_rule_id": None, "generation": None,
                "created_by": "synthesizer", "approved_by": None, "stats": {"live_hits": 0, "live_fp": 0},
                "rationale": cand["rationale"], "positive_examples": cand["positive_examples"],
                "negative_examples": cand["negative_examples"], "taxonomy_term": cand["taxonomy_term"],
                "playbook_suggestion": cand["playbook_suggestion"], "similar_incidents": [s["incident_id"] for s in similar],
                "validation": report.to_dict(), "attempts": attempts, "created_at": now, "updated_at": now,
            })
            db.incidents.update_one({"incident_id": incident_id},
                                    {"$set": {"resolution": {"status": "rule_proposed", "rule_id": rule_id}}})
            return {"status": "proposed", "rule_id": rule_id, "attempts": attempts}
        feedback = report.feedback_text()
    db.incidents.update_one({"incident_id": incident_id}, {"$set": {"synthesis_attempts": attempts}})
    return {"status": "failed", "attempts": attempts}


def _print_attempt(attempt: dict, report) -> None:
    mark = "[green]PASS[/]" if attempt["passed"] else "[red]FAIL[/]"
    console.print(f"  attempt {attempt['attempt']}: {mark} [cyan]{attempt['pattern']}[/] {attempt['metrics']}")
    if not attempt["passed"]:
        console.print(f"[dim]{report.feedback_text()}[/]")


def main():
    from agentshield.db import get_db
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident")
    args = ap.parse_args()
    db = get_db()
    incident_id = args.incident or (db.incidents.find_one(
        {"resolution.status": "open", "seeded": {"$ne": True}}, sort=[("ts", -1)]) or {}).get("incident_id")
    if not incident_id:
        console.print("no open incidents")
        return
    console.print(f"synthesizing rule for [bold]{incident_id}[/]")
    result = propose_rule(db, incident_id, on_attempt=_print_attempt)
    console.print(result["status"], result.get("rule_id", ""))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_synthesizer.py -q`
Expected: `1 passed`

- [ ] **Step 6: Run against a real incident**

Run: `uv run python -m agentshield.learning.synthesizer`
Expected: 1–3 attempt lines; final `proposed R-0001`. `rules` in Atlas has `R-0001` with `status: "proposed"` and a `validation` block.

- [ ] **Step 7: Commit**

```bash
git add agentshield/learning/synthesizer.py agentshield/prompts/synthesizer.md tests/test_synthesizer.py
git commit -m "feat: rule synthesizer with vector-search context and validator retry loop"
```

---

### Task 15: Approval CLI

**Files:**
- Create: `agentshield/cli/approve.py`

**Interfaces:**
- Consumes: `validate`, `ValidationContext`, `run_generation`, `print_eval_table`, `embed`, `get_settings`.
- Produces: `approve_rule(db, rule_id: str, approver: str) -> tuple[dict, dict | None]`, `reject_rule(db, rule_id: str, approver: str) -> None`, `edit_rule(db, rule_id: str, new_pattern: str) -> ValidationReport`. CLI: `python -m agentshield.cli.approve`.

- [ ] **Step 1: Implement** `agentshield/cli/approve.py`

```python
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agentshield.config import get_settings
from agentshield.embeddings import embed
from agentshield.evals import print_eval_table, run_generation
from agentshield.learning.validator import ValidationContext, validate

console = Console()


def render(db, rule: dict) -> None:
    inc = db.incidents.find_one({"incident_id": rule["source_incident_id"]}) or {}
    m = rule["validation"]["metrics"]
    body = Table.grid(padding=(0, 2))
    body.add_row("Incident", f"{inc.get('incident_id')}  {inc.get('agent_pair')}  conf {inc.get('auditor_confidence')}")
    body.add_row("Excerpt", inc.get("excerpt_redacted", ""))
    body.add_row("Similar", ", ".join(rule.get("similar_incidents", [])))
    body.add_row("Entity", rule["entity_type"])
    body.add_row("Pattern", f"[bold cyan]{rule['pattern']}[/]")
    body.add_row("Rationale", rule.get("rationale", ""))
    body.add_row("Tests", f"positives {m['positives']}, negatives matched {m['negatives_matched']}, "
                          f"clean FP {m['candidate_fp_rate']:.2%} on {db.corpus_clean.estimated_document_count()} msgs")
    body.add_row("Eval Δ", f"recall {m['recall_before']:.3f} → [green]{m['recall_after']:.3f}[/]   "
                           f"{rule['entity_type']} {m['entity_recall_before']:.2f} → [green]{m['entity_recall_after']:.2f}[/]   "
                           f"precision {m['precision_before']:.3f} → {m['precision_after']:.3f}")
    body.add_row("Attempts", str(len(rule.get("attempts", []))))
    body.add_row("Playbook", f"{rule['playbook_suggestion']['agent_pair']}: {rule['entity_type']} → "
                             f"{rule['playbook_suggestion']['action']}")
    console.print(Panel(body, title=f"Proposed rule {rule['rule_id']}", border_style="yellow"))


def approve_rule(db, rule_id: str, approver: str) -> tuple[dict, dict | None]:
    rule = db.rules.find_one({"rule_id": rule_id})
    top = db.rules.find_one({"status": "active"}, sort=[("generation", -1)])
    generation = (top or {}).get("generation", 0) + 1
    now = datetime.now(timezone.utc)
    db.rules.update_one({"rule_id": rule_id}, {"$set": {"status": "active", "approved_by": approver,
                                                         "generation": generation, "updated_at": now},
                                                "$inc": {"version": 1}})
    db.incidents.update_one({"incident_id": rule["source_incident_id"]},
                            {"$set": {"resolution": {"status": "rule_active", "rule_id": rule_id}}})
    pb = rule["playbook_suggestion"]
    db.playbooks.update_one({"agent_pair": pb["agent_pair"]},
                            {"$set": {f"actions.{rule['entity_type']}": pb["action"],
                                      "updated_from_incident": rule["source_incident_id"]},
                             "$inc": {"version": 1}}, upsert=True)
    term = rule["taxonomy_term"]
    db.taxonomy.update_one({"domain": term["domain"], "term": term["term"]},
                           {"$set": {"definition": term["definition"], "source_rule_id": rule_id,
                                     "embedding": embed([f"{term['term']}: {term['definition']}"])[0]}},
                           upsert=True)
    return run_generation(db, triggered_by=rule_id)


def reject_rule(db, rule_id: str, approver: str) -> None:
    rule = db.rules.find_one({"rule_id": rule_id})
    db.rules.update_one({"rule_id": rule_id}, {"$set": {"status": "retired", "rejected_by": approver,
                                                         "updated_at": datetime.now(timezone.utc)}})
    db.incidents.update_one({"incident_id": rule["source_incident_id"]},
                            {"$set": {"resolution": {"status": "open", "rule_id": None}}})


def edit_rule(db, rule_id: str, new_pattern: str):
    rule = db.rules.find_one({"rule_id": rule_id})
    report = validate({**rule, "pattern": new_pattern}, ValidationContext.load(db))
    if report.passed:
        db.rules.update_one({"rule_id": rule_id}, {"$set": {"pattern": new_pattern, "validation": report.to_dict(),
                                                             "updated_at": datetime.now(timezone.utc)}})
    return report


def main():
    from agentshield.db import get_db
    db, approver = get_db(), get_settings().approver
    proposed = list(db.rules.find({"status": "proposed"}).sort("created_at", 1))
    if not proposed:
        console.print("no proposed rules")
        return
    for rule in proposed:
        while True:
            render(db, rule)
            choice = Prompt.ask("[a]pprove  [r]eject  [e]dit  [s]kip", choices=["a", "r", "e", "s"], default="a")
            if choice == "a":
                current, previous = approve_rule(db, rule["rule_id"], approver)
                console.print(f"[green]approved {rule['rule_id']}[/] by {approver}; gateway reloads via change stream")
                print_eval_table(console, current, previous)
                break
            if choice == "r":
                reject_rule(db, rule["rule_id"], approver)
                console.print(f"[red]rejected {rule['rule_id']}[/]")
                break
            if choice == "e":
                report = edit_rule(db, rule["rule_id"], Prompt.ask("new pattern", default=rule["pattern"]))
                if not report.passed:
                    console.print(f"[red]edit failed validation[/]\n{report.feedback_text()}")
                rule = db.rules.find_one({"rule_id": rule["rule_id"]})
                continue
            break


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it** (gateway from Task 9 still running in Terminal A)

Run: `uv run python -m agentshield.cli.approve`, press `a`.
Expected: the panel; on approve, `approved R-0001`, a generation 1 eval table with the INSURANCE_POLICY_NUMBER row jumping (≈0.00 → ≈1.00) and overall recall up. **Terminal A logs `rule R-0001 v2 ACTIVE (INSURANCE_POLICY_NUMBER) -> live` within about a second**, with no restart.

- [ ] **Step 3: Commit**

```bash
git add agentshield/cli/approve.py
git commit -m "feat: Rich approval CLI that activates rules, updates playbook and taxonomy, runs next-gen evals"
```

---

## Milestone M5: Hot reload proof and demo

### Task 16: Demo runner, layout, README

**Files:**
- Create: `agentshield/cli/demo.py`, `scripts/demo_layout.sh`, `README.md`

**Interfaces:**
- Consumes: gateway HTTP API, `audit_pending`, `propose_rule`, `run_generation`, `print_eval_table`, `GOLDEN_MESSAGE`, `GOLDEN_SESSION`, `intake.summarize`.
- Produces: CLI `python -m agentshield.cli.demo {send,audit,propose,evals,lineage}`.

- [ ] **Step 1: Implement** `agentshield/cli/demo.py`

```python
import argparse

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentshield.config import get_settings
from agentshield.db import get_db
from demo_agents.fixtures import GOLDEN_MESSAGE, GOLDEN_SESSION

console = Console()


def send(message: str, session: str, via_intake: bool) -> None:
    if via_intake:
        from demo_agents.intake import summarize
        message = summarize(message)
    console.print(Panel(message, title="Intake sends (synthetic)", border_style="blue"))
    r = httpx.post(f"{get_settings().gateway_url}/a2a/forward", timeout=90, json={
        "from_agent": "intake", "to_agent": "claims", "message": message, "session_id": session}).json()
    t = Table("entity", "layer", "rule", title=f"detections ({r['latency_ms']} ms inline)")
    for d in r["detections"]:
        t.add_row(d["entity_type"], d["layer"], f"{d['rule_id'] or ''} v{d['rule_version'] or ''}".strip(" v"))
    console.print(t)
    style = "red" if r["blocked"] else "green"
    console.print(Panel(r["delivered_message"], title="Claims Agent receives", border_style=style))
    if r["reply"]:
        console.print(Panel(r["reply"], title="Reply to Intake (re-hydrated)", border_style="magenta"))


def lineage() -> None:
    db = get_db()
    t = Table("rule", "v", "gen", "entity", "status", "from incident", "approved by", "eval gen", title="rule lineage")
    for r in db.rules.find().sort("rule_id", 1):
        ev = db.evals.find_one({"triggered_by_rule": r["rule_id"]})
        t.add_row(r["rule_id"], str(r["version"]), str(r.get("generation") or "-"), r["entity_type"], r["status"],
                  r["source_incident_id"], r.get("approved_by") or "-", str(ev["generation"]) if ev else "-")
    console.print(t)


def main():
    ap = argparse.ArgumentParser(prog="demo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--message", default=GOLDEN_MESSAGE)
    s.add_argument("--session", default=GOLDEN_SESSION)
    s.add_argument("--via-intake", action="store_true", help="let the Intake LLM summarize first")
    sub.add_parser("audit")
    p = sub.add_parser("propose")
    p.add_argument("--incident")
    sub.add_parser("evals")
    sub.add_parser("lineage")
    args = ap.parse_args()

    if args.cmd == "send":
        send(args.message, args.session, args.via_intake)
    elif args.cmd == "audit":
        from agentshield.learning.auditor import audit_pending
        new = audit_pending(get_db())
        console.print(f"{len(new)} new incident(s): {new}")
    elif args.cmd == "propose":
        from agentshield.learning.synthesizer import _print_attempt, propose_rule
        db = get_db()
        ids = [args.incident] if args.incident else [i["incident_id"] for i in db.incidents.find(
            {"resolution.status": "open", "seeded": {"$ne": True}}).sort("ts", 1)]
        for incident_id in ids:
            console.print(f"[bold]{incident_id}[/]")
            result = propose_rule(db, incident_id, on_attempt=_print_attempt)
            console.print(f"  → {result['status']} {result.get('rule_id', '')}")
    elif args.cmd == "evals":
        from agentshield.evals import print_eval_table, run_generation
        print_eval_table(console, *run_generation(get_db()))
    elif args.cmd == "lineage":
        lineage()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement** `scripts/demo_layout.sh`

```bash
#!/usr/bin/env bash
# Four panes: gateway | demo runner / approval / evals (addendum 15.9)
set -euo pipefail
cd "$(dirname "$0")/.."
tmux kill-session -t shield 2>/dev/null || true
tmux new-session -d -s shield -n demo "uv run uvicorn agentshield.gateway:app --port 8765"
tmux split-window -h -t shield "bash"
tmux split-window -v -t shield:0.1 "bash"
tmux split-window -v -t shield:0.0 "bash"
tmux send-keys -t shield:0.1 "uv run python -m agentshield.cli.demo send" ""
tmux send-keys -t shield:0.2 "uv run python -m agentshield.cli.approve" ""
tmux send-keys -t shield:0.3 "uv run python scripts/run_evals.py" ""
tmux attach -t shield
```

Run: `chmod +x scripts/demo_layout.sh`

- [ ] **Step 3: Full loop rehearsal from a clean database**

```bash
uv run python scripts/seed.py --reset
uv run python scripts/run_evals.py                      # gen 0: novel entities ≈ 0
./scripts/demo_layout.sh                                 # gateway starts in pane 0
# pane 1:
uv run python -m agentshield.cli.demo send               # policy, badge, claim ID leak through
uv run python -m agentshield.cli.demo audit              # incidents created
uv run python -m agentshield.cli.demo propose            # rules proposed, retries visible
# pane 2:
uv run python -m agentshield.cli.approve                 # approve; pane 0 logs ACTIVE -> live
# pane 1:
uv run python -m agentshield.cli.demo send               # same message: now tokenized by L1 rules
uv run python -m agentshield.cli.demo lineage            # rule -> incident -> eval generation
```
Expected: second `send` shows `INSURANCE_POLICY_NUMBER L1 R-0001 v2` (and badge/claim rules if approved) and `<<INSURANCE_POLICY_NUMBER_xxxx>>` in "Claims Agent receives"; gateway never restarted. Then record LLM responses for a safe live demo: `LLM_RECORD=1 uv run python -m agentshield.cli.demo propose` on a fresh reset; demo with `LLM_REPLAY=1` if the network is slow.

- [ ] **Step 4: Write** `README.md`

```markdown
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

All data is synthetic (Faker + fixtures). Raw values exist only in the TTL'd `vault`; incidents store shapes and hashes.
```

- [ ] **Step 5: Run the whole test suite**

Run: `uv run pytest -q`
Expected: all tests pass (≈ 30).

- [ ] **Step 6: Commit and push**

```bash
git add agentshield/cli/demo.py scripts/demo_layout.sh README.md demo_agents/recordings
git commit -m "feat: demo runner, tmux layout, README with Built today section"
gh auth status | grep -A1 Akhilvallala1   # must be the active account
git push
```

---

## After M5 (only if time remains before 4:15)

Pick one M6 stretch from Section 9 (Agent Engine A2A + `allowed_callers`, rule retirement, or a trace viewer). Then: record the 1-minute video from a clean replayed run, confirm the repo is public, submit via the Cerebral Valley form by 5:00 PM.
