import pytest
import asyncio
import httpx

from app.jobs.baekdu_trails import STARTS, activity, parse_routes, sync


def test_start_coordinates_and_original_route():
    row = {"baekduId": "BAEK_34", "baekdusections": "화방재", "baekdusectione": "끝",
           "baekduvia": "화방재→중간→끝", "baekdudistance": "10km"}
    place = {"id": "604996321", "address_name": "강원특별자치도 태백시 혈동",
             "y": "37.12", "x": "128.89"}
    result = activity(row, place)
    assert result["latitude"] == 37.12
    assert result["sport_name"] == "hiking"
    assert result["source_metadata"]["upstream"] == row
    assert result["source_metadata"]["coordinate_type"] == "route_start"
    with pytest.raises(ValueError):
        activity(row, place | {"id": "wrong"})
    with pytest.raises(ValueError):
        activity(row, place | {"address_name": "경기도 태백시"})
    with pytest.raises(ValueError):
        activity(row | {"baekdusections": "미확인"}, place)


def test_error_and_partial_responses_fail_closed():
    with pytest.raises(ValueError):
        parse_routes(b"<response><resultCode>30</resultCode></response>")
    with pytest.raises(ValueError):
        parse_routes(b"<response><resultCode>00</resultCode><totalCount>2</totalCount></response>")
    assert parse_routes(b"<response><resultCode>00</resultCode><totalCount>1</totalCount><item><baekduId>X</baekduId></item></response>") == [{"baekduId": "X"}]


@pytest.mark.parametrize("missing_landmark", [False, True])
def test_sync_validates_every_start_before_writing(missing_landmark):
    writes = []

    class Repository:
        async def sync_source(self, source, items, timestamp):
            writes.append((source, items))
            return len(items)

    def respond(request):
        if "gettrailservice" in request.url.path:
            items = "".join(
                f"<item><baekduId>{key}</baekduId><baekdusections>{value[0]}</baekdusections>"
                f"<baekdusectione>끝</baekdusectione><baekduvia>{value[0]}→끝</baekduvia></item>"
                for key, value in STARTS.items())
            return httpx.Response(200, text=f"<response><resultCode>00</resultCode><totalCount>4</totalCount>{items}</response>")
        value = next(value for value in STARTS.values() if value[1] == request.url.params["query"])
        documents = [] if missing_landmark else [{"id": value[2], "x": "128.9", "y": "37.4",
                                                "address_name": f"강원특별자치도 {value[3]} 테스트"}]
        return httpx.Response(200, json={"documents": documents})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await sync(client, Repository(), "test", "test")

    if missing_landmark:
        with pytest.raises(ValueError):
            asyncio.run(run())
        assert not writes
    else:
        assert asyncio.run(run()) == 4
        assert writes[0][0] == "forest_baekdu"
        assert len({item["external_id"] for item in writes[0][1]}) == 4
