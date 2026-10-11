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


def test_presidio_finds_standard_entities():
    from agentshield.ner import get_ner
    text = "Maria Gonzalez can be reached at maria.g@example.com or (415) 555-0134."
    types = {d.entity_type for d in get_ner()(text)}
    assert {"PERSON", "EMAIL", "PHONE"} <= types


def test_presidio_startup_is_quiet(caplog):
    import logging
    from agentshield.ner import PresidioNER
    with caplog.at_level(logging.INFO):
        PresidioNER()("Call 555 about the 3 cars")
    noisy = [r for r in caplog.records if r.name == "presidio-analyzer" and r.levelno >= logging.INFO]
    assert noisy == []
