from dataclasses import dataclass
from typing import Any, Protocol

import boto3
from botocore.config import Config

from app.core.config import Settings


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    content_type: str | None
    checksum_sha256: str | None


class ObjectStorage(Protocol):
    def create_upload_authorization(
        self, object_key: str, content_type: str, expires_in: int
    ) -> str: ...

    def create_download_authorization(self, object_key: str, expires_in: int) -> str: ...

    def head_object(self, object_key: str) -> ObjectInfo: ...

    def delete_object(self, object_key: str) -> None: ...


class S3CompatibleStorage:
    def __init__(self, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3CompatibleStorage":
        if settings.object_storage_bucket is None:
            raise ValueError("OBJECT_STORAGE_BUCKET is required to configure artifact storage")
        client_options: dict[str, Any] = {
            "service_name": "s3",
            "region_name": settings.object_storage_region,
            "endpoint_url": settings.object_storage_endpoint_url,
            "config": Config(signature_version="s3v4"),
        }
        if settings.object_storage_access_key_id is not None:
            client_options["aws_access_key_id"] = (
                settings.object_storage_access_key_id.get_secret_value()
            )
        if settings.object_storage_secret_access_key is not None:
            client_options["aws_secret_access_key"] = (
                settings.object_storage_secret_access_key.get_secret_value()
            )
        return cls(settings.object_storage_bucket, boto3.client(**client_options))

    def create_upload_authorization(
        self, object_key: str, content_type: str, expires_in: int
    ) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )

    def create_download_authorization(self, object_key: str, expires_in: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_in,
            HttpMethod="GET",
        )

    def head_object(self, object_key: str) -> ObjectInfo:
        result = self.client.head_object(Bucket=self.bucket, Key=object_key)
        return ObjectInfo(
            size_bytes=result["ContentLength"],
            content_type=result.get("ContentType"),
            checksum_sha256=result.get("ChecksumSHA256"),
        )

    def delete_object(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)