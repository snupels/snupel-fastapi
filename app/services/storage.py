import os
from uuid import uuid4

import boto3

from app.exceptions import ApiError

CONTENT_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOAD_EXPIRES_IN = 600


class ProofStorage:
    def __init__(self) -> None:
        self.bucket = os.getenv("S3_BUCKET", "")
        kwargs = {
            "region_name": os.getenv("S3_REGION", "ap-northeast-2"),
            "endpoint_url": os.getenv("S3_ENDPOINT_URL") or None,
            "aws_access_key_id": os.getenv("S3_ACCESS_KEY_ID") or None,
            "aws_secret_access_key": os.getenv("S3_SECRET_ACCESS_KEY") or None,
        }
        self.client = boto3.client("s3", **kwargs) if self.bucket else None

    def upload(self, passport_id: int, stamp_id: int, content_type: str) -> dict:
        extension = CONTENT_TYPES.get(content_type)
        if not extension:
            raise ApiError(400, "bad_request", "Only JPEG, PNG, and WebP images are allowed.")
        if not self.bucket:
            raise ApiError(503, "storage_unavailable", "Proof storage is not configured.")
        key = f"proofs/{passport_id}/{stamp_id}/{uuid4().hex}.{extension}"
        post = self.client.generate_presigned_post(
            self.bucket,
            key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, MAX_UPLOAD_BYTES],
            ],
            ExpiresIn=UPLOAD_EXPIRES_IN,
        )
        return {
            "upload_url": post["url"],
            "fields": post["fields"],
            "object_key": key,
            "expires_in": UPLOAD_EXPIRES_IN,
        }

    def proof_url(self, object_key: str) -> str | None:
        if not self.client:
            return None
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=UPLOAD_EXPIRES_IN,
        )


def get_proof_storage() -> ProofStorage:
    return ProofStorage()
