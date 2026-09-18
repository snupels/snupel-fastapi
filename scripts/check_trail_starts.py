import asyncio
import json
import os

import httpx


async def main():
    key = os.getenv("KAKAO_CLIENT_ID")
    if not key:
        print("ERROR: Kakao key not configured")
        return
    async with httpx.AsyncClient(timeout=20) as client:
        for name in ["화방재", "구부시령", "댓재", "고적대", "태백산 장바위"]:
            try:
                response = await client.get(
                    "https://dapi.kakao.com/v2/local/search/keyword.json",
                    params={"query": name}, headers={"Authorization": f"KakaoAK {key}"},
                )
                rows = response.json().get("documents", [])
                print(json.dumps({"query": name, "status": response.status_code,
                                  "places": [{k: row.get(k) for k in ["id", "place_name", "address_name", "x", "y", "place_url"]} for row in rows]}, ensure_ascii=False))
            except Exception as exc:
                print(type(exc).__name__)


asyncio.run(main())
