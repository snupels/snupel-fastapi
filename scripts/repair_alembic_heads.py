import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import database_url


ANCESTOR_REVISION = "0015_pyeongchang_olympic_museum_mission"
CURRENT_REVISION = "0016_feed_engagement"


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
            ancestor_revision = next(
                (revision for revision in revisions if ANCESTOR_REVISION.startswith(revision)),
                None,
            )
            current_revision = next(
                (revision for revision in revisions if CURRENT_REVISION.startswith(revision)),
                None,
            )
            if ancestor_revision and current_revision:
                await connection.execute(
                    text("DELETE FROM alembic_version WHERE version_num = :revision"),
                    {"revision": ancestor_revision},
                )
                print(f"Removed redundant Alembic revision: {ancestor_revision}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(repair_overlapping_heads())
