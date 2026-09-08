from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.exceptions import ApiError
from app.models import ActivityCategory
from app.repositories.activity import ActivityRepository
from app.services.base import CrudService


class ActivityService(CrudService):
    async def update(self, item_id: int, body, user=None):
        row = await self.get(item_id, user)
        category = body.category if "category" in body.model_fields_set else row.category
        sport_name = body.sport_name if "sport_name" in body.model_fields_set else row.sport_name
        if category == ActivityCategory.sports and not sport_name:
            raise ApiError(400, "bad_request", "sport_name is required for sports activities")
        if category != ActivityCategory.sports and sport_name is not None:
            raise ApiError(400, "bad_request", "sport_name is only allowed for sports activities")
        return await self.repository.update(row, body)

    async def explore(self, **filters):
        if filters.get("q"):
            filters["q"] = filters["q"].strip() or None
        rows = await self.repository.explore(**filters)
        items: dict[int, dict] = {}
        for activity, theme in rows:
            item = items.setdefault(
                activity.id,
                {
                    key: getattr(activity, key)
                    for key in (
                        "id",
                        "category",
                        "representative_image_url",
                        "sport_name",
                        "region",
                        "sigun",
                        "place_name",
                        "latitude",
                        "longitude",
                        "source",
                        "external_id",
                        "summary",
                        "address",
                        "source_url",
                        "starts_at",
                        "ends_at",
                        "source_metadata",
                        "last_synced_at",
                        "is_active",
                        "created_at",
                        "updated_at",
                    )
                }
                | {"themes": [], "has_mission": False},
            )
            if theme:
                value = theme.value if hasattr(theme, "value") else str(theme)
                if value not in item["themes"]:
                    item["themes"].append(value)
                item["has_mission"] = True
        return list(items.values())

    async def map_items(self, **filters):
        return await self.repository.map_items(**filters)


def get_activity_service(session: AsyncSession = Depends(get_session)) -> ActivityService:
    return ActivityService(ActivityRepository(session), "Activity")
