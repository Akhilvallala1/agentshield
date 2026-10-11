from agentshield.learning.synthesizer import build_user_prompt

INCIDENT = {"incident_id": "I-0005", "agent_pair": "intake->claims", "entity_type_guess": "INSURANCE_POLICY_NUMBER",
            "shape": "INS-AA-0000-A", "excerpt_redacted": "policy <<SHAPE:INS-AA-0000-A>> was hit"}
SIMILAR = [{"incident_id": "I-0001", "entity_type_guess": "INSURANCE_POLICY_NUMBER", "shape": "INS-AA-0000-A",
            "excerpt_redacted": "refund for policy <<SHAPE:INS-AA-0000-A>>", "score": 0.91}]


def test_prompt_has_shape_context_and_feedback_but_no_raw_values():
    p = build_user_prompt(INCIDENT, SIMILAR, [{"term": "claim ID", "definition": "CLM-YYYY-NNNNNN"}],
                          feedback="- negatives FAILED: matched ['INS-AZ-4471']")
    assert "INS-AA-0000-A" in p and "I-0001" in p and "claim ID" in p
    assert "negatives FAILED" in p
    assert "INS-AZ-4471-K" not in p
