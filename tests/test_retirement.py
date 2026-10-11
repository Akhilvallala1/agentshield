from agentshield.pipeline import run
from agentshield.rules_cache import RulesCache
from agentshield.types import Rule

POLICY = Rule("R-0001", 2, "INSURANCE_POLICY_NUMBER", r"\bINS-[A-Z]{2}-\d{4}-[A-Z]\b")


def test_should_retire_needs_min_hits_and_fp_rate_above_threshold():
    from agentshield.learning.retirement import should_retire
    assert not should_retire({"live_hits": 4, "live_fp": 4})        # too few hits to judge
    assert not should_retire({"live_hits": 10, "live_fp": 2})       # exactly 20% is allowed
    assert should_retire({"live_hits": 10, "live_fp": 3})
    assert not should_retire({})


def test_hit_snippet_shows_shape_never_raw_value():
    from agentshield.learning.retirement import hit_snippets
    text = "New brochure for product INS-TX-0042-A ships Monday to all branches."
    res = run(text, [POLICY], {}, lambda t: [], salt="drift")
    hits = hit_snippets(text, res, salt="drift")
    assert hits == [{"rule_id": "R-0001", "rule_version": 2, "context": hits[0]["context"]}]
    assert "INS-TX-0042-A" not in hits[0]["context"]
    assert "<<SHAPE:INS-AA-0000-A>>" in hits[0]["context"]
    assert "brochure for product" in hits[0]["context"]


def test_judge_hits_ignores_bad_or_missing_verdicts():
    from agentshield.learning.retirement import judge_hits
    llm = lambda system, user, schema, schema_name, model=None: {"verdicts": [
        {"index": 0, "is_personal": False, "reasoning": "product code"},
        {"index": 7, "is_personal": False, "reasoning": "out of range"}]}
    assert judge_hits(["a", "b"], llm=llm) == [False, None]


def test_stats_only_updates_do_not_reload_rules():
    stats = {"operationType": "update",
             "updateDescription": {"updatedFields": {"stats.live_hits": 3}, "removedFields": []}}
    status = {"operationType": "update",
              "updateDescription": {"updatedFields": {"status": "shadow", "stats.live_fp": 1}, "removedFields": []}}
    assert RulesCache.is_stats_only(stats)
    assert not RulesCache.is_stats_only(status)
    assert not RulesCache.is_stats_only({"operationType": "insert"})
