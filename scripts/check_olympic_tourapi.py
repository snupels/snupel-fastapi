"""Read-only, bounded TourAPI lookup; never logs keys, URLs or raw errors."""
import asyncio
import json
import os

import httpx


async def main():
    key = os.getenv("DATA_GO_KR_SERVICE_KEY")
    if not key:
        print("ERROR: service key is not configured")
        return
    keywords = ["2553644", "2525011"]
    async with httpx.AsyncClient(timeout=35) as client:
        for keyword in keywords:
            try:
                response = await client.get(
                    "https://apis.data.go.kr/B551011/KorService2/detailCommon2",
                    params={"serviceKey": key, "MobileOS": "ETC", "MobileApp": "Snupel",
                            "_type": "json", "contentId": keyword},
                )
                if response.status_code != 200:
                    print(json.dumps({"keyword": keyword, "http_status": response.status_code}))
                    continue
                payload = response.json().get("response", {})
                body = payload.get("body", {})
                items = body.get("items") or {}
                rows = items.get("item", []) if isinstance(items, dict) else []
                if isinstance(rows, dict):
                    rows = [rows]
                print(json.dumps({"keyword": keyword, "resultCode": payload.get("header", {}).get("resultCode"),
                                  "totalCount": body.get("totalCount"),
                                  "items": [{k: row.get(k) for k in ["contentid", "contenttypeid", "title", "addr1", "overview"]} for row in rows]}, ensure_ascii=False))
            except Exception as error:
                print(json.dumps({"keyword": keyword, "error_type": type(error).__name__}))


asyncio.run(main())
