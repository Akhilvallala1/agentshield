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
