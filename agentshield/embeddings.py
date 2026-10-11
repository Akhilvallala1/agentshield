import time

import httpx

from agentshield.config import get_settings

MAX_RETRIES = 6


def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    s = get_settings()
    for attempt in range(MAX_RETRIES):
        resp = httpx.post(
            f"{s.voyage_base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {s.voyage_api_key}"},
            json={"input": texts, "model": s.voyage_model, "input_type": input_type},
            timeout=30,
        )
        if resp.status_code != 429 or attempt == MAX_RETRIES - 1:
            break
        time.sleep(min(2 ** attempt, 20))  # rate limited: back off 1, 2, 4, 8, 16s
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]
