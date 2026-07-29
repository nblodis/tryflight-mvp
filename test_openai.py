import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import (
    OpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)


def main() -> None:
    """Verify that the project can successfully call the OpenAI API."""

    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY was not found.")

    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.create(
            model="gpt-5",
            input="Reply with exactly: TryFlight API connection successful",
            store=False,
        )

        print(response.output_text)

    except AuthenticationError:
        print(
            "Authentication failed. Check whether your API key is valid.",
            file=sys.stderr,
        )

    except PermissionDeniedError:
        print(
            "Permission denied. Confirm the key has Write access "
            "to the Responses API.",
            file=sys.stderr,
        )

    except RateLimitError:
        print(
            "The account may have insufficient credit, a $0 project limit, "
            "or a temporary rate limit.",
            file=sys.stderr,
        )

    except Exception as exc:
        print(
            f"Unexpected error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()