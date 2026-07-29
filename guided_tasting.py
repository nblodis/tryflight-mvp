from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from ai_host import (
    AIHostError,
    generate_final_summary,
    generate_flight_welcome,
    generate_product_reveal,
    generate_reaction_response,
    get_model_name,
)
from analytics import (
    complete_session,
    create_session,
    log_event,
    save_host_message,
    save_prediction,
    save_reactions,
    update_session_status,
)


# ---------------------------------------------------------
# Guided-tasting session-state keys
# ---------------------------------------------------------

GUIDED_TASTING_STATE_KEYS = (
    "tasting_index",
    "tasting_reactions",
    "tasting_predictions",
    "welcome_text",
    "reveal_texts",
    "reaction_responses",
    "final_summary",
    "ai_host_error",
    "analytics_session_id",
    "analytics_session_completed",
    "analytics_warning",
)


# ---------------------------------------------------------
# Navigation and state
# ---------------------------------------------------------

def _navigate_to(page_name: str) -> None:
    """Navigate to another application page."""
    st.session_state["page"] = page_name
    st.rerun()


def clear_guided_tasting_state() -> None:
    """Remove all state created by a guided tasting session."""

    for key in GUIDED_TASTING_STATE_KEYS:
        st.session_state.pop(key, None)


def _analytics_session_id() -> str | None:
    """Return the active analytics session ID, when available."""
    return st.session_state.get("analytics_session_id")


