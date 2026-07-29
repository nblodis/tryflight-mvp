from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "tryflight_analytics.db"


# ---------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------

def _utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def _to_json(value: Any) -> str:
    """Convert a Python value into consistently formatted JSON."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


@contextmanager
def _database_connection() -> Iterator[sqlite3.Connection]:
    """Open a configured SQLite connection and manage transactions."""

    DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON;"
    )

    connection.execute(
        "PRAGMA journal_mode = WAL;"
    )

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ---------------------------------------------------------
# Database initialization
# ---------------------------------------------------------

def initialize_database() -> None:
    """Create all TryFlight analytics tables when absent."""

    with _database_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                participant_mode TEXT NOT NULL,
                occasion TEXT,
                mood TEXT,
                available_time TEXT,
                budget REAL,
                sample_count INTEGER,
                adventurousness INTEGER,
                estimated_total_cost REAL,
                model_name TEXT,
                setup_json TEXT NOT NULL,
                flight_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS participants (
                session_id TEXT NOT NULL,
                participant_index INTEGER NOT NULL,
                participant_name TEXT NOT NULL,
                profile_json TEXT NOT NULL,

                PRIMARY KEY (
                    session_id,
                    participant_index
                ),

                FOREIGN KEY (session_id)
                    REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS session_products (
                session_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                brand TEXT,
                is_wildcard INTEGER NOT NULL,
                recommendation_score REAL,
                estimated_cost REAL,
                product_json TEXT NOT NULL,

                PRIMARY KEY (
                    session_id,
                    product_id
                ),

                FOREIGN KEY (session_id)
                    REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS predictions (
                session_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                participant_name TEXT NOT NULL,
                prediction INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,

                PRIMARY KEY (
                    session_id,
                    product_id,
                    participant_name
                ),

                FOREIGN KEY (session_id)
                    REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reactions (
                session_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                participant_name TEXT NOT NULL,
                prediction INTEGER,
                rating INTEGER NOT NULL,
                reaction_words TEXT,
                purchase_intent TEXT,
                recorded_at TEXT NOT NULL,

                PRIMARY KEY (
                    session_id,
                    product_id,
                    participant_name
                ),

                FOREIGN KEY (session_id)
                    REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS host_messages (
                session_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                product_id TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,

                PRIMARY KEY (
                    session_id,
                    message_type,
                    product_id
                ),

                FOREIGN KEY (session_id)
                    REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_name TEXT NOT NULL,
                product_id TEXT,
                participant_name TEXT,
                event_data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,

                FOREIGN KEY (session_id)
                    REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS
                idx_events_session
            ON events (
                session_id,
                created_at
            );

            CREATE INDEX IF NOT EXISTS
                idx_reactions_product
            ON reactions (
                product_id
            );

            CREATE INDEX IF NOT EXISTS
                idx_sessions_status
            ON sessions (
                status
            );
            """
        )


# ---------------------------------------------------------
# Session creation
# ---------------------------------------------------------

