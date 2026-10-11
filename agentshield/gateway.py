import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rich.logging import RichHandler

from agentshield.db import get_db
from agentshield.learning.retirement import hit_snippets
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
    l1_hits = hit_snippets(text, res, salt=session_id)
    for rule_id in {h["rule_id"] for h in l1_hits}:
        db.rules.update_one({"rule_id": rule_id},
                            {"$inc": {"stats.live_hits": sum(h["rule_id"] == rule_id for h in l1_hits)}})
    db.traces.insert_one({
        "request_id": request_id, "session_id": session_id, "agent_pair": agent_pair, "direction": direction,
        "detections": [d.to_dict() for d in res.detections], "payload_redacted": res.text,
        "l1_hits": l1_hits, "blocked": res.blocked, "latency_ms": round(latency_ms, 2), "audited": False,
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
        reply = rehydrate(get_db(), req.session_id, back.text, allowed=set(out.tokens) | set(back.tokens))
    log.info("%s %s->%s detections=%d inline=%.1fms", request_id, req.from_agent, req.to_agent,
             len(out.detections), latency_ms)
    return ForwardResponse(request_id=request_id, delivered_message=out.text, reply=reply, blocked=out.blocked,
                           detections=[d.to_dict() for d in out.detections], latency_ms=round(latency_ms, 2))


@app.get("/health")
def health() -> dict:
    return {"active_rules": len(state.cache.all_active()), "reloads": state.cache.reload_count}
