from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {
    "product_id",
    "brand",
    "product_name",
    "flavor_tags",
    "texture_tags",
    "familiarity",
    "adventurousness",
    "intensity",
    "estimated_cost",
    "available",
    "label_verified",
    "allergens",
    "story",
}


def _parse_tags(value: Any) -> set[str]:
    """Convert a pipe-separated CSV value into a clean set of tags."""

    if pd.isna(value):
        return set()

    return {
        item.strip()
        for item in str(value).split("|")
        if item.strip()
    }


def _convert_boolean_column(
    catalog: pd.DataFrame,
    column_name: str,
) -> None:
    """Convert TRUE/FALSE text into real Python boolean values."""

    converted = (
        catalog[column_name]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(
            {
                "true": True,
                "false": False,
            }
        )
    )

    if converted.isna().any():
        raise ValueError(
            f"Column '{column_name}' must contain only TRUE or FALSE."
        )

    catalog[column_name] = converted


def load_catalog(catalog_path: Path) -> pd.DataFrame:
    """Load and validate the structured product catalog."""

    if not catalog_path.exists():
        raise FileNotFoundError(
            f"Product catalog was not found at: {catalog_path}"
        )

    catalog = pd.read_csv(catalog_path)

    missing_columns = REQUIRED_COLUMNS.difference(catalog.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"The catalog is missing required columns: {missing_text}"
        )

    _convert_boolean_column(catalog, "available")
    _convert_boolean_column(catalog, "label_verified")

    numeric_columns = [
        "familiarity",
        "adventurousness",
        "intensity",
        "estimated_cost",
    ]

    for column_name in numeric_columns:
        catalog[column_name] = pd.to_numeric(
            catalog[column_name],
            errors="raise",
        )

    return catalog


def _score_product(
    product: pd.Series,
    setup: dict,
    profiles: list[dict],
) -> tuple[float, list[str]]:
    """Score one eligible product against all participant profiles."""

    product_flavors = _parse_tags(product["flavor_tags"])
    product_textures = _parse_tags(product["texture_tags"])

    participant_scores: list[float] = []
    reasons: list[str] = []

    for profile in profiles:
        flavor_likes = set(profile.get("flavor_likes", []))
        flavor_dislikes = set(profile.get("flavor_dislikes", []))
        texture_likes = set(profile.get("texture_likes", []))
        texture_dislikes = set(profile.get("texture_dislikes", []))

        flavor_matches = product_flavors.intersection(flavor_likes)
        flavor_conflicts = product_flavors.intersection(flavor_dislikes)
        texture_matches = product_textures.intersection(texture_likes)
        texture_conflicts = product_textures.intersection(
            texture_dislikes
        )

        participant_score = 0.0

        participant_score += 4.0 * len(flavor_matches)
        participant_score += 3.0 * len(texture_matches)

        participant_score -= 6.0 * len(flavor_conflicts)
        participant_score -= 5.0 * len(texture_conflicts)

        desired_familiarity = int(
            profile.get("familiarity_preference", 3)
        )

        familiarity_difference = abs(
            int(product["familiarity"]) - desired_familiarity
        )

        participant_score += max(
            0.0,
            3.0 - familiarity_difference,
        )

        participant_scores.append(participant_score)

        if flavor_matches:
            reasons.append(
                "matches "
                + ", ".join(sorted(flavor_matches))
                + " flavor preferences"
            )

        if texture_matches:
            reasons.append(
                "includes preferred "
                + ", ".join(sorted(texture_matches))
                + " textures"
            )

    average_participant_score = (
        sum(participant_scores) / len(participant_scores)
    )

    desired_adventurousness = int(
        setup.get("adventurousness", 3)
    )

    adventure_difference = abs(
        int(product["adventurousness"])
        - desired_adventurousness
    )

    adventure_score = max(
        0.0,
        4.0 - adventure_difference,
    )

    total_score = average_participant_score + adventure_score

    occasion = setup.get("occasion", "")

    if occasion == "Take a challenge":
        total_score += float(product["adventurousness"]) * 0.5

    elif occasion == "Relax and unwind":
        total_score += float(product["familiarity"]) * 0.4

    if not reasons:
        reasons.append(
            "adds contrast and variety to the overall flight"
        )

    return total_score, sorted(set(reasons))


