"""Classify the complementary purposes of recommended places."""

ROLE_LABELS = {"activity": "메인 체험", "meal": "식사", "sightseeing": "관광", "rest": "휴식"}


def role(activity):
    metadata = getattr(activity, "source_metadata", None) or {}
    content_type = str(metadata.get("contenttypeid") or "")
    name = str(getattr(activity, "place_name", "") or "")
    if content_type == "39":
        return "rest" if "카페" in name or "커피" in name or str(metadata.get("cat3")) == "A05020900" else "meal"
    category = getattr(activity.category, "value", activity.category)
    if category == "sports" or str(getattr(activity, "sport_name", "") or "").lower() in {
        "golf", "골프", "surfing", "marine", "ski", "rafting", "kayak", "skiing",
    }:
        return "activity"
    return "sightseeing"
