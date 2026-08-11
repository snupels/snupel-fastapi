import os
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError

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

    def validate(self, object_key: str) -> None:
        if not self.client:
            raise ApiError(503, "storage_unavailable", "Proof storage is not configured.")
        try:
            metadata = self.client.head_object(Bucket=self.bucket, Key=object_key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise ApiError(400, "bad_request", "Proof image was not uploaded.") from error
            raise ApiError(503, "storage_unavailable", "Proof storage is unavailable.") from error
        except BotoCoreError as error:
            raise ApiError(503, "storage_unavailable", "Proof storage is unavailable.") from error

        if (
            metadata.get("ContentType") not in CONTENT_TYPES
            or not 1 <= metadata.get("ContentLength", 0) <= MAX_UPLOAD_BYTES
        ):
            raise ApiError(400, "bad_request", "Invalid proof image.")


def get_proof_storage() -> ProofStorage:
    return ProofStorage()
