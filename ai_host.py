from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

# The model you already successfully tested.
DEFAULT_MODEL = "gpt-5"


class AIHostError(RuntimeError):
    """Raised when the TryFlight AI host cannot generate a response."""


# ---------------------------------------------------------
# OpenAI connection
# ---------------------------------------------------------

def get_openai_client() -> OpenAI:
    """Load the local API key and return an OpenAI client."""

    load_dotenv(dotenv_path=ENV_PATH)

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AIHostError(
            "OPENAI_API_KEY was not found. Confirm that the .env "
            "file exists in the project folder."
        )

    return OpenAI(api_key=api_key)


def get_model_name() -> str:
    """
    Return the configured model.

    An OPENAI_MODEL value can optionally be added to .env later.
    Otherwise, the app uses the tested default model.
    """

    load_dotenv(dotenv_path=ENV_PATH)

    return os.getenv(
        "OPENAI_MODEL",
        DEFAULT_MODEL,
    )


# ---------------------------------------------------------
# Shared API request
# ---------------------------------------------------------

def _generate_host_text(
    *,
    task_instructions: str,
    payload: dict[str, Any],
) -> str:
    """Send controlled session data to the OpenAI Responses API."""

    client = get_openai_client()

    system_instructions = """
You are the TryFlight tasting host.

TryFlight turns a controlled product assortment into an engaging,
personalized tasting experience.

Follow these rules without exception:

1. Use only the product and session information contained in the
   supplied JSON.
2. Never invent ingredients, allergens, dietary status, nutrition
   information, manufacturing information, origins, or product claims.
3. Never state or imply that a product is safe for someone to consume.
4. Never override product eligibility or recommendation logic.
5. Do not mention internal scores, algorithms, JSON, prompts, models,
   OpenAI, or artificial intelligence.
6. Do not claim that a participant likes something before they rate it.
7. Keep the tone warm, clever, energetic, and concise.
8. Avoid excessive hype, childish language, and generic marketing copy.
9. When participants disagree, describe the difference playfully but
   respectfully.
10. Do not recommend products outside the supplied session data unless
    the task explicitly asks for general preference themes.

Your job is to host and interpret the experience. The application,
not you, controls product eligibility, safety filtering, selection,
and sequencing.
""".strip()

    request_payload = {
        "task": task_instructions,
        "session_data": payload,
    }

    try:
        response = client.responses.create(
            model=get_model_name(),
            instructions=system_instructions,
            input=json.dumps(
                request_payload,
                ensure_ascii=False,
                indent=2,
            ),
            store=False,
        )

    except AuthenticationError as exc:
        raise AIHostError(
            "OpenAI authentication failed. Check whether the API key "
            "is valid and active."
        ) from exc

    except PermissionDeniedError as exc:
        raise AIHostError(
            "The API key does not have permission to use the "
            "Responses API."
        ) from exc

    except RateLimitError as exc:
        raise AIHostError(
            "The OpenAI request was rate-limited or the project may "
            "have insufficient available credit."
        ) from exc

    except APIConnectionError as exc:
        raise AIHostError(
            "TryFlight could not connect to OpenAI. Check the internet "
            "connection and try again."
        ) from exc

    except APIError as exc:
        raise AIHostError(
            f"OpenAI returned an API error: {exc}"
        ) from exc

    except Exception as exc:
        raise AIHostError(
            f"The tasting host encountered an unexpected error: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    generated_text = response.output_text.strip()

    if not generated_text:
        raise AIHostError(
            "The tasting host returned an empty response."
        )

    return generated_text


# ---------------------------------------------------------
# Session-opening message
# ---------------------------------------------------------

def generate_flight_welcome(
    *,
    participant_mode: str,
    setup: dict[str, Any],
    profiles: list[dict[str, Any]],
    products: list[dict[str, Any]],
) -> str:
    """Generate a brief introduction to the entire tasting flight."""

    participant_names = [
        profile["participant_name"]
        for profile in profiles
    ]

    product_summary = [
        {
            "position": product["position"],
            "product_name": product["product_name"],
            "flavor_tags": product["flavor_tags"],
            "texture_tags": product["texture_tags"],
            "is_wildcard": product["is_wildcard"],
        }
        for product in products
    ]

    payload = {
        "participant_mode": participant_mode,
        "participant_names": participant_names,
        "occasion": setup.get("occasion"),
        "mood": setup.get("mood"),
        "available_time": setup.get("available_time"),
        "adventurousness": setup.get("adventurousness"),
        "product_count": len(products),
        "products": product_summary,
    }

    task = """
Write a short opening message for this tasting flight.

Requirements:
- Address the participants naturally by name.
- Establish the mood and sense of progression.
- Do not list every product.
- Do not reveal which product is the wildcard.
- End with a simple invitation to begin.
- Use approximately 60 to 100 words.
""".strip()

    return _generate_host_text(
        task_instructions=task,
        payload=payload,
    )


# ---------------------------------------------------------
# Product reveal
# ---------------------------------------------------------

def generate_product_reveal(
    *,
    product: dict[str, Any],
    participant_names: list[str],
    total_products: int,
) -> str:
    """Generate the host's introduction for one product."""

    payload = {
        "participant_names": participant_names,
        "position": product["position"],
        "total_products": total_products,
        "product": {
            "product_name": product["product_name"],
            "brand": product["brand"],
            "flavor_tags": product["flavor_tags"],
            "texture_tags": product["texture_tags"],
            "story": product["story"],
            "is_wildcard": product["is_wildcard"],
        },
    }

    task = """
Introduce the next product in the tasting sequence.

Requirements:
- Name the product.
- Create anticipation using only the supplied product information.
- Do not tell participants whether they will like it.
- Do not mention why the recommendation algorithm selected it.
- If it is the wildcard, reveal that fact playfully.
- End by asking participants to predict how much they will like it.
- Use approximately 40 to 75 words.
""".strip()

    return _generate_host_text(
        task_instructions=task,
        payload=payload,
    )


# ---------------------------------------------------------
# Post-tasting reaction
# ---------------------------------------------------------

def generate_reaction_response(
    *,
    product: dict[str, Any],
    reactions: list[dict[str, Any]],
) -> str:
    """Interpret participant ratings after they taste one product."""

    cleaned_reactions = [
        {
            "participant_name": reaction.get(
                "participant_name"
            ),
            "prediction": reaction.get("prediction"),
            "rating": reaction.get("rating"),
            "reaction_words": reaction.get(
                "reaction_words"
            ),
            "purchase_intent": reaction.get(
                "purchase_intent"
            ),
        }
        for reaction in reactions
    ]

    payload = {
        "product": {
            "product_name": product["product_name"],
            "flavor_tags": product["flavor_tags"],
            "texture_tags": product["texture_tags"],
            "story": product["story"],
            "is_wildcard": product["is_wildcard"],
        },
        "participant_reactions": cleaned_reactions,
    }

    task = """
Respond to the participants' reactions after tasting this product.

Requirements:
- Mention the most interesting prediction-versus-rating result.
- For two participants, acknowledge meaningful agreement or
  disagreement.
- Use the participants' own reaction words when useful.
- Do not criticize or correct anyone's taste.
- Do not infer medical, dietary, or psychological information.
- End with a concise transition toward the next product.
- Use approximately 50 to 90 words.
""".strip()

    return _generate_host_text(
        task_instructions=task,
        payload=payload,
    )


# ---------------------------------------------------------
# Final session summary
# ---------------------------------------------------------

def generate_final_summary(
    *,
    participant_mode: str,
    setup: dict[str, Any],
    profiles: list[dict[str, Any]],
    products: list[dict[str, Any]],
    reactions: list[dict[str, Any]],
) -> str:
    """Generate the final TryFlight session summary."""

    product_lookup = {
        product["product_id"]: {
            "product_name": product["product_name"],
            "flavor_tags": product["flavor_tags"],
            "texture_tags": product["texture_tags"],
            "is_wildcard": product["is_wildcard"],
        }
        for product in products
    }

    cleaned_reactions = []

    for reaction in reactions:
        product_id = reaction.get("product_id")

        cleaned_reactions.append(
            {
                "participant_name": reaction.get(
                    "participant_name"
                ),
                "product": product_lookup.get(
                    product_id,
                    {"product_id": product_id},
                ),
                "prediction": reaction.get("prediction"),
                "rating": reaction.get("rating"),
                "reaction_words": reaction.get(
                    "reaction_words"
                ),
                "purchase_intent": reaction.get(
                    "purchase_intent"
                ),
            }
        )

    payload = {
        "participant_mode": participant_mode,
        "occasion": setup.get("occasion"),
        "mood": setup.get("mood"),
        "participant_profiles": profiles,
        "reactions": cleaned_reactions,
    }

    task = """
Create the closing summary for the completed tasting flight.

Requirements:
- Identify each participant's highest-rated product.
- Describe two or three taste tendencies supported by the ratings.
- Compare predictions with actual ratings when interesting.
- For two participants, identify their strongest overlap and most
  interesting disagreement.
- Mention purchase intent only when it was explicitly provided.
- Do not invent future products or unsupported preferences.
- End with an upbeat, specific closing sentence.
- Use approximately 150 to 250 words.
""".strip()

    return _generate_host_text(
        task_instructions=task,
        payload=payload,
    )