def _safe_analytics_call(
    action_label: str,
    operation: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> tuple[bool, Any | None]:
    """
    Run one analytics operation without breaking the tasting experience.

    Analytics errors are surfaced in the interface, while the consumer
    flow is allowed to continue.
    """

    try:
        result = operation(*args, **kwargs)
        return True, result

    except Exception as exc:
        st.session_state["analytics_warning"] = (
            f"Analytics could not complete '{action_label}': "
            f"{type(exc).__name__}: {exc}"
        )

        return False, None


def _show_analytics_warning() -> None:
    """Display a non-blocking analytics warning, if one exists."""

    warning = st.session_state.get("analytics_warning")

    if warning:
        st.warning(
            warning
            + " The tasting can continue, but this activity may not "
            "have been saved."
        )


def _ensure_analytics_session(
    *,
    participant_mode: str,
    setup: dict[str, Any],
    profiles: list[dict[str, Any]],
    flight: dict[str, Any],
) -> str | None:
    """Create the persistent analytics session when one does not exist."""

    existing_session_id = _analytics_session_id()

    if existing_session_id:
        return existing_session_id

    success, result = _safe_analytics_call(
        "create tasting session",
        create_session,
        participant_mode=participant_mode,
        setup=setup,
        profiles=profiles,
        flight=flight,
        model_name=get_model_name(),
    )

    if not success or not result:
        return None

    session_id = str(result)
    st.session_state["analytics_session_id"] = session_id

    return session_id


def start_guided_tasting() -> None:
    """Initialize a new guided tasting and persistent test session."""

    participant_mode = st.session_state.get("participant_mode")
    setup = st.session_state.get("experience_setup")
    profiles = st.session_state.get("participant_profiles")
    flight = st.session_state.get("flight")

    if (
        not participant_mode
        or not setup
        or not profiles
        or not flight
    ):
        st.session_state["page"] = "review"
        st.rerun()

    clear_guided_tasting_state()

    st.session_state["tasting_index"] = 0
    st.session_state["tasting_reactions"] = []
    st.session_state["tasting_predictions"] = {}
    st.session_state["reveal_texts"] = {}
    st.session_state["reaction_responses"] = {}

    _ensure_analytics_session(
        participant_mode=participant_mode,
        setup=setup,
        profiles=profiles,
        flight=flight,
    )

    _navigate_to("guided_tasting")


# ---------------------------------------------------------
# Session-data helpers
# ---------------------------------------------------------

def _participant_names(
    profiles: list[dict[str, Any]],
) -> list[str]:
    """Return all participant names."""

    return [
        profile["participant_name"]
        for profile in profiles
    ]


def _product_reactions(
    product_id: str,
) -> list[dict[str, Any]]:
    """Return saved reactions for one product."""

    return [
        reaction
        for reaction in st.session_state.get(
            "tasting_reactions",
            [],
        )
        if reaction["product_id"] == product_id
    ]


def _prediction_for(
    product_id: str,
    participant_name: str,
) -> int | None:
    """Return one participant's saved prediction."""

    return (
        st.session_state.get(
            "tasting_predictions",
            {},
        )
        .get(product_id, {})
        .get(participant_name)
    )


# ---------------------------------------------------------
# AI-host message generation and persistence
# ---------------------------------------------------------

def _load_welcome_message(
    *,
    participant_mode: str,
    setup: dict[str, Any],
    profiles: list[dict[str, Any]],
    products: list[dict[str, Any]],
) -> None:
    """Generate and save the session welcome once."""

    if st.session_state.get("welcome_text"):
        return

    with st.spinner(
        "Your TryFlight host is preparing the session..."
    ):
        welcome_text = generate_flight_welcome(
            participant_mode=participant_mode,
            setup=setup,
            profiles=profiles,
            products=products,
        )

    st.session_state["welcome_text"] = welcome_text

    session_id = _analytics_session_id()

    if session_id:
        _safe_analytics_call(
            "save host welcome",
            save_host_message,
            session_id=session_id,
            message_type="flight_welcome",
            content=welcome_text,
        )

        _safe_analytics_call(
            "log host welcome",
            log_event,
            session_id=session_id,
            event_name="flight_welcome_generated",
            event_data={
                "character_count": len(welcome_text),
            },
        )


def _load_product_reveal(
    *,
    product: dict[str, Any],
    participant_names: list[str],
    total_products: int,
) -> None:
    """Generate and save one product reveal once."""

    reveal_texts = st.session_state.setdefault(
        "reveal_texts",
        {},
    )

    product_id = product["product_id"]

    if product_id in reveal_texts:
        return

    with st.spinner("Preparing the next reveal..."):
        reveal_text = generate_product_reveal(
            product=product,
            participant_names=participant_names,
            total_products=total_products,
        )

    reveal_texts[product_id] = reveal_text

    session_id = _analytics_session_id()

    if session_id:
        _safe_analytics_call(
            "save product reveal",
            save_host_message,
            session_id=session_id,
            message_type="product_reveal",
            product_id=product_id,
            content=reveal_text,
        )

        _safe_analytics_call(
            "log product reveal",
            log_event,
            session_id=session_id,
            event_name="product_reveal_generated",
            product_id=product_id,
            event_data={
                "position": product["position"],
                "is_wildcard": product["is_wildcard"],
            },
        )


# ---------------------------------------------------------
# Prediction collection
# ---------------------------------------------------------

def _show_prediction_form(
    *,
    product: dict[str, Any],
    profiles: list[dict[str, Any]],
) -> None:
    """Collect and persist predictions before tasting."""

    product_id = product["product_id"]

    st.subheader("Make your prediction")

    st.write(
        "Before tasting, predict how much you expect "
        "to like this product."
    )

    with st.form(
        f"prediction_form_{product_id}"
    ):
        predictions: dict[str, int] = {}

        for participant_index, profile in enumerate(
            profiles
        ):
            participant_name = profile[
                "participant_name"
            ]

            predictions[participant_name] = st.slider(
                f"{participant_name}'s prediction",
                min_value=1,
                max_value=10,
                value=5,
                key=(
                    f"prediction_"
                    f"{product_id}_"
                    f"{participant_index}"
                ),
            )

        submitted = st.form_submit_button(
            "Lock predictions",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    st.session_state.setdefault(
        "tasting_predictions",
        {},
    )[product_id] = predictions

    st.session_state.pop(
        "ai_host_error",
        None,
    )

    session_id = _analytics_session_id()

    if session_id:
        for participant_name, prediction in predictions.items():
            _safe_analytics_call(
                "save prediction",
                save_prediction,
                session_id=session_id,
                product_id=product_id,
                participant_name=participant_name,
                prediction=prediction,
            )

        _safe_analytics_call(
            "log predictions locked",
            log_event,
            session_id=session_id,
            event_name="predictions_locked",
            product_id=product_id,
            event_data={
                "predictions": predictions,
                "position": product["position"],
            },
        )

    st.rerun()


# ---------------------------------------------------------
# Reaction collection
# ---------------------------------------------------------

def _show_rating_form(
    *,
    product: dict[str, Any],
    profiles: list[dict[str, Any]],
) -> None:
    """Collect ratings, reactions, and purchase intent."""

    product_id = product["product_id"]

    st.subheader("Taste, then react")

    st.write(
        "Taste the product, record your first reaction, "
        "and rate it."
    )

    purchase_options = [
        "Definitely not",
        "Probably not",
        "Maybe",
        "Probably yes",
        "Definitely yes",
    ]

    with st.form(
        f"rating_form_{product_id}"
    ):
        submitted_reactions: list[
            dict[str, Any]
        ] = []

        for participant_index, profile in enumerate(
            profiles
        ):
            participant_name = profile[
                "participant_name"
            ]

            st.markdown(
                f"#### {participant_name}"
            )

            rating = st.slider(
                "Rating",
                min_value=1,
                max_value=10,
                value=5,
                key=(
                    f"rating_"
                    f"{product_id}_"
                    f"{participant_index}"
                ),
            )

            reaction_words = st.text_input(
                "First reaction",
                placeholder=(
                    "Examples: richer than expected, "
                    "too sour, or great crunch."
                ),
                key=(
                    f"reaction_words_"
                    f"{product_id}_"
                    f"{participant_index}"
                ),
            )

            purchase_intent = st.selectbox(
                "Would you consider buying it?",
                options=purchase_options,
                index=2,
                key=(
                    f"purchase_intent_"
                    f"{product_id}_"
                    f"{participant_index}"
                ),
            )

            submitted_reactions.append(
                {
                    "product_id": product_id,
                    "participant_name": (
                        participant_name
                    ),
                    "prediction": _prediction_for(
                        product_id,
                        participant_name,
                    ),
                    "rating": rating,
                    "reaction_words": (
                        reaction_words.strip()
                    ),
                    "purchase_intent": (
                        purchase_intent
                    ),
                }
            )

        submitted = st.form_submit_button(
            "Submit reactions",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    existing_reactions = [
        reaction
        for reaction in st.session_state.get(
            "tasting_reactions",
            [],
        )
        if reaction["product_id"] != product_id
    ]

    st.session_state["tasting_reactions"] = (
        existing_reactions
        + submitted_reactions
    )

    session_id = _analytics_session_id()

    if session_id:
        _safe_analytics_call(
            "save participant reactions",
            save_reactions,
            session_id=session_id,
            reactions=submitted_reactions,
        )

        _safe_analytics_call(
            "log reactions submitted",
            log_event,
            session_id=session_id,
            event_name="reactions_submitted",
            product_id=product_id,
            event_data={
                "position": product["position"],
                "reactions": [
                    {
                        "participant_name": reaction[
                            "participant_name"
                        ],
                        "prediction": reaction[
                            "prediction"
                        ],
                        "rating": reaction["rating"],
                        "purchase_intent": reaction[
                            "purchase_intent"
                        ],
                        "has_reaction_words": bool(
                            reaction[
                                "reaction_words"
                            ]
                        ),
                    }
                    for reaction in submitted_reactions
                ],
            },
        )

    try:
        with st.spinner(
            "Your host is reading the room..."
        ):
            host_response = (
                generate_reaction_response(
                    product=product,
                    reactions=submitted_reactions,
                )
            )

        st.session_state.setdefault(
            "reaction_responses",
            {},
        )[product_id] = host_response

        st.session_state.pop(
            "ai_host_error",
            None,
        )

        if session_id:
            _safe_analytics_call(
                "save host reaction",
                save_host_message,
                session_id=session_id,
                message_type="reaction_response",
                product_id=product_id,
                content=host_response,
            )

            _safe_analytics_call(
                "log host reaction",
                log_event,
                session_id=session_id,
                event_name="host_reaction_generated",
                product_id=product_id,
                event_data={
                    "character_count": len(
                        host_response
                    ),
                },
            )

    except AIHostError as exc:
        st.session_state[
            "ai_host_error"
        ] = str(exc)

        if session_id:
            _safe_analytics_call(
                "log host reaction failure",
                log_event,
                session_id=session_id,
                event_name="host_reaction_failed",
                product_id=product_id,
                event_data={
                    "error": str(exc),
                },
            )

    st.rerun()


def _retry_reaction_response(
    *,
    product: dict[str, Any],
    reactions: list[dict[str, Any]],
) -> None:
    """Retry the host response without losing ratings."""

    product_id = product["product_id"]
    session_id = _analytics_session_id()

    try:
        with st.spinner(
            "Your host is reading the room..."
        ):
            host_response = (
                generate_reaction_response(
                    product=product,
                    reactions=reactions,
                )
            )

        st.session_state.setdefault(
            "reaction_responses",
            {},
        )[product_id] = host_response

        st.session_state.pop(
            "ai_host_error",
            None,
        )

        if session_id:
            _safe_analytics_call(
                "save retried host reaction",
                save_host_message,
                session_id=session_id,
                message_type="reaction_response",
                product_id=product_id,
                content=host_response,
            )

            _safe_analytics_call(
                "log host reaction retry",
                log_event,
                session_id=session_id,
                event_name="host_reaction_retry_succeeded",
                product_id=product_id,
            )

    except AIHostError as exc:
        st.session_state[
            "ai_host_error"
        ] = str(exc)

        if session_id:
            _safe_analytics_call(
                "log failed host reaction retry",
                log_event,
                session_id=session_id,
                event_name="host_reaction_retry_failed",
                product_id=product_id,
                event_data={
                    "error": str(exc),
                },
            )

    st.rerun()


# ---------------------------------------------------------
# Completed-product display and advancement
# ---------------------------------------------------------

def _show_completed_product(
    *,
    product: dict[str, Any],
    total_products: int,
) -> None:
    """Show the host response and advance the tasting."""

    product_id = product["product_id"]

    reactions = _product_reactions(
        product_id
    )

    host_response = (
        st.session_state.get(
            "reaction_responses",
            {},
        ).get(product_id)
    )

    if host_response:
        st.info(host_response)

    with st.expander(
        "See submitted reactions"
    ):
        for reaction in reactions:
            st.write(
                f"**{reaction['participant_name']}** — "
                f"Prediction: "
                f"{reaction['prediction']}/10 · "
                f"Rating: "
                f"{reaction['rating']}/10 · "
                f"Purchase intent: "
                f"{reaction['purchase_intent']}"
            )

            if reaction["reaction_words"]:
                st.caption(
                    reaction["reaction_words"]
                )

    current_index = st.session_state.get(
        "tasting_index",
        0,
    )

    is_last_product = (
        current_index
        == total_products - 1
    )

    button_label = (
        "Finish and see results"
        if is_last_product
        else "Continue to next product"
    )

    if not st.button(
        button_label,
        type="primary",
        use_container_width=True,
    ):
        return

    session_id = _analytics_session_id()

    if session_id:
        _safe_analytics_call(
            "log product completion",
            log_event,
            session_id=session_id,
            event_name="product_completed",
            product_id=product_id,
            event_data={
                "position": product["position"],
                "is_last_product": is_last_product,
            },
        )

    if is_last_product:
        _navigate_to("results")

    else:
        st.session_state[
            "tasting_index"
        ] = current_index + 1

        st.session_state.pop(
            "ai_host_error",
            None,
        )

        st.rerun()


# ---------------------------------------------------------
# Guided tasting page
# ---------------------------------------------------------

def show_guided_tasting_page() -> None:
    """Run the complete guided tasting experience."""

    flight = st.session_state.get(
        "flight"
    )

    participant_mode = st.session_state.get(
        "participant_mode"
    )

    setup = st.session_state.get(
        "experience_setup"
    )

    profiles = st.session_state.get(
        "participant_profiles"
    )

    if (
        not flight
        or not participant_mode
        or not setup
        or not profiles
    ):
        _navigate_to("review")
        return

    products = flight["products"]

    _ensure_analytics_session(
        participant_mode=participant_mode,
        setup=setup,
        profiles=profiles,
        flight=flight,
    )

    _show_analytics_warning()

    participant_names = (
        _participant_names(profiles)
    )

    if "tasting_index" not in st.session_state:
        st.session_state[
            "tasting_index"
        ] = 0

    try:
        _load_welcome_message(
            participant_mode=participant_mode,
            setup=setup,
            profiles=profiles,
            products=products,
        )

    except AIHostError as exc:
        st.error(str(exc))

        session_id = _analytics_session_id()

        if session_id:
            _safe_analytics_call(
                "log welcome failure",
                log_event,
                session_id=session_id,
                event_name="flight_welcome_failed",
                event_data={
                    "error": str(exc),
                },
            )

        if st.button(
            "Retry host introduction",
            use_container_width=True,
        ):
            st.session_state.pop(
                "welcome_text",
                None,
            )

            st.rerun()

        return

    current_index = st.session_state[
        "tasting_index"
    ]

    if current_index >= len(products):
        _navigate_to("results")
        return

    product = products[current_index]
    product_id = product["product_id"]

    st.title("Guided tasting")

    st.progress(
        (current_index + 1)
        / len(products),
        text=(
            f"Product {current_index + 1} "
            f"of {len(products)}"
        ),
    )

    with st.expander(
        "Welcome from your host",
        expanded=current_index == 0,
    ):
        st.write(
            st.session_state[
                "welcome_text"
            ]
        )

    try:
        _load_product_reveal(
            product=product,
            participant_names=(
                participant_names
            ),
            total_products=len(products),
        )

    except AIHostError as exc:
        st.error(str(exc))

        session_id = _analytics_session_id()

        if session_id:
            _safe_analytics_call(
                "log product reveal failure",
                log_event,
                session_id=session_id,
                event_name="product_reveal_failed",
                product_id=product_id,
                event_data={
                    "error": str(exc),
                },
            )

        if st.button(
            "Retry product reveal",
            use_container_width=True,
        ):
            st.session_state.setdefault(
                "reveal_texts",
                {},
            ).pop(
                product_id,
                None,
            )

            st.rerun()

        return

    st.divider()

    wildcard_label = (
        " · Wildcard"
        if product["is_wildcard"]
        else ""
    )

    st.header(
        f"{product['position']}. "
        f"{product['product_name']}"
        f"{wildcard_label}"
    )

    st.caption(product["brand"])

    st.write(
        st.session_state[
            "reveal_texts"
        ][product_id]
    )

    st.warning(
        "Before tasting, confirm the physical package "
        "and allergen label are appropriate for every "
        "participant."
    )

    predictions = (
        st.session_state.get(
            "tasting_predictions",
            {},
        ).get(product_id)
    )

    reactions = _product_reactions(
        product_id
    )

    host_response = (
        st.session_state.get(
            "reaction_responses",
            {},
        ).get(product_id)
    )

    if not predictions:
        _show_prediction_form(
            product=product,
            profiles=profiles,
        )

    elif not reactions:
        _show_rating_form(
            product=product,
            profiles=profiles,
        )

    elif not host_response:
        error_message = (
            st.session_state.get(
                "ai_host_error"
            )
        )

        if error_message:
            st.error(error_message)

        if st.button(
            "Retry host reaction",
            type="primary",
            use_container_width=True,
        ):
            _retry_reaction_response(
                product=product,
                reactions=reactions,
            )

    else:
        _show_completed_product(
            product=product,
            total_products=len(products),
        )

    st.divider()

    if st.button(
        "Exit to flight overview",
        use_container_width=True,
    ):
        session_id = _analytics_session_id()

        if session_id:
            _safe_analytics_call(
                "log tasting exit",
                log_event,
                session_id=session_id,
                event_name="session_exited_to_flight_overview",
                product_id=product_id,
                event_data={
                    "current_position": product[
                        "position"
                    ],
                    "completed_products": current_index,
                },
            )

            _safe_analytics_call(
                "update exited session",
                update_session_status,
                session_id=session_id,
                status="exited",
            )

        _navigate_to("flight")


# ---------------------------------------------------------
# Results page
# ---------------------------------------------------------

def show_results_page() -> None:
    """Display ratings and the final AI-generated summary."""

    flight = st.session_state.get(
        "flight"
    )

    participant_mode = st.session_state.get(
        "participant_mode"
    )

    setup = st.session_state.get(
        "experience_setup"
    )

    profiles = st.session_state.get(
        "participant_profiles"
    )

    reactions = st.session_state.get(
        "tasting_reactions",
        [],
    )

    if (
        not flight
        or not participant_mode
        or not setup
        or not profiles
    ):
        _navigate_to("review")
        return

    expected_reactions = (
        len(flight["products"])
        * len(profiles)
    )

    if len(reactions) < expected_reactions:
        _navigate_to(
            "guided_tasting"
        )
        return

    session_id = _ensure_analytics_session(
        participant_mode=participant_mode,
        setup=setup,
        profiles=profiles,
        flight=flight,
    )

    if (
        session_id
        and not st.session_state.get(
            "analytics_session_completed"
        )
    ):
        completion_success, _ = (
            _safe_analytics_call(
                "complete tasting session",
                complete_session,
                session_id=session_id,
            )
        )

        if completion_success:
            st.session_state[
                "analytics_session_completed"
            ] = True

    st.title("Your TryFlight results")

    st.success(
        "You completed the tasting."
    )

    _show_analytics_warning()

    st.subheader("Ratings")

    for product in flight["products"]:
        product_reactions = [
            reaction
            for reaction in reactions
            if reaction["product_id"]
            == product["product_id"]
        ]

        average_rating = (
            sum(
                reaction["rating"]
                for reaction
                in product_reactions
            )
            / len(product_reactions)
        )

        with st.container(border=True):
            st.markdown(
                f"### {product['product_name']}"
            )

            st.write(
                f"**Average rating:** "
                f"{average_rating:.1f}/10"
            )

            for reaction in product_reactions:
                st.write(
                    f"**{reaction['participant_name']}:** "
                    f"{reaction['rating']}/10 "
                    f"(predicted "
                    f"{reaction['prediction']}/10)"
                )

                st.write(
                    "**Purchase intent:** "
                    f"{reaction['purchase_intent']}"
                )

                if reaction["reaction_words"]:
                    st.caption(
                        reaction[
                            "reaction_words"
                        ]
                    )

    st.divider()

    st.subheader(
        "Your host's closing take"
    )

    if not st.session_state.get(
        "final_summary"
    ):
        try:
            with st.spinner(
                "Building your final taste profile..."
            ):
                final_summary = generate_final_summary(
                    participant_mode=(
                        participant_mode
                    ),
                    setup=setup,
                    profiles=profiles,
                    products=flight[
                        "products"
                    ],
                    reactions=reactions,
                )

            st.session_state[
                "final_summary"
            ] = final_summary

            st.session_state.pop(
                "ai_host_error",
                None,
            )

            if session_id:
                _safe_analytics_call(
                    "save final summary",
                    save_host_message,
                    session_id=session_id,
                    message_type="final_summary",
                    content=final_summary,
                )

                _safe_analytics_call(
                    "log final summary",
                    log_event,
                    session_id=session_id,
                    event_name="final_summary_generated",
                    event_data={
                        "character_count": len(
                            final_summary
                        ),
                    },
                )

        except AIHostError as exc:
            st.session_state[
                "ai_host_error"
            ] = str(exc)

            if session_id:
                _safe_analytics_call(
                    "log final summary failure",
                    log_event,
                    session_id=session_id,
                    event_name="final_summary_failed",
                    event_data={
                        "error": str(exc),
                    },
                )

    final_summary = (
        st.session_state.get(
            "final_summary"
        )
    )

    if final_summary:
        st.info(final_summary)

    else:
        st.error(
            st.session_state.get(
                "ai_host_error",
                (
                    "The final summary could "
                    "not be generated."
                ),
            )
        )

        if st.button(
            "Retry final summary",
            use_container_width=True,
        ):
            st.session_state.pop(
                "final_summary",
                None,
            )

            st.session_state.pop(
                "ai_host_error",
                None,
            )

            st.rerun()

    st.divider()

    if session_id:
        with st.expander(
            "Test-session details"
        ):
            st.caption(
                "Analytics session ID"
            )
            st.code(session_id)

            st.caption(
                "This session is stored locally in "
                "data/tryflight_analytics.db."
            )

    overview_column, restart_column = (
        st.columns(2)
    )

    with overview_column:
        if st.button(
            "View flight overview",
            use_container_width=True,
        ):
            _navigate_to("flight")

    with restart_column:
        if st.button(
            "Start a new TryFlight",
            type="primary",
            use_container_width=True,
        ):
            for key in list(
                st.session_state.keys()
            ):
                del st.session_state[key]

            st.session_state[
                "page"
            ] = "participant_mode"

            st.rerun()