from agentshield.llm import complete_text
from agentshield.prompts import load_prompt


def handle(message: str) -> str:
    return complete_text(load_prompt("claims"), message)
