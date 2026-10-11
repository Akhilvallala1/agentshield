"""Rule retirement: the harness prunes rules that turn out to be wrong on live traffic (3.8)."""
from datetime import datetime, timezone

from agentshield.db import next_id
from agentshield.embeddings import embed
from agentshield.evals import run_generation
from agentshield.learning.incidents import shape_of
from agentshield.llm import complete_json
from agentshield.pipeline import _token
from agentshield.prompts import load_prompt
from agentshield.types import PipelineResult

MIN_HITS = 5
MAX_FP_RATE = 0.2

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["index", "is_personal", "reasoning"],
        "properties": {"index": {"type": "integer"}, "is_personal": {"type": "boolean"},
                       "reasoning": {"type": "string"}}}}},
}


def fp_rate(stats: dict) -> float:
    hits = stats.get("live_hits", 0)
    return stats.get("live_fp", 0) / hits if hits else 0.0


def should_retire(stats: dict, min_hits: int = MIN_HITS, max_fp_rate: float = MAX_FP_RATE) -> bool:
    return stats.get("live_hits", 0) >= min_hits and fp_rate(stats) > max_fp_rate


def hit_snippets(original: str, result: PipelineResult, salt: str, window: int = 60) -> list[dict]:
    """Context around each L1 hit, taken from the forwarded text, with the hit shown only as its shape."""
    out = []
    for d in result.detections:
        if d.layer != "L1":
            continue
        value = original[d.start:d.end]
        token = _token(d.entity_type, value, salt)
        at = result.text.find(token)
        if at < 0:
            continue  # action was allow/mask: no token to anchor on
        shaped = f"<<SHAPE:{shape_of(value)}>>"
        lo, hi = max(0, at - window), min(len(result.text), at + len(token) + window)
        context = result.text[lo:at] + shaped + result.text[at + len(token):hi]
        out.append({"rule_id": d.rule_id, "rule_version": d.rule_version, "context": context})
    return out


def judge_hits(contexts: list[str], llm=complete_json) -> list[bool | None]:
    """is_personal per snippet; None where the model gave no usable verdict (never counted)."""
    numbered = "\n".join(f"[{i}] {c}" for i, c in enumerate(contexts))
    result = llm(load_prompt("hit_review"), numbered, REVIEW_SCHEMA, "hit_verdicts")
    verdicts: list[bool | None] = [None] * len(contexts)
    for v in result.get("verdicts", []):
        if isinstance(v.get("index"), int) and 0 <= v["index"] < len(contexts):
            verdicts[v["index"]] = bool(v["is_personal"])
    return verdicts


def review_hits(db, llm=complete_json) -> dict[str, int]:
    """Judge unreviewed L1 hits; returns false positives found per rule."""
    found: dict[str, int] = {}
    for trace in db.traces.find({"l1_hits.0": {"$exists": True}, "hits_reviewed": {"$ne": True}}):
        hits = trace["l1_hits"]
        for hit, personal in zip(hits, judge_hits([h["context"] for h in hits], llm)):
            if personal is False:
                db.rules.update_one({"rule_id": hit["rule_id"]}, {"$inc": {"stats.live_fp": 1}})
                found[hit["rule_id"]] = found.get(hit["rule_id"], 0) + 1
        db.traces.update_one({"_id": trace["_id"]}, {"$set": {"hits_reviewed": True}})
    return found


def retire(db, min_hits: int = MIN_HITS, max_fp_rate: float = MAX_FP_RATE, embed_fn=embed) -> list[dict]:
    retired = []
    for rule in db.rules.find({"status": "active"}):
        stats = rule.get("stats", {})
        if not should_retire(stats, min_hits, max_fp_rate):
            continue
        now = datetime.now(timezone.utc)
        rate = fp_rate(stats)
        db.rules.update_one({"rule_id": rule["rule_id"]}, {"$set": {
            "status": "shadow", "updated_at": now,
            "retired_reason": f"live FP rate {rate:.0%} on {stats['live_hits']} hits (limit {max_fp_rate:.0%})"}})
        samples = [h["context"] for t in db.traces.find({"l1_hits.rule_id": rule["rule_id"]}).limit(20)
                   for h in t["l1_hits"] if h["rule_id"] == rule["rule_id"]][:5]
        summary = f"{rule['entity_type']}: rule {rule['rule_id']} over-matches live traffic"
        incident_id = next_id(db, "incident", "I")
        db.incidents.insert_one({
            "incident_id": incident_id, "ts": now, "kind": "rule_fp", "agent_pair": rule["scope"]["agent_pair"],
            "entity_type_guess": rule["entity_type"], "shape": None, "span_sha256": None,
            "excerpt_redacted": " | ".join(samples), "missed_by": [], "rule_id": rule["rule_id"],
            "live_stats": stats, "resolution": {"status": "open", "rule_id": rule["rule_id"]},
            "embedding": embed_fn([summary])[0]})
        current, previous = run_generation(db, triggered_by=f"retire:{rule['rule_id']}")
        retired.append({"rule_id": rule["rule_id"], "fp_rate": rate, "hits": stats["live_hits"],
                        "incident_id": incident_id, "eval": current, "previous": previous})
    return retired
