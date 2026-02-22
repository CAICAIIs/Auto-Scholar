import json
import os
from pathlib import Path

from backend.evaluation.schemas import HumanRating, HumanRatingSummary

RATINGS_FILE = Path(os.environ.get("RATINGS_FILE", "data/ratings.json"))


def _ensure_data_dir() -> None:
    RATINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not RATINGS_FILE.exists():
        RATINGS_FILE.write_text("[]")


def _load_ratings() -> list[dict]:
    _ensure_data_dir()
    try:
        return json.loads(RATINGS_FILE.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_ratings(ratings: list[dict]) -> None:
    _ensure_data_dir()
    RATINGS_FILE.write_text(json.dumps(ratings, indent=2, default=str))


def save_rating(rating: HumanRating) -> None:
    ratings = _load_ratings()
    ratings.append(rating.model_dump(mode="json"))
    _save_ratings(ratings)


def get_ratings_for_thread(thread_id: str) -> list[HumanRating]:
    ratings = _load_ratings()
    return [HumanRating.model_validate(r) for r in ratings if r.get("thread_id") == thread_id]


def get_rating_summary(thread_id: str) -> HumanRatingSummary | None:
    ratings = get_ratings_for_thread(thread_id)
    if not ratings:
        return None

    count = len(ratings)
    return HumanRatingSummary(
        thread_id=thread_id,
        rating_count=count,
        avg_overall=sum(r.overall_quality for r in ratings) / count,
        avg_accuracy=sum(r.factual_accuracy for r in ratings) / count,
        avg_coherence=sum(r.coherence for r in ratings) / count,
        avg_completeness=sum(r.completeness for r in ratings) / count,
        avg_writing=sum(r.writing_quality for r in ratings) / count,
    )


def get_all_ratings() -> list[HumanRating]:
    ratings = _load_ratings()
    return [HumanRating.model_validate(r) for r in ratings]
