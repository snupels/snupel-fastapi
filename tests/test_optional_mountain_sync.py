import asyncio
import httpx

from app.jobs.sync_tourism import MOUNTAIN_URL, TourismSync


def test_unavailable_mountain_source_preserves_records_and_continues():
    sources = []

    class Sync(TourismSync):
        async def _pages(self, url, params):
            if url == MOUNTAIN_URL:
                raise httpx.HTTPStatusError(
                    "unauthorized", request=httpx.Request("GET", "https://example.test"),
                    response=httpx.Response(401),
                )
            return [{"code": "32", "name": "강원"}] if url.endswith("/areaCode2") else []

        async def _file_rows(self, _url):
            return []

    class Repository:
        async def sync_source(self, source, *_):
            sources.append(source)
            return 0

        async def sports_dedup_candidates(self):
            return [], set()

        async def deactivate_activity_ids(self, _ids):
            return 0

    result = asyncio.run(Sync(None, Repository(), "key").run())
    assert result["mountain100_unavailable"] == 1
    assert "mountain100" not in sources
    assert "tourapi" in sources and "gangwon_marine" in sources
