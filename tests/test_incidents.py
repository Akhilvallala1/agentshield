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
