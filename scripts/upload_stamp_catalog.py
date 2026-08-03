"""Upload the supplied passport stamp SVGs to the configured S3 bucket."""

import argparse
import mimetypes
import os
from pathlib import Path
from zipfile import ZipFile

import boto3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    args = parser.parse_args()
    bucket = os.environ["S3_BUCKET"]
    client = boto3.client(
        "s3",
        region_name=os.getenv("S3_REGION", "ap-northeast-2"),
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY") or None,
    )
    with ZipFile(args.zip_path) as archive:
        for name in archive.namelist():
            if not name.endswith(".svg"):
                continue
            client.upload_fileobj(
                archive.open(name),
                bucket,
                f"stamps/{name}",
                ExtraArgs={"ContentType": mimetypes.guess_type(name)[0] or "image/svg+xml"},
            )


if __name__ == "__main__":
    main()
