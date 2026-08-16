"""
Lightweight category filter to avoid unnecessary transcript and Gemini calls.
"""

from dataclasses import dataclass

NON_EDUCATIONAL = {
    "10": "Music",
    "17": "Sports",
    "23": "Comedy",
}


@dataclass
class CategoryDecision:
    allowed: bool
    category_name: str


def should_analyze(category_id: str) -> CategoryDecision:
    """
    Decide whether WatchWise should analyze this video.
    """

    if category_id in NON_EDUCATIONAL:
        return CategoryDecision(
            allowed=False,
            category_name=NON_EDUCATIONAL[category_id],
        )

    return CategoryDecision(
        allowed=True,
        category_name="Educational/Other",
    )