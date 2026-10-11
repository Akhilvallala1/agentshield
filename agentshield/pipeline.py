"""Inline path. Pure functions, no I/O, no LLM (addendum 15.3)."""
import hashlib
import re

from agentshield.types import NER, Detection, PipelineResult, Rule

DEFAULT_ACTION = "tokenize"
TOKEN_RE = re.compile(r"<<[A-Z_]+_[0-9a-f]{8}>>")
# Floor that no playbook can weaken (SEC4). mask and tokenize protect equally.
BASELINE_ACTIONS = {"SSN": "block", "CREDIT_CARD": "mask"}
ACTION_RANK = {"allow": 0, "generalize": 1, "tokenize": 2, "mask": 2, "block": 3}
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


def detect_raw(text: str, rules: list[Rule], ner: NER) -> list[Detection]:
    return _l1(text, rules) + ner(text)


def detect(text: str, rules: list[Rule], ner: NER) -> list[Detection]:
    return _resolve_overlaps(detect_raw(text, rules, ner))


def merged_action(existing: str | None, suggested: str) -> str:
    """Combine two actions without ever weakening protection."""
    if existing is None:
        return DEFAULT_ACTION if suggested == "allow" else suggested
    return suggested if ACTION_RANK.get(suggested, 0) > ACTION_RANK.get(existing, 0) else existing


def effective_actions(actions: dict[str, str]) -> dict[str, str]:
    out = dict(actions)
    for entity_type, floor in BASELINE_ACTIONS.items():
        out[entity_type] = merged_action(actions.get(entity_type), floor)
    return out


def _token(entity_type: str, value: str, salt: str) -> str:
    return f"<<{entity_type}_{hashlib.sha256((salt + value).encode()).hexdigest()[:8]}>>"


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


def transform(text: str, detections: list[Detection], actions: dict[str, str], salt: str = "",
              raw_detections: list[Detection] | None = None) -> PipelineResult:
    actions = effective_actions(actions)
    # Block is decided before overlap resolution so an overlapping rule cannot hide it (SEC1).
    candidates = detections if raw_detections is None else raw_detections
    blocked = sorted({d.entity_type for d in candidates if actions.get(d.entity_type) == "block"})
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
    raw = detect_raw(text, rules, ner)
    return transform(text, _resolve_overlaps(raw), actions, salt, raw_detections=raw)
