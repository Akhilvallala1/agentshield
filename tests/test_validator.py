from agentshield.learning.validator import ValidationContext, check_backtracking, validate
from agentshield.synth_data import make_corpus_clean, make_eval_set


def ctx():
    return ValidationContext(make_eval_set(140), make_corpus_clean(200), [], ner=lambda t: [], fp_threshold=0.01)


GOOD = {
    "entity_type": "INSURANCE_POLICY_NUMBER",
    "pattern": r"\bINS-[A-Z]{2}-\d{4}-[A-Z]\b",
    "positive_examples": ["INS-AZ-4471-K", "INS-TX-0092-B", "INS-CA-1180-Q"],
    "negative_examples": ["INSTANT-RESULT", "IN-AZ-4471", "INS-AZ-4471", "SKU-AZ-4471"],
}


def test_good_rule_passes_and_raises_recall():
    r = validate(GOOD, ctx())
    assert r.passed, r.failures
    assert r.metrics["recall_after"] > r.metrics["recall_before"]
    assert r.metrics["candidate_fp_rate"] == 0.0


def test_bad_regex_fails_fast():
    r = validate({**GOOD, "pattern": "INS-[A-Z"}, ctx())
    assert not r.passed and r.failures == ["compiles"]


def test_catastrophic_backtracking_rejected_without_hanging():
    assert check_backtracking(r"\bINS-[A-Z]{2}-\d{4}-[A-Z]\b")
    assert not check_backtracking(r"^(a+)+$")


def test_match_everything_rejected_by_fp_gate():
    r = validate({**GOOD, "pattern": r"\w+", "negative_examples": []}, ctx())
    assert not r.passed and "clean_fp_rate" in r.failures


def test_negative_example_match_rejected():
    r = validate({**GOOD, "pattern": r"\bINS-[A-Z]{2}-\d{4}\b"}, ctx())
    assert "negatives" in r.failures
    assert "INS-AZ-4471" in r.feedback_text()
