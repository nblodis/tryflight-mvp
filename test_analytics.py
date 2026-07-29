from analytics import (
    create_session,
    delete_session,
    get_database_path,
    get_session_count,
    save_host_message,
    save_prediction,
    save_reactions,
)


demo_setup = {
    "occasion": "Discover something new",
    "mood": "Curious",
    "available_time": "30 minutes",
    "budget": 20,
    "sample_count": 4,
    "adventurousness": 3,
}

demo_profiles = [
    {
        "participant_name": "Analytics Test",
        "flavor_likes": ["Chocolate"],
        "flavor_dislikes": [],
        "texture_likes": ["Crunchy"],
        "texture_dislikes": [],
        "familiarity_preference": 3,
        "restrictions": [],
        "other_dislikes": "",
    }
]

demo_flight = {
    "total_cost": 1.25,
    "products": [
        {
            "product_id": "test_product",
            "position": 1,
            "product_name": "Test Product",
            "brand": "TryFlight Test",
            "is_wildcard": False,
            "score": 10.0,
            "estimated_cost": 1.25,
            "flavor_tags": ["Chocolate"],
            "texture_tags": ["Crunchy"],
        }
    ],
}


before_count = get_session_count()

session_id = create_session(
    participant_mode="Just me",
    setup=demo_setup,
    profiles=demo_profiles,
    flight=demo_flight,
    model_name="gpt-5-mini",
)

save_prediction(
    session_id=session_id,
    product_id="test_product",
    participant_name="Analytics Test",
    prediction=7,
)

save_reactions(
    session_id=session_id,
    reactions=[
        {
            "product_id": "test_product",
            "participant_name": "Analytics Test",
            "prediction": 7,
            "rating": 8,
            "reaction_words": "Better than expected",
            "purchase_intent": "Probably yes",
        }
    ],
)

save_host_message(
    session_id=session_id,
    message_type="test_message",
    content="Analytics test successful.",
    product_id="test_product",
)

after_insert_count = get_session_count()

print(f"Database: {get_database_path()}")
print(f"Sessions before test: {before_count}")
print(f"Sessions after insert: {after_insert_count}")
print(f"Created session: {session_id}")

delete_session(
    session_id=session_id,
)

after_cleanup_count = get_session_count()

print(f"Sessions after cleanup: {after_cleanup_count}")

if after_cleanup_count != before_count:
    raise RuntimeError(
        "Analytics cleanup failed."
    )

print("Success: SQLite analytics are working.")