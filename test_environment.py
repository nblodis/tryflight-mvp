import os
from pathlib import Path

from dotenv import load_dotenv


# Locate the .env file in this project's top-level folder.
env_path = Path(__file__).resolve().parent / ".env"

# Load the variables stored in .env.
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError(
        "OPENAI_API_KEY was not found. Check that .env is in the "
        "project folder and contains OPENAI_API_KEY=your_key."
    )

print("Success: OpenAI API key loaded securely.")