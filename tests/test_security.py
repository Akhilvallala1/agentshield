"""Regression tests for security-plugin findings SEC1-SEC5, SEC9 (see ledger)."""
import re

from agentshield.pipeline import TOKEN_RE, run, transform
from agentshield.types import Detection, Rule

SSN_TEXT = "ssn 123-45-6789 on file"


def ssn_ner(text):
    i = text.find("123-45-6789")
    return [Detection("SSN", i, i + 11, "L2")] if i >= 0 else []


def test_sec1_overlapping_l1_rule_cannot_bypass_block():
    partial = Rule("R-9", 1, "PART", r"\d{3}-\d{2}")  # overlaps the SSN, wins overlap resolution
    res = run(SSN_TEXT, [partial], {"SSN": "block", "PART": "tokenize"}, ssn_ner)
    assert res.blocked and "SSN" in res.blocked_types
    assert "6789" not in res.text


def test_sec2_ner_cache_is_bounded():
    from agentshield.ner import PresidioNER
    ner = PresidioNER(cache_size=2)
    for t in ["alpha one", "beta two", "gamma three"]:
        ner(t)
    assert len(ner._cache) <= 2


def test_sec3_tokens_have_8_hex_chars():
    res = transform("x Maria Gonzalez", [Detection("PERSON", 2, 16, "L2")], {}, salt="s")
    token = next(iter(res.tokens))
    assert re.fullmatch(r"<<PERSON_[0-9a-f]{8}>>", token)
    assert TOKEN_RE.fullmatch(token)


def test_sec4_baseline_actions_apply_without_playbook():
    blocked = transform(SSN_TEXT, ssn_ner(SSN_TEXT), {})
    assert blocked.blocked
    card = "card 4111111111111111"
    masked = transform(card, [Detection("CREDIT_CARD", 5, 21, "L2")], {})
    assert masked.text == "card ************1111"


class _FakeVault:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query):
        return [d for d in self.docs if d["session_id"] == query["session_id"] and d["token"] in query["token"]["$in"]]


class _FakeDB:
    def __init__(self, docs):
        self.vault = _FakeVault(docs)


def test_sec5_rehydrate_only_tokens_minted_by_this_request():
    from agentshield.vault import rehydrate
    mine, replayed = "<<PERSON_aaaaaaaa>>", "<<SSN_bbbbbbbb>>"
    db = _FakeDB([{"session_id": "s", "token": mine, "value": "Maria"},
                  {"session_id": "s", "token": replayed, "value": "123-45-6789"}])
    out = rehydrate(db, "s", f"hi {mine} and {replayed}", allowed={mine})
    assert out == f"hi Maria and {replayed}"


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, q=None, *a, **k):
        docs = [d for d in self.docs if all(d.get(key) == v for key, v in (q or {}).items())]
        return _Cursor(docs)

    def find_one(self, q, *a, **k):
        return None

    def insert_one(self, doc):
        self.docs.append(doc)

    def update_one(self, *a, **k):
        pass

    def update_many(self, *a, **k):
        pass

    def find_one_and_update(self, q, u, **k):
        return {"seq": len(self.docs) + 1}


class _Cursor(list):
    def sort(self, *a):
        return self

    def limit(self, n):
        return self


class _AuditDB:
    def __init__(self, text):
        self.traces = _Coll([{"_id": 1, "audited": False, "blocked": False, "payload_redacted": text,
                              "agent_pair": "intake->claims", "direction": "request", "request_id": "r1"}])
        self.incidents = _Coll()
        self.counters = _Coll()


def test_sec9_i1_i2_incident_has_no_raw_values_or_reasoning():
    from agentshield.learning.auditor import audit_pending
    text = "Policy INS-AZ-4471-K. Please confirm INS-AZ-4471-K today. Badge ADJ#77-1043 too."
    findings = [
        {"span": "INS-AZ-4471-K", "entity_type": "INSURANCE_POLICY_NUMBER",
         "reasoning": "INS-AZ-4471-K is a policy", "confidence": 0.95},
        {"span": "ADJ#77-1043", "entity_type": "ADJUSTER_BADGE", "reasoning": "badge", "confidence": 0.5},
    ]
    db = _AuditDB(text)
    llm = lambda system, user, schema, schema_name, model=None: {"findings": findings}
    created = audit_pending(db, llm=llm, embed_fn=lambda texts: [[0.0]] * len(texts))
    assert len(created) == 1  # low-confidence badge does not become an incident...
    doc = db.incidents.docs[0]
    blob = repr(doc)
    assert "INS-AZ-4471-K" not in blob  # I1: every occurrence redacted
    assert "ADJ#77-1043" not in blob  # I2: ...but it is still redacted from the excerpt
    assert "auditor_reasoning" not in doc  # SEC9: LLM prose is never stored


def test_i3_overlapping_spans_merge_cleanly():
    from agentshield.learning.incidents import redact_excerpt
    text = "policy INS-AZ-4471-K ok"
    full = (7, 20)
    inner = (11, 18)  # "AZ-4471"
    assert redact_excerpt(text, [full, inner], focus=full) == "policy <<SHAPE:INS-AA-0000-A>> ok"


def test_i5_bad_rule_doc_does_not_kill_cache():
    from agentshield.rules_cache import RulesCache
    c = RulesCache(db=None)
    c.upsert_doc({"rule_id": "R-1", "version": 1, "entity_type": "X", "pattern": r"\bX\d\b",
                  "status": "active", "scope": {"agent_pair": "*"}})
    c.upsert_doc({"rule_id": "R-2", "version": 1, "entity_type": "Y", "pattern": "([unclosed",
                  "status": "active", "scope": {"agent_pair": "*"}})
    assert [r.rule_id for r in c.all_active()] == ["R-1"]


def test_sec12_playbook_update_never_weakens_existing_action():
    from agentshield.cli.approve import merged_action
    assert merged_action(existing="block", suggested="allow") == "block"
    assert merged_action(existing="tokenize", suggested="mask") == "tokenize"
    assert merged_action(existing=None, suggested="tokenize") == "tokenize"
    assert merged_action(existing="mask", suggested="block") == "block"


def test_sec13_untrusted_text_is_escaped_for_rich():
    from rich.console import Console
    from agentshield.cli.approve import safe
    console = Console(record=True, width=80)
    console.print(safe("[bold red]APPROVED BY SECURITY[/] policy <<SHAPE:INS-AA-0000-A>>"))
    assert "[bold red]APPROVED BY SECURITY[/]" in console.export_text()
