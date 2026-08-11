from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.models.stamp_catalog import stamp_image_url
from app.repositories.stampbook import StampbookRepository
from app.schemas.stampbook import StampbookFilter


class StampbookService:
    def __init__(self, repository: StampbookRepository) -> None:
        self.repository = repository

    async def get(
        self,
        user: LoginUser,
        status: StampbookFilter,
        *,
        page: int,
        size: int,
    ) -> dict:
        passport_id = await self.repository.passport_id(user.id)
        if passport_id is None:
            raise ApiError(404, "passport_not_found", "Passport not found.")

        summary, rows = await self.repository.stampbook(
            passport_id,
            status,
            offset=(page - 1) * size,
            limit=size,
        )
        items: dict[int, dict] = {}
        for row in rows:
            item = items.setdefault(
                row["catalog_id"],
                {
                    key: row[key]
                    for key in (
                        "catalog_id",
                        "stamp_id",
                        "region_ko",
                        "region_en",
                        "sport_ko",
                        "sport_en",
                        "color",
                        "status",
                        "collected_at",
                    )
                }
                | {"image_url": stamp_image_url(row["image_key"]), "courses": []},
            )
            if row["course_id"] is not None:
                item["courses"].append(
                    {"id": row["course_id"], "title": row["course_title"]}
                )

        total_items = summary[status.value] if status != StampbookFilter.all else summary["total"]
        return {
            "summary": summary,
            "page": page,
            "size": size,
            "total_items": total_items,
            "total_pages": (total_items + size - 1) // size,
            "items": list(items.values()),
        }


def get_stampbook_service(
    session: AsyncSession = Depends(get_session),
) -> StampbookService:
    return StampbookService(StampbookRepository(session))
