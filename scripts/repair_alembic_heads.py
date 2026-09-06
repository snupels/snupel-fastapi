import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import database_url


OVERLAPPING_REVISION_PAIRS = (
    ("0015_pyeongchang_olympic_museum_mission", "0016_feed_engagement"),
    ("0022_gangneung_olympic_museum_site", "0023_remove_kwandong_hockey_center"),
    ("0023_remove_kwandong_hockey_center", "0024_yundaechun_rafting_site"),
)


def redundant_revisions(revisions: set[str]) -> set[str]:
    redundant = set()
    for ancestor, descendant in OVERLAPPING_REVISION_PAIRS:
        ancestor_revision = next(
            (revision for revision in revisions if ancestor.startswith(revision)),
            None,
        )
        descendant_revision = next(
            (revision for revision in revisions if descendant.startswith(revision)),
            None,
        )
        if ancestor_revision and descendant_revision:
            redundant.add(ancestor_revision)
    return redundant


async def repair_overlapping_heads() -> None:
    engine = create_async_engine(database_url())
    try:
        async with engine.begin() as connection:
            has_version_table = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).has_table("alembic_version")
            )
            if not has_version_table:
                return

            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            revisions = {str(revision) for revision in result.scalars()}
            for revision in redundant_revisions(revisions):
                await connection.execute(
                    text("DELETE FROM alembic_version WHERE version_num = :revision"),
                    {"revision": revision},
                )
                print(f"Removed redundant Alembic revision: {revision}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(repair_overlapping_heads())
