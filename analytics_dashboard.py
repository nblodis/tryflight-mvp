from __future__ import annotations

import hmac
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from analytics import get_database_path


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

POSITIVE_PURCHASE_INTENT = (
    "Probably yes",
    "Definitely yes",
)


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------

def _get_configured_password() -> str:
    """Load the private dashboard password."""

    load_dotenv(dotenv_path=ENV_PATH)

    environment_password = os.getenv(
        "ANALYTICS_PASSWORD",
        "",
    )

    streamlit_password = ""

    try:
        streamlit_password = str(
            st.secrets.get(
                "ANALYTICS_PASSWORD",
                "",
            )
        )
    except Exception:
        # Local development may not have a Streamlit secrets file.
        streamlit_password = ""

    return streamlit_password or environment_password


def _require_dashboard_authentication() -> bool:
    """Require the founder password before displaying analytics."""

    if st.session_state.get(
        "analytics_authenticated",
        False,
    ):
        return True

    configured_password = _get_configured_password()

    st.title("TryFlight Analytics")
    st.subheader("Founder access")

    if not configured_password:
        st.error(
            "No analytics password is configured."
        )

        st.write(
            "Add the following variable to your local `.env` file:"
        )

        st.code(
            "ANALYTICS_PASSWORD=your-private-password",
            language="text",
        )

        return False

    with st.form("analytics_login_form"):
        entered_password = st.text_input(
            "Dashboard password",
            type="password",
        )

        submitted = st.form_submit_button(
            "Open analytics",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        password_matches = hmac.compare_digest(
            entered_password,
            configured_password,
        )

        if password_matches:
            st.session_state[
                "analytics_authenticated"
            ] = True

            st.rerun()

        else:
            st.error("Incorrect password.")

    return False


# ---------------------------------------------------------
# Database helpers
# ---------------------------------------------------------

def _database_exists() -> bool:
    """Return whether the local analytics database exists."""

    return get_database_path().exists()


def _read_dataframe(
    query: str,
    parameters: tuple[Any, ...] = (),
) -> pd.DataFrame:
    """Run a query and return its result as a dataframe."""

    database_path = get_database_path()

    if not database_path.exists():
        return pd.DataFrame()

    with sqlite3.connect(database_path) as connection:
        return pd.read_sql_query(
            query,
            connection,
            params=parameters,
        )


def _read_one(
    query: str,
    parameters: tuple[Any, ...] = (),
) -> dict[str, Any]:
    """Run a query and return one row as a dictionary."""

    database_path = get_database_path()

    if not database_path.exists():
        return {}

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row

        result = connection.execute(
            query,
            parameters,
        ).fetchone()

    return dict(result) if result else {}


def _load_json(value: str | None) -> Any:
    """Safely parse a stored JSON value."""

    if not value:
        return {}

    try:
        return json.loads(value)

    except json.JSONDecodeError:
        return {
            "unparsed_value": value,
        }


def _format_percentage(
    value: float | int | None,
) -> str:
    """Format a nullable number as a percentage."""

    if value is None:
        return "—"

    return f"{float(value):.1f}%"


def _format_decimal(
    value: float | int | None,
    places: int = 1,
) -> str:
    """Format a nullable decimal value."""

    if value is None:
        return "—"

    return f"{float(value):.{places}f}"


# ---------------------------------------------------------
# Overview queries
# ---------------------------------------------------------

def _get_session_summary() -> dict[str, Any]:
    """Return overall session counts."""

    return _read_one(
        """
        SELECT
            COUNT(*) AS total_sessions,

            SUM(
                CASE
                    WHEN status = 'completed'
                    THEN 1
                    ELSE 0
                END
            ) AS completed_sessions,

            SUM(
                CASE
                    WHEN status = 'in_progress'
                    THEN 1
                    ELSE 0
                END
            ) AS in_progress_sessions,

            SUM(
                CASE
                    WHEN status = 'exited'
                    THEN 1
                    ELSE 0
                END
            ) AS exited_sessions,

            AVG(
                CASE
                    WHEN status = 'completed'
                    THEN 1.0
                    ELSE 0.0
                END
            ) * 100.0 AS completion_rate

        FROM sessions;
        """
    )


def _get_reaction_summary() -> dict[str, Any]:
    """Return rating and purchase-intent measures."""

    return _read_one(
        """
        SELECT
            COUNT(*) AS total_reactions,

            AVG(rating) AS average_rating,

            AVG(
                CASE
                    WHEN prediction IS NOT NULL
                    THEN ABS(rating - prediction)
                    ELSE NULL
                END
            ) AS average_prediction_error,

            AVG(
                CASE
                    WHEN purchase_intent IN (
                        'Probably yes',
                        'Definitely yes'
                    )
                    THEN 1.0
                    ELSE 0.0
                END
            ) * 100.0 AS positive_purchase_intent_rate

        FROM reactions;
        """
    )


def _get_participant_count() -> int:
    """Return the total number of saved participants."""

    result = _read_one(
        """
        SELECT COUNT(*) AS participant_count
        FROM participants;
        """
    )

    return int(
        result.get(
            "participant_count",
            0,
        )
        or 0
    )


# ---------------------------------------------------------
# Dashboard sections
# ---------------------------------------------------------

def _show_overview_tab() -> None:
    """Display high-level experiment measures."""

    session_summary = _get_session_summary()
    reaction_summary = _get_reaction_summary()

    total_sessions = int(
        session_summary.get(
            "total_sessions",
            0,
        )
        or 0
    )

    completed_sessions = int(
        session_summary.get(
            "completed_sessions",
            0,
        )
        or 0
    )

    completion_rate = session_summary.get(
        "completion_rate"
    )

    average_rating = reaction_summary.get(
        "average_rating"
    )

    prediction_error = reaction_summary.get(
        "average_prediction_error"
    )

    purchase_intent_rate = reaction_summary.get(
        "positive_purchase_intent_rate"
    )

    first_row = st.columns(3)

    with first_row[0]:
        st.metric(
            "Saved sessions",
            total_sessions,
            border=True,
        )

    with first_row[1]:
        st.metric(
            "Completed sessions",
            completed_sessions,
            border=True,
        )

    with first_row[2]:
        st.metric(
            "Completion rate",
            _format_percentage(
                completion_rate
            ),
            border=True,
        )

    second_row = st.columns(3)

    with second_row[0]:
        st.metric(
            "Participants",
            _get_participant_count(),
            border=True,
        )

    with second_row[1]:
        st.metric(
            "Average rating",
            (
                _format_decimal(
                    average_rating
                )
                + "/10"
                if average_rating is not None
                else "—"
            ),
            border=True,
        )

    with second_row[2]:
        st.metric(
            "Positive purchase intent",
            _format_percentage(
                purchase_intent_rate
            ),
            help=(
                "Percentage of reactions marked "
                "'Probably yes' or 'Definitely yes'."
            ),
            border=True,
        )

    st.caption(
        "Average prediction miss: "
        f"{_format_decimal(prediction_error)} points."
    )

    st.divider()

    status_data = _read_dataframe(
        """
        SELECT
            status,
            COUNT(*) AS sessions
        FROM sessions
        GROUP BY status
        ORDER BY sessions DESC;
        """
    )

    daily_data = _read_dataframe(
        """
        SELECT
            SUBSTR(created_at, 1, 10) AS session_date,
            COUNT(*) AS sessions,
            SUM(
                CASE
                    WHEN status = 'completed'
                    THEN 1
                    ELSE 0
                END
            ) AS completed_sessions
        FROM sessions
        GROUP BY SUBSTR(created_at, 1, 10)
        ORDER BY session_date;
        """
    )

    chart_column, trend_column = st.columns(2)

    with chart_column:
        st.subheader("Session status")

        if status_data.empty:
            st.info("No session-status data yet.")

        else:
            st.bar_chart(
                status_data.set_index("status")
            )

    with trend_column:
        st.subheader("Sessions by date")

        if daily_data.empty:
            st.info("No session trend data yet.")

        else:
            st.line_chart(
                daily_data.set_index(
                    "session_date"
                )[
                    [
                        "sessions",
                        "completed_sessions",
                    ]
                ]
            )

    st.divider()

    st.subheader("Recent sessions")

    recent_sessions = _read_dataframe(
        """
        SELECT
            SUBSTR(created_at, 1, 19) AS created_utc,
            SUBSTR(session_id, 1, 8) AS session,
            status,
            participant_mode,
            occasion,
            sample_count,
            ROUND(estimated_total_cost, 2)
                AS estimated_cost
        FROM sessions
        ORDER BY created_at DESC
        LIMIT 10;
        """
    )

    if recent_sessions.empty:
        st.info("No saved sessions yet.")

    else:
        st.dataframe(
            recent_sessions,
            width="stretch",
            hide_index=True,
        )


def _show_product_tab() -> None:
    """Display aggregated product performance."""

    st.subheader("Product performance")

    product_data = _read_dataframe(
        """
        SELECT
            sp.product_id,
            sp.product_name,
            sp.brand,

            MAX(sp.is_wildcard)
                AS used_as_wildcard,

            COUNT(r.rating)
                AS ratings,

            ROUND(
                AVG(r.rating),
                2
            ) AS average_rating,

            ROUND(
                AVG(
                    CASE
                        WHEN r.prediction IS NOT NULL
                        THEN ABS(
                            r.rating - r.prediction
                        )
                        ELSE NULL
                    END
                ),
                2
            ) AS average_prediction_error,

            ROUND(
                AVG(
                    CASE
                        WHEN r.purchase_intent IN (
                            'Probably yes',
                            'Definitely yes'
                        )
                        THEN 1.0
                        ELSE 0.0
                    END
                ) * 100.0,
                1
            ) AS positive_purchase_intent_pct

        FROM session_products AS sp

        LEFT JOIN reactions AS r
            ON r.session_id = sp.session_id
            AND r.product_id = sp.product_id

        GROUP BY
            sp.product_id,
            sp.product_name,
            sp.brand

        ORDER BY
            average_rating DESC,
            ratings DESC;
        """
    )

    if product_data.empty:
        st.info(
            "Complete a guided tasting to populate "
            "product-performance analytics."
        )
        return

    chart_data = (
        product_data.loc[
            product_data["ratings"] > 0,
            [
                "product_name",
                "average_rating",
            ],
        ]
        .set_index("product_name")
    )

    if not chart_data.empty:
        st.bar_chart(chart_data)

    st.dataframe(
        product_data,
        width="stretch",
        hide_index=True,
        column_config={
            "product_id": None,
            "used_as_wildcard": st.column_config.CheckboxColumn(
                "Wildcard"
            ),
            "average_rating": st.column_config.NumberColumn(
                "Average rating",
                format="%.2f",
            ),
            "average_prediction_error": (
                st.column_config.NumberColumn(
                    "Prediction miss",
                    format="%.2f",
                )
            ),
            "positive_purchase_intent_pct": (
                st.column_config.NumberColumn(
                    "Positive intent",
                    format="%.1f%%",
                )
            ),
        },
    )


def _get_session_table() -> pd.DataFrame:
    """Return one summarized row per session."""

    return _read_dataframe(
        """
        SELECT
            s.session_id,
            SUBSTR(s.created_at, 1, 19)
                AS created_utc,
            s.status,
            s.participant_mode,
            s.occasion,
            s.mood,
            s.sample_count,
            s.model_name,

            COUNT(
                DISTINCT p.participant_index
            ) AS participants,

            COUNT(
                DISTINCT sp.product_id
            ) AS products,

            COUNT(r.rating)
                AS submitted_reactions,

            ROUND(
                AVG(r.rating),
                2
            ) AS average_rating

        FROM sessions AS s

        LEFT JOIN participants AS p
            ON p.session_id = s.session_id

        LEFT JOIN session_products AS sp
            ON sp.session_id = s.session_id

        LEFT JOIN reactions AS r
            ON r.session_id = s.session_id

        GROUP BY s.session_id

        ORDER BY s.created_at DESC;
        """
    )


def _show_selected_session(
    session_id: str,
) -> None:
    """Display the details of one selected session."""

    session = _read_one(
        """
        SELECT *
        FROM sessions
        WHERE session_id = ?;
        """,
        (session_id,),
    )

    if not session:
        st.error("The selected session could not be found.")
        return

    st.divider()
    st.subheader("Selected session")

    status_column, mode_column, products_column = (
        st.columns(3)
    )

    with status_column:
        st.metric(
            "Status",
            session.get("status", "Unknown"),
            border=True,
        )

    with mode_column:
        st.metric(
            "Mode",
            session.get(
                "participant_mode",
                "Unknown",
            ),
            border=True,
        )

    with products_column:
        st.metric(
            "Products",
            session.get(
                "sample_count",
                0,
            ),
            border=True,
        )

    st.caption(f"Session ID: {session_id}")
    st.caption(
        f"Created at: {session.get('created_at')} UTC"
    )

    setup_tab, participant_tab, reaction_tab, host_tab = (
        st.tabs(
            [
                "Setup",
                "Participants",
                "Reactions",
                "Host messages",
            ]
        )
    )

    with setup_tab:
        st.json(
            _load_json(
                session.get("setup_json")
            )
        )

    with participant_tab:
        participant_data = _read_dataframe(
            """
            SELECT
                participant_index,
                participant_name,
                profile_json
            FROM participants
            WHERE session_id = ?
            ORDER BY participant_index;
            """,
            (session_id,),
        )

        if participant_data.empty:
            st.info("No participant records found.")

        else:
            for _, participant in (
                participant_data.iterrows()
            ):
                with st.expander(
                    str(
                        participant[
                            "participant_name"
                        ]
                    ),
                    expanded=True,
                ):
                    st.json(
                        _load_json(
                            participant[
                                "profile_json"
                            ]
                        )
                    )

    with reaction_tab:
        reaction_data = _read_dataframe(
            """
            SELECT
                sp.position,
                sp.product_name,
                r.participant_name,
                r.prediction,
                r.rating,
                r.rating - r.prediction
                    AS prediction_difference,
                r.reaction_words,
                r.purchase_intent,
                SUBSTR(r.recorded_at, 1, 19)
                    AS recorded_utc

            FROM reactions AS r

            INNER JOIN session_products AS sp
                ON sp.session_id = r.session_id
                AND sp.product_id = r.product_id

            WHERE r.session_id = ?

            ORDER BY
                sp.position,
                r.participant_name;
            """,
            (session_id,),
        )

        if reaction_data.empty:
            st.info(
                "No participant reactions were saved."
            )

        else:
            st.dataframe(
                reaction_data,
                width="stretch",
                hide_index=True,
            )

    with host_tab:
        host_data = _read_dataframe(
            """
            SELECT
                message_type,
                product_id,
                content,
                SUBSTR(created_at, 1, 19)
                    AS created_utc
            FROM host_messages
            WHERE session_id = ?
            ORDER BY created_at;
            """,
            (session_id,),
        )

        if host_data.empty:
            st.info("No host messages were saved.")

        else:
            for _, message in host_data.iterrows():
                message_title = str(
                    message["message_type"]
                ).replace("_", " ").title()

                with st.expander(message_title):
                    st.write(message["content"])

                    if message["product_id"]:
                        st.caption(
                            "Product ID: "
                            f"{message['product_id']}"
                        )


def _show_sessions_tab() -> None:
    """Display session-level records and drill-down."""

    st.subheader("Saved sessions")

    session_data = _get_session_table()

    if session_data.empty:
        st.info("No sessions have been saved.")
        return

    displayed_sessions = session_data.copy()

    displayed_sessions["session"] = (
        displayed_sessions[
            "session_id"
        ].str.slice(0, 8)
    )

    visible_columns = [
        "created_utc",
        "session",
        "status",
        "participant_mode",
        "occasion",
        "participants",
        "products",
        "submitted_reactions",
        "average_rating",
        "model_name",
    ]

    st.dataframe(
        displayed_sessions[visible_columns],
        width="stretch",
        hide_index=True,
    )

    st.download_button(
        "Download session summary CSV",
        data=displayed_sessions[
            visible_columns
        ].to_csv(index=False),
        file_name="tryflight_session_summary.csv",
        mime="text/csv",
        use_container_width=True,
    )

    session_options: dict[str, str] = {}

    for _, session in session_data.iterrows():
        label = (
            f"{session['created_utc']} · "
            f"{session['status']} · "
            f"{str(session['session_id'])[:8]}"
        )

        session_options[label] = str(
            session["session_id"]
        )

    selected_label = st.selectbox(
        "Inspect a specific session",
        options=list(session_options.keys()),
    )

    selected_session_id = session_options[
        selected_label
    ]

    _show_selected_session(
        selected_session_id
    )


def _show_events_tab() -> None:
    """Display the behavioral event log."""

    st.subheader("Behavioral events")

    event_names = _read_dataframe(
        """
        SELECT DISTINCT event_name
        FROM events
        ORDER BY event_name;
        """
    )

    event_filter_options = ["All events"]

    if not event_names.empty:
        event_filter_options.extend(
            event_names["event_name"].tolist()
        )

    selected_event = st.selectbox(
        "Event type",
        options=event_filter_options,
    )

    if selected_event == "All events":
        event_data = _read_dataframe(
            """
            SELECT
                event_id,
                SUBSTR(session_id, 1, 8)
                    AS session,
                event_name,
                product_id,
                participant_name,
                event_data_json,
                SUBSTR(created_at, 1, 19)
                    AS created_utc
            FROM events
            ORDER BY event_id DESC
            LIMIT 500;
            """
        )

    else:
        event_data = _read_dataframe(
            """
            SELECT
                event_id,
                SUBSTR(session_id, 1, 8)
                    AS session,
                event_name,
                product_id,
                participant_name,
                event_data_json,
                SUBSTR(created_at, 1, 19)
                    AS created_utc
            FROM events
            WHERE event_name = ?
            ORDER BY event_id DESC
            LIMIT 500;
            """,
            (selected_event,),
        )

    if event_data.empty:
        st.info("No behavioral events found.")

    else:
        st.dataframe(
            event_data,
            width="stretch",
            hide_index=True,
        )

        st.download_button(
            "Download filtered event log",
            data=event_data.to_csv(index=False),
            file_name="tryflight_event_log.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ---------------------------------------------------------
# Public dashboard entry point
# ---------------------------------------------------------

def show_analytics_dashboard() -> None:
    """Render the private TryFlight analytics dashboard."""

    if not _require_dashboard_authentication():
        return

    title_column, lock_column = st.columns(
        [4, 1]
    )

    with title_column:
        st.title("TryFlight Analytics")
        st.caption(
            "Local MVP experiment and session data"
        )

    with lock_column:
        if st.button(
            "Lock",
            use_container_width=True,
        ):
            st.session_state.pop(
                "analytics_authenticated",
                None,
            )

            st.rerun()

    if not _database_exists():
        st.info(
            "The analytics database has not been "
            "created yet."
        )
        return

    tab_overview, tab_products, tab_sessions, tab_events = (
        st.tabs(
            [
                "Overview",
                "Products",
                "Sessions",
                "Event log",
            ]
        )
    )

    with tab_overview:
        _show_overview_tab()

    with tab_products:
        _show_product_tab()

    with tab_sessions:
        _show_sessions_tab()

    with tab_events:
        _show_events_tab()