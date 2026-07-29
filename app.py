from pathlib import Path

import streamlit as st

from analytics_dashboard import show_analytics_dashboard
from guided_tasting import (
    show_guided_tasting_page,
    show_results_page,
    start_guided_tasting,
)
from recommendation import build_flight, load_catalog


# ---------------------------------------------------------
# Page configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="TryFlight",
    page_icon="✈️",
    layout="centered",
)


# ---------------------------------------------------------
# File paths and catalog loading
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
CATALOG_PATH = PROJECT_ROOT / "data" / "products.csv"


@st.cache_data(show_spinner=False)
def get_product_catalog():
    """Load and cache the structured product catalog."""
    return load_catalog(CATALOG_PATH)


# ---------------------------------------------------------
# Application state and navigation
# ---------------------------------------------------------

if "page" not in st.session_state:
    st.session_state["page"] = "participant_mode"


def navigate_to(page_name: str) -> None:
    """Navigate to another app screen."""
    st.session_state["page"] = page_name
    st.rerun()


def clear_state(*keys: str) -> None:
    """Remove selected values from Streamlit session state."""
    for key in keys:
        st.session_state.pop(key, None)


def start_over() -> None:
    """Clear the entire session and return to the first screen."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.session_state["page"] = "participant_mode"
    st.rerun()


def safe_option_index(
    options: list[str],
    selected_value: str,
    default_value: str,
) -> int:
    """Return a safe index for a Streamlit selection widget."""
    if selected_value in options:
        return options.index(selected_value)

    return options.index(default_value)


def show_founder_sidebar() -> None:
    """Display private founder navigation."""

    active_page = st.session_state.get(
        "page",
        "participant_mode",
    )

    with st.sidebar:
        st.caption("Founder tools")

        if active_page == "analytics":
            if st.button(
                "← Return to TryFlight",
                key="return_from_analytics",
                use_container_width=True,
            ):
                return_page = st.session_state.get(
                    "analytics_return_page",
                    "participant_mode",
                )

                st.session_state["page"] = return_page
                st.rerun()

        else:
            if st.button(
                "Analytics dashboard",
                key="open_analytics",
                use_container_width=True,
            ):
                st.session_state[
                    "analytics_return_page"
                ] = active_page

                st.session_state["page"] = "analytics"
                st.rerun()


# ---------------------------------------------------------
# Screen 1: Participant mode
# ---------------------------------------------------------

def show_participant_mode_page() -> None:
    """Display the participant-selection screen."""

    st.title("TryFlight")
    st.subheader("Discover what you like, one taste at a time.")

    st.write(
        "TryFlight creates a personalized tasting journey based on "
        "your preferences, occasion, and sense of adventure."
    )

    st.divider()

    st.header("Who is tasting?")

    participant_mode = st.radio(
        "Choose an experience mode:",
        options=[
            "Just me",
            "Two people",
        ],
        index=None,
        key="participant_mode_choice",
    )

    if participant_mode == "Just me":
        st.success("Solo tasting selected.")

        st.write(
            "You’ll receive a tasting flight designed around your "
            "individual preferences."
        )

    elif participant_mode == "Two people":
        st.success("Two-person tasting selected.")

        st.write(
            "Each person will create a profile so TryFlight can reveal "
            "agreements, surprises, and differences."
        )

    st.divider()

    if st.button(
        "Continue",
        type="primary",
        disabled=participant_mode is None,
        use_container_width=True,
    ):
        previous_mode = st.session_state.get("participant_mode")

        if previous_mode != participant_mode:
            clear_state(
                "experience_setup",
                "participant_profiles",
                "flight",
                "flight_error",
            )

        st.session_state["participant_mode"] = participant_mode
        navigate_to("experience_setup")


# ---------------------------------------------------------
# Screen 2: Experience setup
# ---------------------------------------------------------

def show_experience_setup_page() -> None:
    """Display the occasion and experience-setup screen."""

    participant_mode = st.session_state.get("participant_mode")

    if participant_mode is None:
        navigate_to("participant_mode")
        return

    st.title("Build your flight")
    st.caption(f"Experience mode: {participant_mode}")

    st.write(
        "Tell us what kind of tasting experience you want to create."
    )

    st.divider()

    existing_setup = st.session_state.get(
        "experience_setup",
        {},
    )

    occasion_options = [
        "Discover something new",
        "Taste with someone",
        "Relax and unwind",
        "Take a challenge",
        "Find a gift",
        "Build a custom flight",
    ]

    mood_options = [
        "Curious",
        "Playful",
        "Relaxed",
        "Adventurous",
        "Competitive",
        "Surprising",
    ]

    time_options = [
        "15 minutes",
        "30 minutes",
        "45 minutes",
        "60+ minutes",
    ]

    with st.form("experience_setup_form"):
        occasion = st.selectbox(
            "What kind of experience are you creating?",
            options=occasion_options,
            index=safe_option_index(
                options=occasion_options,
                selected_value=existing_setup.get(
                    "occasion",
                    "Discover something new",
                ),
                default_value="Discover something new",
            ),
        )

        mood = st.selectbox(
            "What mood are you going for?",
            options=mood_options,
            index=safe_option_index(
                options=mood_options,
                selected_value=existing_setup.get(
                    "mood",
                    "Curious",
                ),
                default_value="Curious",
            ),
        )

        available_time = st.select_slider(
            "How much time do you have?",
            options=time_options,
            value=existing_setup.get(
                "available_time",
                "30 minutes",
            ),
        )

        budget = st.slider(
            "Approximate product budget",
            min_value=5,
            max_value=50,
            value=int(existing_setup.get("budget", 20)),
            step=5,
            format="$%d",
        )

        sample_count = st.slider(
            "How many products would you like to taste?",
            min_value=4,
            max_value=8,
            value=int(
                existing_setup.get(
                    "sample_count",
                    6,
                )
            ),
        )

        adventurousness = st.slider(
            "How adventurous should the flight be?",
            min_value=1,
            max_value=5,
            value=int(
                existing_setup.get(
                    "adventurousness",
                    3,
                )
            ),
        )

        st.caption(
            "1 = Keep it familiar · 5 = Surprise me"
        )

        setup_submitted = st.form_submit_button(
            "Continue to preferences",
            type="primary",
            use_container_width=True,
        )

    if setup_submitted:
        new_setup = {
            "occasion": occasion,
            "mood": mood,
            "available_time": available_time,
            "budget": budget,
            "sample_count": sample_count,
            "adventurousness": adventurousness,
        }

        if new_setup != existing_setup:
            clear_state(
                "participant_profiles",
                "flight",
                "flight_error",
            )

        st.session_state["experience_setup"] = new_setup
        navigate_to("preference_intake")

    st.divider()

    if st.button(
        "← Back",
        use_container_width=True,
    ):
        navigate_to("participant_mode")


# ---------------------------------------------------------
# Shared preference controls
# ---------------------------------------------------------

def normalize_restrictions(
    restrictions: list[str],
) -> list[str]:
    """Remove 'None' when another restriction is selected."""

    if len(restrictions) > 1 and "None" in restrictions:
        return [
            restriction
            for restriction in restrictions
            if restriction != "None"
        ]

    return restrictions


def collect_preference_fields(
    key_prefix: str,
    heading: str,
) -> dict:
    """Display and collect preference controls for one participant."""

    st.markdown(f"### {heading}")

    flavor_options = [
        "Chocolate",
        "Caramel",
        "Vanilla",
        "Peanut or nutty",
        "Fruit",
        "Berry",
        "Citrus",
        "Mint",
        "Coffee",
        "Cinnamon",
        "Sweet",
        "Sour",
        "Salty",
        "Spicy",
    ]

    texture_options = [
        "Crunchy",
        "Crispy",
        "Chewy",
        "Gummy",
        "Creamy",
        "Soft",
        "Hard candy",
        "Filled",
    ]

    restriction_options = [
        "None",
        "Peanuts",
        "Tree nuts",
        "Milk or dairy",
        "Soy",
        "Wheat or gluten",
        "Egg",
        "Sesame",
        "Gelatin",
        "Other",
    ]

    flavor_likes = st.multiselect(
        "Which flavors usually sound good?",
        options=flavor_options,
        key=f"{key_prefix}_flavor_likes",
    )

    flavor_dislikes = st.multiselect(
        "Which flavors would you rather avoid?",
        options=flavor_options,
        key=f"{key_prefix}_flavor_dislikes",
    )

    texture_likes = st.multiselect(
        "Which textures do you enjoy?",
        options=texture_options,
        key=f"{key_prefix}_texture_likes",
    )

    texture_dislikes = st.multiselect(
        "Which textures do you dislike?",
        options=texture_options,
        key=f"{key_prefix}_texture_dislikes",
    )

    familiarity_preference = st.slider(
        "How familiar should the products feel?",
        min_value=1,
        max_value=5,
        value=3,
        key=f"{key_prefix}_familiarity",
    )

    st.caption(
        "1 = Mostly new and unusual · "
        "5 = Mostly familiar favorites"
    )

    restrictions = st.multiselect(
        "Allergies or dietary restrictions",
        options=restriction_options,
        key=f"{key_prefix}_restrictions",
    )

    other_dislikes = st.text_area(
        "Anything else you strongly dislike?",
        placeholder=(
            "Examples: coconut, artificial banana flavor, "
            "or extremely sour products."
        ),
        key=f"{key_prefix}_other_dislikes",
    )

    return {
        "flavor_likes": flavor_likes,
        "flavor_dislikes": flavor_dislikes,
        "texture_likes": texture_likes,
        "texture_dislikes": texture_dislikes,
        "familiarity_preference": familiarity_preference,
        "restrictions": normalize_restrictions(
            restrictions
        ),
        "other_dislikes": other_dislikes.strip(),
    }


# ---------------------------------------------------------
# Screen 3: Preference intake
# ---------------------------------------------------------

def show_preference_intake_page() -> None:
    """Display participant preference controls."""

    participant_mode = st.session_state.get(
        "participant_mode"
    )

    experience_setup = st.session_state.get(
        "experience_setup"
    )

    if participant_mode is None:
        navigate_to("participant_mode")
        return

    if experience_setup is None:
        navigate_to("experience_setup")
        return

    st.title("Tell us what you like")

    st.write(
        "Your answers will shape the products, sequence, and wildcard "
        "included in your flight."
    )

    st.warning(
        "TryFlight does not determine whether a product is medically "
        "safe. Always review the physical package and allergen label "
        "before consuming any product."
    )

    st.divider()

    with st.form("preference_intake_form"):
        if participant_mode == "Just me":
            participant_name = st.text_input(
                "What should we call you?",
                value="Taster",
                key="solo_participant_name",
            )

            solo_preferences = collect_preference_fields(
                key_prefix="solo",
                heading="Your preferences",
            )

            profiles = [
                {
                    "participant_name": (
                        participant_name.strip()
                        or "Taster"
                    ),
                    **solo_preferences,
                }
            ]

        else:
            name_column_1, name_column_2 = st.columns(2)

            with name_column_1:
                participant_one_name = st.text_input(
                    "First participant",
                    value="Taster 1",
                    key="participant_one_name",
                )

            with name_column_2:
                participant_two_name = st.text_input(
                    "Second participant",
                    value="Taster 2",
                    key="participant_two_name",
                )

            st.divider()

            participant_one_preferences = (
                collect_preference_fields(
                    key_prefix="participant_one",
                    heading="Participant 1 preferences",
                )
            )

            st.divider()

            participant_two_preferences = (
                collect_preference_fields(
                    key_prefix="participant_two",
                    heading="Participant 2 preferences",
                )
            )

            profiles = [
                {
                    "participant_name": (
                        participant_one_name.strip()
                        or "Taster 1"
                    ),
                    **participant_one_preferences,
                },
                {
                    "participant_name": (
                        participant_two_name.strip()
                        or "Taster 2"
                    ),
                    **participant_two_preferences,
                },
            ]

        preferences_submitted = st.form_submit_button(
            "Review my flight setup",
            type="primary",
            use_container_width=True,
        )

    if preferences_submitted:
        previous_profiles = st.session_state.get(
            "participant_profiles"
        )

        if profiles != previous_profiles:
            clear_state(
                "flight",
                "flight_error",
            )

        st.session_state["participant_profiles"] = profiles
        navigate_to("review")

    st.divider()

    if st.button(
        "← Back to experience setup",
        use_container_width=True,
    ):
        navigate_to("experience_setup")


# ---------------------------------------------------------
# Review helpers
# ---------------------------------------------------------

def display_list(
    label: str,
    values: list[str],
) -> None:
    """Display a readable list with an empty state."""

    readable_values = (
        ", ".join(values)
        if values
        else "No preference selected"
    )

    st.write(f"**{label}:** {readable_values}")


# ---------------------------------------------------------
# Screen 4: Review
# ---------------------------------------------------------

def show_review_page() -> None:
    """Display the completed setup before generating a flight."""

    participant_mode = st.session_state.get(
        "participant_mode"
    )

    setup = st.session_state.get(
        "experience_setup"
    )

    profiles = st.session_state.get(
        "participant_profiles"
    )

    if participant_mode is None:
        navigate_to("participant_mode")
        return

    if setup is None:
        navigate_to("experience_setup")
        return

    if profiles is None:
        navigate_to("preference_intake")
        return

    st.title("Your TryFlight setup")

    st.success("Your preferences have been saved.")

    st.subheader("Experience")

    experience_column_1, experience_column_2 = (
        st.columns(2)
    )

    with experience_column_1:
        st.write(f"**Mode:** {participant_mode}")
        st.write(f"**Occasion:** {setup['occasion']}")
        st.write(f"**Mood:** {setup['mood']}")

    with experience_column_2:
        st.write(
            f"**Time:** {setup['available_time']}"
        )
        st.write(f"**Budget:** ${setup['budget']}")
        st.write(
            f"**Products:** {setup['sample_count']}"
        )
        st.write(
            "**Adventurousness:** "
            f"{setup['adventurousness']} of 5"
        )

    st.divider()

    st.subheader("Taste profiles")

    for profile in profiles:
        with st.expander(
            profile["participant_name"],
            expanded=True,
        ):
            display_list(
                "Flavor likes",
                profile["flavor_likes"],
            )

            display_list(
                "Flavor dislikes",
                profile["flavor_dislikes"],
            )

            display_list(
                "Texture likes",
                profile["texture_likes"],
            )

            display_list(
                "Texture dislikes",
                profile["texture_dislikes"],
            )

            display_list(
                "Restrictions",
                profile["restrictions"],
            )

            st.write(
                "**Familiarity preference:** "
                f"{profile['familiarity_preference']} of 5"
            )

            other_dislikes = (
                profile["other_dislikes"]
                or "Nothing additional entered"
            )

            st.write(
                f"**Other dislikes:** {other_dislikes}"
            )

    st.warning(
        "Product eligibility is controlled by structured catalog "
        "data and deterministic rules—not by an AI guess."
    )

    st.divider()

    back_column, create_column = st.columns(2)

    with back_column:
        if st.button(
            "← Edit preferences",
            use_container_width=True,
        ):
            navigate_to("preference_intake")

    with create_column:
        create_clicked = st.button(
            "Create my flight",
            type="primary",
            use_container_width=True,
        )

    if create_clicked:
        try:
            with st.spinner(
                "Building your personalized flight..."
            ):
                catalog = get_product_catalog()

                flight = build_flight(
                    catalog=catalog,
                    setup=setup,
                    profiles=profiles,
                )

            st.session_state["flight"] = flight
            clear_state("flight_error")
            navigate_to("flight")

        except (
            FileNotFoundError,
            ValueError,
        ) as exc:
            st.session_state["flight_error"] = str(exc)
            clear_state("flight")

    flight_error = st.session_state.get(
        "flight_error"
    )

    if flight_error:
        st.error(flight_error)


# ---------------------------------------------------------
# Screen 5: Generated flight
# ---------------------------------------------------------

def show_flight_page() -> None:
    """Display the generated and sequenced tasting flight."""

    flight = st.session_state.get("flight")

    if flight is None:
        navigate_to("review")
        return

    st.title("Your TryFlight")

    products = flight["products"]

    st.success(
        f"We created a {len(products)}-product flight "
        f"with an estimated tasting cost of "
        f"${flight['total_cost']:.2f}."
    )

    st.warning(flight["catalog_warning"])

    st.write(
        "Taste the products in the order shown below. "
        "The sequence begins with approachable options and builds "
        "toward stronger or more surprising experiences."
    )

    st.divider()

    for product in products:
        wildcard_label = (
            " · Wildcard"
            if product["is_wildcard"]
            else ""
        )

        with st.container(border=True):
            st.markdown(
                f"### {product['position']}. "
                f"{product['product_name']}"
                f"{wildcard_label}"
            )

            st.caption(product["brand"])

            st.write(product["story"])

            st.write(
                "**Flavor:** "
                + ", ".join(
                    product["flavor_tags"]
                )
            )

            st.write(
                "**Texture:** "
                + ", ".join(
                    product["texture_tags"]
                )
            )

            st.write(
                "**Why it fits:** "
                + "; ".join(
                    product["reasons"]
                )
            )

            st.write(
                "**Estimated tasting cost:** "
                f"${product['estimated_cost']:.2f}"
            )

    st.divider()

    if st.button(
        "Start guided tasting",
        type="primary",
        use_container_width=True,
    ):
        start_guided_tasting()

    st.divider()

    edit_column, restart_column = st.columns(2)

    with edit_column:
        if st.button(
            "← Edit my setup",
            use_container_width=True,
        ):
            navigate_to("review")

    with restart_column:
        if st.button(
            "Start over",
            use_container_width=True,
        ):
            start_over()


# ---------------------------------------------------------
# Founder sidebar
# ---------------------------------------------------------

show_founder_sidebar()


# ---------------------------------------------------------
# Page router
# ---------------------------------------------------------

current_page = st.session_state["page"]

if current_page == "participant_mode":
    show_participant_mode_page()

elif current_page == "experience_setup":
    show_experience_setup_page()

elif current_page == "preference_intake":
    show_preference_intake_page()

elif current_page == "review":
    show_review_page()

elif current_page == "flight":
    show_flight_page()

elif current_page == "guided_tasting":
    show_guided_tasting_page()

elif current_page == "results":
    show_results_page()

elif current_page == "analytics":
    show_analytics_dashboard()

else:
    st.session_state["page"] = "participant_mode"
    st.rerun()