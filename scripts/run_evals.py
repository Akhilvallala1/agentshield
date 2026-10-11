from rich.console import Console

from agentshield.db import get_db
from agentshield.evals import print_eval_table, run_generation


def main():
    current, previous = run_generation(get_db())
    print_eval_table(Console(), current, previous)


if __name__ == "__main__":
    main()
