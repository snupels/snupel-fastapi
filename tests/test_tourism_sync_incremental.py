import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.jobs.sync_tourism import SEOUL, TourismSync
from app.repositories.activity import ActivityRepository
from app.repositories.course import CourseRepository
from app.repositories.me import MeRepository
from app.repositories.stamp_submission import StampSubmissionRepository
from app.repositories.stampbook import StampbookRepository


def test_changed_list_updates_visible_rows_and_hides_showflag_zero(monkeypatch):
    monkeypatch.delenv("KAKAO_CLIENT_ID", raising=False)
    captured = {}
    day = datetime.now(SEOUL).date() - timedelta(days=1)

    class Sync(TourismSync):
        async def _pages(self, url, params):
            if url.endswith("/areaCode2"):
                return [{"code": "32", "name": "강원"}]
            if url.endswith("/areaBasedSyncList2"):
                assert params["modifiedtime"] == day.strftime("%Y%m%d")
                return [
                    {"contentid": "visible", "contenttypeid": "12", "title": "강원 관광지",
                     "addr1": "강원특별자치도 강릉시", "showflag": "1"},
                    {"contentid": "hidden", "contenttypeid": "12", "title": "숨긴 장소",
                     "addr1": "강원특별자치도 강릉시", "showflag": "0"},
                ]
            return []

    class Repository:
        async def sync_changes(self, source, rows, _at):
            captured["source"], captured["rows"] = source, rows
            return len(rows)

        async def hide_upstream_ids(self, source, ids):
            captured["hidden"] = source, ids

    result = asyncio.run(Sync(None, Repository(), "key")._tourapi_day(
        day, full=False,
    ))
    assert result == 1
    assert captured["rows"][0]["external_id"] == "visible"
    assert captured["rows"][0]["upstream_visible"] is True
    assert captured["hidden"] == ("tourapi", {"hidden"})


def test_missed_dates_resume_after_failure(monkeypatch):
    monkeypatch.delenv("KAKAO_CLIENT_ID", raising=False)
    target = datetime.now(SEOUL).date() - timedelta(days=1)
    state = SimpleNamespace(last_success_date=target - timedelta(days=3))
    processed = []

    class Repository:
        session = None

        @asynccontextmanager
        async def begin_nested(self):
            yield

        async def sync_state(self, _source):
            return state

        async def record_sync(self, source, *, day, count):
            if source == "tourapi":
                state.last_success_date = day

        async def record_sync_error(self, *_args):
            pass

        async def commit(self):
            pass

        async def sports_dedup_candidates(self):
            return [], set()

        async def deactivate_activity_ids(self, _ids):
            return 0

    repository = Repository()
    repository.session = repository

    class Sync(TourismSync):
        fail = True

        async def _tourapi_day(self, day, *, full):
            assert not full
            processed.append(day)
            if self.fail and day == target - timedelta(days=1):
                raise ValueError("temporary failure")
            return 1

        async def _pages(self, _url, _params):
            return []

        async def _file_rows(self, _url):
            return []

    first = Sync(None, repository, "key")
    result = asyncio.run(first.run())
    assert result["tourapi_unavailable"] == 1
    assert state.last_success_date == target - timedelta(days=2)
    second = Sync(None, repository, "key")
    second.fail = False
    asyncio.run(second.run())
    assert processed == [target - timedelta(days=2), target - timedelta(days=1),
                         target - timedelta(days=1), target]
    assert state.last_success_date == target


def test_delta_upsert_preserves_unchanged_and_hidden_rows():
    changed = SimpleNamespace(external_id="changed", source_metadata={}, upstream_visible=False,
                              is_active=True)
    untouched = SimpleNamespace(external_id="untouched", source_metadata={},
                                upstream_visible=True, is_active=True)

    class Session:
        async def scalars(self, _query):
            return [changed, untouched]

        async def flush(self):
            pass

    repository = ActivityRepository(Session())
    asyncio.run(repository.sync_changes("tourapi", [{
        "external_id": "changed", "category": "event", "source_metadata": {},
    }], datetime(2026, 10, 1)))
    assert changed.upstream_visible is False
    assert untouched.is_active is True


def test_festival_refresh_does_not_override_previous_hide():
    class Sync(TourismSync):
        async def _pages(self, _url, _params):
            return [{"contentid": "event", "title": "행사", "contenttypeid": "15"}]

    rows = asyncio.run(Sync(None, None, "key")._festival_rows({}, "32", {}))
    assert "upstream_visible" not in rows[0]


def test_visibility_filters_keep_hidden_activities_out_of_queries():
    available = str(ActivityRepository._available())
    course = str(CourseRepository._visible_course())
    stampbook = str(StampbookRepository._catalog_status(1))
    assert "activities.upstream_visible IS true" in available
    assert "last_synced_at" not in available
    assert "activities.upstream_visible IS true" in course
    assert "activities.upstream_visible IS true" in stampbook

    class Result:
        def mappings(self):
            return self

        def all(self):
            return []

    class Session:
        statements = []

        async def execute(self, statement):
            self.statements.append(str(statement))
            return Result()

    session = Session()
    asyncio.run(MeRepository(session).saved_activities(1, offset=0, limit=20))
    asyncio.run(CourseRepository(session).itinerary(1))
    asyncio.run(StampSubmissionRepository(session).list_user(1))
    asyncio.run(StampSubmissionRepository(session).list_feed())
    assert len(session.statements) == 4
    assert all("activities.upstream_visible IS true" in sql for sql in session.statements)


def test_incomplete_api_page_is_rejected():
    class Sync(TourismSync):
        async def _get(self, _url, _params):
            return {"response": {"body": {"items": {"item": []}, "totalCount": 2}}}

    with pytest.raises(ValueError, match="Incomplete page"):
        asyncio.run(Sync(None, None, "key")._pages("https://example.test", {}))


def test_api_page_without_total_count_is_rejected():
    class Sync(TourismSync):
        async def _get(self, _url, _params):
            return {"response": {"body": {"items": {"item": [{"id": 1}]}}}}

    with pytest.raises(ValueError, match="Missing totalCount"):
        asyncio.run(Sync(None, None, "key")._pages("https://example.test", {}))
