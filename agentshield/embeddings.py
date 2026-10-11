import httpx

from agentshield.config import get_settings


def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    s = get_settings()
    resp = httpx.post(
        f"{s.voyage_base_url.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {s.voyage_api_key}"},
        json={"input": texts, "model": s.voyage_model, "input_type": input_type},
        timeout=30,
    )
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]
