from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.activity import ActivityRepository
from app.services.base import CrudService


class ActivityService(CrudService):
    async def explore(self, **filters):
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
