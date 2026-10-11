"""Single OpenAI entry point (addendum 15.10). Record/replay for demo safety (15.7)."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from openai import BadRequestError, OpenAI

from agentshield.config import get_settings

RECORDINGS = Path(__file__).resolve().parent.parent / "demo_agents" / "recordings"


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().llm_api_key)


def _call(model: str, messages: list[dict], response_format: dict | None) -> str:
    s = get_settings()
    key = hashlib.sha256(json.dumps([model, messages, response_format], sort_keys=True).encode()).hexdigest()[:16]
    path = RECORDINGS / f"{key}.json"
    if s.llm_replay and path.exists():
        return json.loads(path.read_text())["content"]
    kwargs = {"model": model, "messages": messages}
    if response_format:
        kwargs["response_format"] = response_format
    try:
        resp = _client().chat.completions.create(temperature=0, **kwargs)
    except BadRequestError as e:
        if "temperature" not in str(e):
            raise
        resp = _client().chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    if s.llm_record:
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"model": model, "content": content}, indent=2))
    return content


def complete_json(system: str, user: str, schema: dict, schema_name: str, model: str | None = None) -> dict:
    fmt = {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return json.loads(_call(model or get_settings().llm_model_reasoning, messages, fmt))


def complete_text(system: str, user: str, model: str | None = None) -> str:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return _call(model or get_settings().llm_model_fast, messages, None)
