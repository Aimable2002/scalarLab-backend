from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from app.adapters.datasets.download import ExternalDatasetDownloader
from app.modules.methods.forex_baseline import train_ohlcv_direction_baseline


def upload_artifact(upload_url: str, artifact_bytes: bytes) -> None:
    response = httpx.put(
        upload_url,
        content=artifact_bytes,
        headers={"Content-Type": "application/octet-stream"},
        timeout=120,
    )
    response.raise_for_status()


def execute_forex_baseline_job(
    payload: Mapping[str, Any],
    downloader: ExternalDatasetDownloader | None = None,
    artifact_uploader: Callable[[str, bytes], None] = upload_artifact,
) -> dict[str, Any]:
    dataset = payload["dataset"]
    artifact_upload_url = payload["artifact_upload_url"]
    artifact_id = payload["artifact_id"]
    dataset_downloader = downloader or ExternalDatasetDownloader()
    with dataset_downloader.download(
        dataset["provider"],
        dataset["source_id"],
        dataset["revision"],
        dataset["file_path"],
    ) as dataset_file:
        data = read_ohlcv_dataset(dataset_file)
        result = train_ohlcv_direction_baseline(data)
        artifact_uploader(artifact_upload_url, result.artifact_bytes)
        return {
            "artifact_id": artifact_id,
            "checksum_sha256": sha256(result.artifact_bytes).hexdigest(),
            "size_bytes": len(result.artifact_bytes),
            "metrics": result.metrics,
            "split_timestamp": result.split_timestamp,
        }


def read_ohlcv_dataset(dataset_file: Path) -> pd.DataFrame:
    suffix = dataset_file.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(dataset_file)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(dataset_file)
    raise ValueError("Forex baseline input must be a CSV or Parquet file")