"""Read-only bounded lookup; never log credentials or request URLs."""
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
        for keyword in ["설악산", "오대산", "태백산"]:
            try:
                response = await client.get(
                    "https://apis.data.go.kr/1400000/trailInfoService/gettrailservice",
                    params={"serviceKey": key, "numOfRows": 100, "pageNo": 1,
                            "searchWrd": keyword},
                )
                root = ET.fromstring(response.text)
                fields = ["baekduId", "baekdugbn", "baekdugbnname", "baekdusections",
                          "baekdusectione", "baekduvia", "baekdudistance", "baekdurealdistance",
                          "baekduspect", "mntloca", "mntname", "mntnnm", "mntnfile"]
                result = {name: root.findtext(".//" + name) for name in
                          ["resultCode", "resultMsg", "totalCount", "returnReasonCode", "returnAuthMsg"]}
                result["items"] = [{name: row.findtext(name) for name in fields}
                                   for row in root.findall(".//item")]
                print(json.dumps({"keyword": keyword, "http_status": response.status_code,
                                  "result": result}, ensure_ascii=False).replace(key, "[REDACTED]"))
            except Exception as exc:
                print(json.dumps({"keyword": keyword, "error_type": type(exc).__name__}))


asyncio.run(main())
