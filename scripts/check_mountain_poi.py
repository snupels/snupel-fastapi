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
        for mountain in ["", "설악산", "오대산", "치악산", "태백산"]:
            try:
                response = await client.get(
                    "https://apis.data.go.kr/B553662/sceneryInfoService/getSceneryInfoList",
                    params={"serviceKey": key, "type": "json", "numOfRows": 5,
                            "pageNo": 1, "srchFrtrlNm": mountain},
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
                            "sample": rows}
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
