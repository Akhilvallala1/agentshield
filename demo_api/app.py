"""Public demo endpoint for the portfolio site.

Runs only the inline fast path (compiled rules + Presidio). No LLM, no database, no learning loop:
public traffic can never write a rule. Nothing a visitor sends is logged or kept, and the NER cache
is disabled so raw text does not stay in memory between requests.
"""
import os
import secrets
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agentshield.ner import PresidioNER
from agentshield.pipeline import _resolve_overlaps, detect_raw, transform
from agentshield.types import Rule

MAX_CHARS = 2000
PER_IP_PER_MIN = int(os.getenv("PER_IP_PER_MIN", "20"))
GLOBAL_PER_MIN = int(os.getenv("GLOBAL_PER_MIN", "300"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "https://akhilvallala1.github.io").split(",") if o.strip()]

# The learned rule still active at the end of the recorded demo run (demo_agents/recordings).
# The policy-number rule from that run was later retired for firing on product codes, so it is not here.
LEARNED_RULES = [
    Rule("learned-ADJUSTER_BADGE", 1, "ADJUSTER_BADGE", r"(?<![A-Za-z0-9-])\bADJ#\d{2}-\d{4}\b(?![A-Za-z0-9-])"),
]
# Same policy as the intake->claims playbook, plus the learned entity.
ACTIONS = {"SSN": "block", "CREDIT_CARD": "mask", "PERSON": "tokenize", "EMAIL": "tokenize",
           "PHONE": "tokenize", "ADJUSTER_BADGE": "tokenize"}


class RedactRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)


class Span(BaseModel):
    entity_type: str
    start: int
    end: int
    layer: str  # "L1" learned rule, "L2" Presidio
    rule_id: str | None = None


class RedactResponse(BaseModel):
    output: str
    blocked: bool
    blocked_types: list[str]
    detections: list[Span]
    latency_ms: float


class RateLimiter:
    """Sliding one-minute window, in memory. Fine for a single small Cloud Run service."""

    def __init__(self, per_key: int, total: int):
        self.per_key, self.total = per_key, total
        self._hits: dict[str, deque] = {}
        self._all: deque = deque()
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            for q in (self._all, self._hits.setdefault(key, deque())):
                while q and now - q[0] > 60:
                    q.popleft()
            if len(self._all) >= self.total or len(self._hits[key]) >= self.per_key:
                return False
            self._all.append(now)
            self._hits[key].append(now)
            if len(self._hits) > 10_000:  # drop idle keys so memory stays bounded
                self._hits = {k: q for k, q in self._hits.items() if q}
            return True


@lru_cache
def get_ner() -> PresidioNER:
    return PresidioNER(cache_size=0)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_ner()("warm up")  # load spaCy before the first visitor arrives
    yield


limiter = RateLimiter(PER_IP_PER_MIN, GLOBAL_PER_MIN)
app = FastAPI(title="AgentShield demo", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"], max_age=600)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/redact", response_model=RedactResponse)
def redact(body: RedactRequest, request: Request) -> RedactResponse:
    if not limiter.allow(client_key(request)):
        raise HTTPException(429, "Too many requests. Try again in a minute.")
    t0 = time.perf_counter()
    raw = detect_raw(body.text, LEARNED_RULES, get_ner())
    dets = _resolve_overlaps(raw)
    res = transform(body.text, dets, ACTIONS, salt=secrets.token_hex(8), raw_detections=raw)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    # res.tokens maps tokens back to raw values; it is deliberately never returned.
    return RedactResponse(
        output=res.text, blocked=res.blocked, blocked_types=res.blocked_types, latency_ms=latency_ms,
        detections=[Span(entity_type=d.entity_type, start=d.start, end=d.end, layer=d.layer, rule_id=d.rule_id)
                    for d in dets])
