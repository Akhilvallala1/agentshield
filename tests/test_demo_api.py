import pytest
from fastapi.testclient import TestClient

import demo_api.app as demo
from agentshield.types import Detection

ORIGIN = "https://akhilvallala1.github.io"


def fake_ner(text):
    i = text.find("Maria Gonzalez")
    return [Detection("PERSON", i, i + 14, "L2")] if i >= 0 else []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(demo, "get_ner", lambda: fake_ner)
    monkeypatch.setattr(demo, "limiter", demo.RateLimiter(per_key=3, total=100))
    with TestClient(demo.app) as c:
        yield c


def test_learned_rule_and_ner_both_fire(client):
    text = "Maria Gonzalez spoke to adjuster ADJ#77-1043 today."
    r = client.post("/redact", json={"text": text}).json()
    assert [(d["entity_type"], d["layer"]) for d in r["detections"]] == [("PERSON", "L2"), ("ADJUSTER_BADGE", "L1")]
    assert "Maria Gonzalez" not in r["output"] and "ADJ#77-1043" not in r["output"]
    assert "<<ADJUSTER_BADGE_" in r["output"] and not r["blocked"]


def test_raw_values_never_returned(client):
    r = client.post("/redact", json={"text": "Maria Gonzalez and ADJ#12-3456"})
    assert "Maria Gonzalez" not in r.text and "ADJ#12-3456" not in r.text
    assert "tokens" not in r.json()


def test_retired_policy_rule_is_not_live(client):
    r = client.post("/redact", json={"text": "Product code INS-TX-0042-A ships Monday."}).json()
    assert r["detections"] == []


def test_ssn_blocks_message(monkeypatch, client):
    monkeypatch.setattr(demo, "get_ner", lambda: lambda t: [Detection("SSN", 4, 15, "L2")])
    r = client.post("/redact", json={"text": "ssn 123-45-6789"}).json()
    assert r["blocked"] and r["blocked_types"] == ["SSN"] and "123-45-6789" not in r["output"]


def test_length_cap(client):
    assert client.post("/redact", json={"text": "a" * 2001}).status_code == 422
    assert client.post("/redact", json={"text": ""}).status_code == 422


def test_rate_limit_per_ip(client):
    codes = [client.post("/redact", json={"text": "hi"}, headers={"x-forwarded-for": "1.2.3.4"}).status_code
             for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert client.post("/redact", json={"text": "hi"}, headers={"x-forwarded-for": "5.6.7.8"}).status_code == 200


def test_cors_only_for_the_site(client):
    ok = client.options("/redact", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    bad = client.options("/redact", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_no_docs_exposed(client):
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_health_route_avoids_cloud_run_reserved_z_suffix(client):
    assert client.get("/health").json() == {"ok": True}
