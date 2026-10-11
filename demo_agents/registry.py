from typing import Callable

from demo_agents import claims, intake

AGENTS: dict[str, Callable[[str], str]] = {
    "claims": claims.handle,
    "intake": intake.summarize,
}
