import re
from dataclasses import asdict, dataclass, field
from typing import Callable


@dataclass
class Rule:
    rule_id: str
    version: int
    entity_type: str
    pattern: str
    agent_pair: str = "*"
    compiled: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        self.compiled = re.compile(self.pattern)

    @classmethod
    def from_doc(cls, doc: dict) -> "Rule":
        return cls(doc["rule_id"], doc.get("version", 1), doc["entity_type"], doc["pattern"],
                   doc.get("scope", {}).get("agent_pair", "*"))


@dataclass(frozen=True)
class Detection:
    entity_type: str
    start: int
    end: int
    layer: str
    rule_id: str | None = None
    rule_version: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PipelineResult:
    text: str
    detections: list[Detection]
    tokens: dict[str, tuple[str, str]]
    blocked: bool = False
    blocked_types: list[str] = field(default_factory=list)


NER = Callable[[str], list[Detection]]
