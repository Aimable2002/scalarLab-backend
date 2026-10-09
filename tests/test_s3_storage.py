from app.adapters.storage.s3 import ObjectInfo, S3CompatibleStorage


class FakeS3Client:
    def __init__(self):
        self.presign_calls = []
        self.deleted = []

    def generate_presigned_url(self, operation, **kwargs):
        self.presign_calls.append((operation, kwargs))
        return "https://storage.example/signed"

    def head_object(self, **kwargs):
        return {
            "ContentLength": 4096,
            "ContentType": "application/octet-stream",
            "ChecksumSHA256": "abc123",
        }

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)


def test_s3_adapter_presigns_scoped_upload_and_download():
    client = FakeS3Client()
    storage = S3CompatibleStorage("scalar-artifacts", client)

    upload_url = storage.create_upload_authorization("workspaces/id/file", "application/zip", 300)
    download_url = storage.create_download_authorization("workspaces/id/file", 120)

    assert upload_url == "https://storage.example/signed"
    assert download_url == "https://storage.example/signed"
    assert client.presign_calls[0][0] == "put_object"
    assert client.presign_calls[0][1]["Params"] == {
        "Bucket": "scalar-artifacts",
        "Key": "workspaces/id/file",
        "ContentType": "application/zip",
    }
    assert client.presign_calls[1][0] == "get_object"


def test_s3_adapter_reads_metadata_and_deletes_objects():
    client = FakeS3Client()
    storage = S3CompatibleStorage("scalar-artifacts", client)

    info = storage.head_object("workspaces/id/file")
    storage.delete_object("workspaces/id/file")

    assert info == ObjectInfo(4096, "application/octet-stream", "abc123")
    assert client.deleted == [{"Bucket": "scalar-artifacts", "Key": "workspaces/id/file"}]