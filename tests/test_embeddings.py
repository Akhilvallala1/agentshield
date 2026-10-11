import httpx

from agentshield import embeddings


def test_embed_retries_on_429(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        req = httpx.Request("POST", url)
        if len(calls) < 3:
            return httpx.Response(429, request=req)
        return httpx.Response(200, request=req, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    monkeypatch.setattr(embeddings.time, "sleep", lambda s: None)
    assert embeddings.embed(["x"]) == [[0.1, 0.2]]
    assert len(calls) == 3
