from agentshield import llm
from agentshield.config import Settings


def test_record_then_replay_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "RECORDINGS", tmp_path)
    calls = []

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    calls.append(kw)
                    msg = type("M", (), {"content": '{"ok": true}'})
                    return type("R", (), {"choices": [type("C", (), {"message": msg})]})

    monkeypatch.setattr(llm, "_client", lambda: FakeClient)
    schema = {"type": "object", "additionalProperties": False, "required": ["ok"],
              "properties": {"ok": {"type": "boolean"}}}
    monkeypatch.setattr(llm, "get_settings", lambda: Settings(_env_file=None, llm_record=True))
    assert llm.complete_json("sys", "user", schema, "t") == {"ok": True}
    assert len(calls) == 1 and list(tmp_path.glob("*.json"))
    monkeypatch.setattr(llm, "get_settings", lambda: Settings(_env_file=None, llm_replay=True))
    assert llm.complete_json("sys", "user", schema, "t") == {"ok": True}
    assert len(calls) == 1  # served from the recording
