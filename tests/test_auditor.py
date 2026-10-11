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
