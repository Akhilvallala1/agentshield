import re

from agentshield.synth_data import NOVEL, make_corpus_clean, make_eval_set

NOVEL_RE = {
    "INSURANCE_POLICY_NUMBER": r"^INS-[A-Z]{2}-\d{4}-[A-Z]$",
    "CLAIM_ID": r"^CLM-\d{4}-\d{6}$",
    "ADJUSTER_BADGE": r"^ADJ#\d{2}-\d{4}$",
    "CRYPTO_WALLET": r"^0x[0-9a-f]{40}$",
}


def test_eval_set_spans_point_at_values():
    data = make_eval_set(120)
    assert len(data) == 120
    for ex in data:
        assert ex["spans"], ex
        for sp in ex["spans"]:
            value = ex["text"][sp["start"]:sp["end"]]
            assert value and value == value.strip()
            if sp["entity_type"] in NOVEL_RE:
                assert re.match(NOVEL_RE[sp["entity_type"]], value), (sp, value)


def test_eval_set_is_deterministic_and_covers_novel_types():
    a, b = make_eval_set(80), make_eval_set(80)
    assert a == b
    types = {sp["entity_type"] for ex in a for sp in ex["spans"]}
    assert set(NOVEL) <= types
    assert {ex["kind"] for ex in a} <= {"standard", "novel", "mixed"}


def test_corpus_clean_has_no_real_identifiers():
    corpus = make_corpus_clean(300)
    assert len(corpus) == 300
    for c in corpus:
        for pattern in NOVEL_RE.values():
            assert not re.search(pattern.strip("^$"), c["text"]), c["text"]
