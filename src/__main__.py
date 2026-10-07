"""Entry point: uv run python -m src <command> [options]."""

import fire

from src.cli import Commands


def main() -> None:
    """Expose the application commands through Python Fire."""
    fire.Fire(Commands)


if __name__ == "__main__":
    main()
