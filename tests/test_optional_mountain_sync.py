import asyncio

from app.jobs.sync_tourism import TourismSync


def test_deprecated_mountain_source_is_deactivated_without_api_request():
    sources = []
    requested = []

    class Sync(TourismSync):
        async def _pages(self, url, params):
            requested.append(url)
            return [{"code": "32", "name": "강원"}] if url.endswith("/areaCode2") else []

        async def _file_rows(self, _url):
            return []

    class Repository:
        async def sync_source(self, source, items, _timestamp):
            sources.append((source, items))
            return 0

        async def sports_dedup_candidates(self):
            return [], set()

        async def deactivate_activity_ids(self, _ids):
            return 0

    result = asyncio.run(Sync(None, Repository(), "key").run())
    assert result["mountain100"] == 0
    assert ("mountain100", []) in sources
    assert {"tourapi", "gangwon_marine"}.issubset(source for source, _ in sources)
    assert all("top100Famt" not in url for url in requested)
