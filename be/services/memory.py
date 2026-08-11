from __future__ import annotations

from schemas.pipeline import UserTravelMemory


def get_user_memory(
    user_id: str | None,
) -> UserTravelMemory:
    """
    Preserves the notebook's current placeholder behavior.

    TODO:
    Replace this with UserMemoryORM retrieval once your memory ranking/
    extraction strategy is finalized.
    """
    if not user_id:
        return UserTravelMemory()

    return UserTravelMemory(
        preferred_travel_styles=[
            "culture",
            "food",
        ],
        preferred_activities=[
            "sightseeing",
        ],
        budget_level="mid_range",
    )