def create_session(
    *,
    participant_mode: str,
    setup: dict[str, Any],
    profiles: list[dict[str, Any]],
    flight: dict[str, Any],
    model_name: str,
) -> str:
    """Create and persist a new guided tasting session."""

    initialize_database()

    session_id = str(uuid.uuid4())
    timestamp = _utc_now()

    products = flight.get(
        "products",
        [],
    )

    with _database_connection() as connection:
        connection.execute(
            """
            INSERT INTO sessions (
                session_id,
                created_at,
                started_at,
                completed_at,
                status,
                participant_mode,
                occasion,
                mood,
                available_time,
                budget,
                sample_count,
                adventurousness,
                estimated_total_cost,
                model_name,
                setup_json,
                flight_json
            )
            VALUES (
                ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            );
            """,
            (
                session_id,
                timestamp,
                timestamp,
                "in_progress",
                participant_mode,
                setup.get("occasion"),
                setup.get("mood"),
                setup.get("available_time"),
                setup.get("budget"),
                setup.get("sample_count"),
                setup.get("adventurousness"),
                flight.get("total_cost"),
                model_name,
                _to_json(setup),
                _to_json(flight),
            ),
        )

        for participant_index, profile in enumerate(
            profiles,
            start=1,
        ):
            connection.execute(
                """
                INSERT INTO participants (
                    session_id,
                    participant_index,
                    participant_name,
                    profile_json
                )
                VALUES (?, ?, ?, ?);
                """,
                (
                    session_id,
                    participant_index,
                    profile.get(
                        "participant_name",
                        f"Taster {participant_index}",
                    ),
                    _to_json(profile),
                ),
            )

        for product in products:
            connection.execute(
                """
                INSERT INTO session_products (
                    session_id,
                    product_id,
                    position,
                    product_name,
                    brand,
                    is_wildcard,
                    recommendation_score,
                    estimated_cost,
                    product_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    product["product_id"],
                    product["position"],
                    product["product_name"],
                    product.get("brand"),
                    int(
                        bool(
                            product.get(
                                "is_wildcard",
                                False,
                            )
                        )
                    ),
                    product.get("score"),
                    product.get("estimated_cost"),
                    _to_json(product),
                ),
            )

        connection.execute(
            """
            INSERT INTO events (
                session_id,
                event_name,
                product_id,
                participant_name,
                event_data_json,
                created_at
            )
            VALUES (?, ?, NULL, NULL, ?, ?);
            """,
            (
                session_id,
                "session_started",
                _to_json(
                    {
                        "participant_count": len(
                            profiles
                        ),
                        "product_count": len(
                            products
                        ),
                        "model_name": model_name,
                    }
                ),
                timestamp,
            ),
        )

    return session_id


# ---------------------------------------------------------
# Predictions and reactions
# ---------------------------------------------------------

def save_prediction(
    *,
    session_id: str,
    product_id: str,
    participant_name: str,
    prediction: int,
) -> None:
    """Insert or update one participant's product prediction."""

    initialize_database()

    timestamp = _utc_now()

    with _database_connection() as connection:
        connection.execute(
            """
            INSERT INTO predictions (
                session_id,
                product_id,
                participant_name,
                prediction,
                recorded_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT (
                session_id,
                product_id,
                participant_name
            )
            DO UPDATE SET
                prediction = excluded.prediction,
                recorded_at = excluded.recorded_at;
            """,
            (
                session_id,
                product_id,
                participant_name,
                int(prediction),
                timestamp,
            ),
        )


def save_reactions(
    *,
    session_id: str,
    reactions: list[dict[str, Any]],
) -> None:
    """Insert or update all reactions submitted for a product."""

    initialize_database()

    timestamp = _utc_now()

    with _database_connection() as connection:
        for reaction in reactions:
            connection.execute(
                """
                INSERT INTO reactions (
                    session_id,
                    product_id,
                    participant_name,
                    prediction,
                    rating,
                    reaction_words,
                    purchase_intent,
                    recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT (
                    session_id,
                    product_id,
                    participant_name
                )
                DO UPDATE SET
                    prediction = excluded.prediction,
                    rating = excluded.rating,
                    reaction_words = excluded.reaction_words,
                    purchase_intent = excluded.purchase_intent,
                    recorded_at = excluded.recorded_at;
                """,
                (
                    session_id,
                    reaction["product_id"],
                    reaction["participant_name"],
                    reaction.get("prediction"),
                    int(reaction["rating"]),
                    reaction.get("reaction_words"),
                    reaction.get("purchase_intent"),
                    timestamp,
                ),
            )


# ---------------------------------------------------------
# AI-host output
# ---------------------------------------------------------

def save_host_message(
    *,
    session_id: str,
    message_type: str,
    content: str,
    product_id: str | None = None,
) -> None:
    """Insert or update one generated host message."""

    initialize_database()

    timestamp = _utc_now()
    normalized_product_id = product_id or ""

    with _database_connection() as connection:
        connection.execute(
            """
            INSERT INTO host_messages (
                session_id,
                message_type,
                product_id,
                content,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT (
                session_id,
                message_type,
                product_id
            )
            DO UPDATE SET
                content = excluded.content,
                created_at = excluded.created_at;
            """,
            (
                session_id,
                message_type,
                normalized_product_id,
                content,
                timestamp,
            ),
        )


# ---------------------------------------------------------
# Behavioral event log
# ---------------------------------------------------------

def log_event(
    *,
    session_id: str,
    event_name: str,
    product_id: str | None = None,
    participant_name: str | None = None,
    event_data: dict[str, Any] | None = None,
) -> None:
    """Append one behavioral event to the event log."""

    initialize_database()

    with _database_connection() as connection:
        connection.execute(
            """
            INSERT INTO events (
                session_id,
                event_name,
                product_id,
                participant_name,
                event_data_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                session_id,
                event_name,
                product_id,
                participant_name,
                _to_json(event_data or {}),
                _utc_now(),
            ),
        )


# ---------------------------------------------------------
# Session status
# ---------------------------------------------------------

def update_session_status(
    *,
    session_id: str,
    status: str,
    mark_completed: bool = False,
) -> None:
    """Update the overall status of a guided tasting session."""

    initialize_database()

    completed_at = (
        _utc_now()
        if mark_completed
        else None
    )

    with _database_connection() as connection:
        if mark_completed:
            connection.execute(
                """
                UPDATE sessions
                SET
                    status = ?,
                    completed_at = ?
                WHERE session_id = ?;
                """,
                (
                    status,
                    completed_at,
                    session_id,
                ),
            )

        else:
            connection.execute(
                """
                UPDATE sessions
                SET status = ?
                WHERE session_id = ?;
                """,
                (
                    status,
                    session_id,
                ),
            )


def complete_session(
    *,
    session_id: str,
) -> None:
    """Mark a guided tasting session as completed."""

    update_session_status(
        session_id=session_id,
        status="completed",
        mark_completed=True,
    )

    log_event(
        session_id=session_id,
        event_name="session_completed",
    )


# ---------------------------------------------------------
# Verification and maintenance
# ---------------------------------------------------------

def get_database_path() -> Path:
    """Return the absolute analytics database path."""

    return DATABASE_PATH


def get_session_count() -> int:
    """Return the number of saved tasting sessions."""

    initialize_database()

    with _database_connection() as connection:
        result = connection.execute(
            """
            SELECT COUNT(*) AS session_count
            FROM sessions;
            """
        ).fetchone()

    return int(result["session_count"])


def delete_session(
    *,
    session_id: str,
) -> None:
    """Delete one session and its related test records."""

    initialize_database()

    with _database_connection() as connection:
        connection.execute(
            """
            DELETE FROM sessions
            WHERE session_id = ?;
            """,
            (session_id,),
        )