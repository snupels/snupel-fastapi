from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityCategory, Stamp, StampCatalog
from app.models.stamp_catalog import stamp_image_url

ACTIVITY_PREFIX = "stamp-catalog-"
SPORT_NAMES = {
    "MOUNTAIN": "hiking",
    "WATER": "water_sports",
    "SNOW": "ski",
    "OLYMPIC": "olympic_legacy",
    "ATHLETICS": "running",
}
REGION_SLUGS = {
    "CHUNCHEON": "chuncheon",
    "WONJU": "wonju",
    "GANGNEUNG": "gangneung",
    "DONGHAE": "donghae",
    "TAEBAEK": "taebaek",
    "SOKCHO": "sokcho",
    "SAMCHEOK": "samcheok",
    "HONGCHEON": "hongcheon",
    "HOENGSEONG": "hoengseong",
    "YEONGWOL": "yeongwol",
    "PYEONGCHANG": "pyeongchang",
    "JEONGSEON": "jeongseon",
    "CHEORWON": "cheorwon",
    "HWACHEON": "hwacheon",
    "YANGGU": "yanggu",
    "INJE": "inje",
    "GOSEONG": "goseong",
    "YANGYANG": "yangyang",
}
SPORT_SLUGS = {
    "MOUNTAIN": "mountain",
    "WATER": "water",
    "SNOW": "snow",
    "OLYMPIC": "olympic",
    "ATHLETICS": "athletics",
}
CITY_REGIONS = {"춘천", "원주", "강릉", "동해", "태백", "속초", "삼척"}


class StampRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def seed_catalog(self) -> dict[str, int]:
        catalogs = list(
            await self.session.scalars(select(StampCatalog).order_by(StampCatalog.id))
        )
        stamps = {
            row.stamp_catalog_id: row
            for row in await self.session.scalars(
                select(Stamp).where(Stamp.stamp_catalog_id.is_not(None))
            )
        }
        activities = {
            row.external_id: row
            for row in await self.session.scalars(
                select(Activity).where(Activity.external_id.like(f"{ACTIVITY_PREFIX}%"))
            )
        }
        created = 0
        for number, catalog in enumerate(catalogs, 1):
            image_key = (
                f"stamps/{number:02d}-{REGION_SLUGS[catalog.region_en]}-"
                f"{SPORT_SLUGS[catalog.sport_en]}.svg"
            )
            description = f"{catalog.region_ko} {catalog.sport_ko} 스탬프"
            catalog.image_key = image_key
            if stamp := stamps.get(catalog.id):
                stamp.description = description
                stamp.image_url = stamp_image_url(image_key)
                continue

            external_id = f"{ACTIVITY_PREFIX}{catalog.id}"
            activity = activities.get(external_id)
            if activity is None:
                activity = Activity(
                    category=ActivityCategory.sports,
                    sport_name=SPORT_NAMES[catalog.sport_en],
                    region="강원특별자치도",
                    sigun=f"{catalog.region_ko}{'시' if catalog.region_ko in CITY_REGIONS else '군'}",
                    place_name=description,
                    source=None,
                    external_id=external_id,
                    summary=f"{description} 미션",
                    is_active=True,
                )
                self.session.add(activity)
                await self.session.flush()
                activities[external_id] = activity
            self.session.add(
                Stamp(
                    activity_id=activity.id,
                    stamp_catalog_id=catalog.id,
                    description=description,
                    image_url=stamp_image_url(image_key),
                )
            )
            created += 1
        await self.session.flush()
        return {"created": created, "existing": len(catalogs) - created, "total": len(catalogs)}
