"""Bounded read-only inspection of the subscribed hiking POI service."""
import asyncio
import json
import os
import xml.etree.ElementTree as ET

import httpx


async def main():
    key = os.getenv("DATA_GO_KR_SERVICE_KEY")
    if not key:
        print("ERROR: key not configured")
        return
    async with httpx.AsyncClient(timeout=40) as client:
        for mountain in ["100대명산 목록"]:
            try:
                response = await client.get(
                    "https://apis.data.go.kr/B553662/top100FamtListBasiInfoService/getTop100FamtListBasiInfoList",
                    params={"serviceKey": key, "type": "json", "numOfRows": 100,
                            "pageNo": 1},
                )
                try:
                    data = response.json()
                    body = data.get("response", {}).get("body", {})
                    items = body.get("items", {})
                    rows = items.get("item", []) if isinstance(items, dict) else []
                    if isinstance(rows, dict):
                        rows = [rows]
                    data = {"header": data.get("response", {}).get("header"),
                            "totalCount": body.get("totalCount"),
                            "sample": rows[:1],
                            "gangwon": [row for row in rows if "강원" in json.dumps(row, ensure_ascii=False)]}
                except ValueError:
                    root = ET.fromstring(response.text)
                    data = {name: root.findtext(".//" + name) for name in
                            ["returnReasonCode", "returnAuthMsg", "resultCode", "resultMsg"]}
                # Public POI data only; redact defensively if a provider echoes the key.
                print(json.dumps({"mountain": mountain, "status": response.status_code,
                                  "data": data}, ensure_ascii=False).replace(key, "[REDACTED]"))
            except Exception as exc:
                print(json.dumps({"mountain": mountain, "error_type": type(exc).__name__}))


asyncio.run(main())
