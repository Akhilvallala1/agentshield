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
