from agentshield.llm import complete_text
from agentshield.prompts import load_prompt


def summarize(customer_message: str) -> str:
    return complete_text(load_prompt("intake"), customer_message)