def _get_active_restrictions(
    profiles: list[dict],
) -> set[str]:
    """Combine restrictions entered by every participant."""

    restrictions: set[str] = set()

    for profile in profiles:
        for restriction in profile.get("restrictions", []):
            if restriction and restriction != "None":
                restrictions.add(restriction)

    return restrictions


def build_flight(
    catalog: pd.DataFrame,
    setup: dict,
    profiles: list[dict],
) -> dict:
    """Create a deterministic, budget-aware tasting flight."""

    sample_count = int(setup.get("sample_count", 6))
    budget = float(setup.get("budget", 20))

    eligible = catalog.loc[catalog["available"]].copy()

    if eligible.empty:
        raise ValueError(
            "No products in the catalog are currently available."
        )

    active_restrictions = _get_active_restrictions(profiles)

    if active_restrictions:
        unverified_products_exist = (
            ~eligible["label_verified"]
        ).any()

        if unverified_products_exist:
            raise ValueError(
                "This demo catalog has not been label-verified. "
                "TryFlight will not generate a flight for participants "
                "with allergy or dietary restrictions until verified "
                "product data is added."
            )

        eligible = eligible.loc[
            eligible["allergens"].apply(
                lambda value: not bool(
                    _parse_tags(value).intersection(
                        active_restrictions
                    )
                )
            )
        ]

    scored_products: list[dict] = []

    for _, product in eligible.iterrows():
        score, reasons = _score_product(
            product=product,
            setup=setup,
            profiles=profiles,
        )

        scored_products.append(
            {
                "product_id": product["product_id"],
                "brand": product["brand"],
                "product_name": product["product_name"],
                "flavor_tags": sorted(
                    _parse_tags(product["flavor_tags"])
                ),
                "texture_tags": sorted(
                    _parse_tags(product["texture_tags"])
                ),
                "familiarity": int(product["familiarity"]),
                "adventurousness": int(
                    product["adventurousness"]
                ),
                "intensity": int(product["intensity"]),
                "estimated_cost": float(
                    product["estimated_cost"]
                ),
                "story": product["story"],
                "score": score,
                "reasons": reasons,
            }
        )

    selected_products: list[dict] = []
    selected_flavors: set[str] = set()
    selected_textures: set[str] = set()
    total_cost = 0.0

    remaining_products = scored_products.copy()

    while (
        remaining_products
        and len(selected_products) < sample_count
    ):
        best_product: dict | None = None
        best_adjusted_score: float | None = None

        for candidate in remaining_products:
            candidate_cost = candidate["estimated_cost"]

            if total_cost + candidate_cost > budget:
                continue

            new_flavors = set(
                candidate["flavor_tags"]
            ).difference(selected_flavors)

            new_textures = set(
                candidate["texture_tags"]
            ).difference(selected_textures)

            diversity_bonus = (
                0.75 * len(new_flavors)
                + 0.50 * len(new_textures)
            )

            adjusted_score = (
                candidate["score"] + diversity_bonus
            )

            if (
                best_adjusted_score is None
                or adjusted_score > best_adjusted_score
            ):
                best_product = candidate
                best_adjusted_score = adjusted_score

        if best_product is None:
            break

        selected_products.append(best_product)

        selected_flavors.update(best_product["flavor_tags"])
        selected_textures.update(best_product["texture_tags"])

        total_cost += best_product["estimated_cost"]

        remaining_products = [
            product
            for product in remaining_products
            if product["product_id"]
            != best_product["product_id"]
        ]

    if len(selected_products) < sample_count:
        raise ValueError(
            f"Only {len(selected_products)} products fit within the "
            f"${budget:.0f} budget. Increase the budget or reduce the "
            "requested product count."
        )

    # Start with approachable products and build toward intensity.
    selected_products.sort(
        key=lambda product: (
            product["intensity"],
            product["adventurousness"],
        )
    )

    # Choose one deliberate wildcard.
    wildcard = max(
        selected_products,
        key=lambda product: (
            product["adventurousness"],
            product["intensity"],
        ),
    )

    if len(selected_products) >= 4:
        selected_products.remove(wildcard)
        selected_products.insert(-1, wildcard)

    for position, product in enumerate(
        selected_products,
        start=1,
    ):
        product["position"] = position
        product["is_wildcard"] = (
            product["product_id"]
            == wildcard["product_id"]
        )

    return {
        "products": selected_products,
        "total_cost": round(total_cost, 2),
        "catalog_warning": (
            "This flight uses fictional demo products. Replace them "
            "with products whose attributes and labels you personally "
            "verify before conducting a real tasting."
        ),
    }