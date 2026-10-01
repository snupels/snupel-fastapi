import asyncio
from contextlib import asynccontextmanager

from app.jobs.sync_tourism import TourismSync


def test_deprecated_mountain_source_is_deactivated_without_api_request():
    sources = []
    requested = []

    class Sync(TourismSync):
        async def _pages(self, url, params):
            requested.append(url)
            if url.endswith("/areaCode2"):
                return [{"code": "32", "name": "강원"}]
            if url.endswith("/areaBasedSyncList2"):
                return [{"contentid": "1", "contenttypeid": "12", "title": "강원 관광지",
                         "addr1": "강원특별자치도 강릉시", "showflag": "1"}]
            return []

        async def _file_rows(self, _url):
            return [{"상호": "강원 해양 체험", "주소": "강원특별자치도 강릉시"}]

    class Repository:
        session = None

        @asynccontextmanager
        async def begin_nested(self):
            yield

        async def sync_state(self, _source):
            return None

        async def sync_source(self, source, items, _timestamp):
            sources.append((source, items))
            return 0

        async def record_sync(self, *_args, **_kwargs):
            pass

        async def record_sync_error(self, *_args):
            pass

        async def hide_upstream_ids(self, *_args):
            pass

        async def commit(self):
            pass

        async def sports_dedup_candidates(self):
            return [], set()

        async def deactivate_activity_ids(self, _ids):
            return 0

    repository = Repository()
    repository.session = repository
    result = asyncio.run(Sync(None, repository, "key").run())
    assert result["mountain100"] == 0
    assert ("mountain100", []) in sources
    assert {"tourapi", "gangwon_marine"}.issubset(source for source, _ in sources)
    assert all("top100Famt" not in url for url in requested)
