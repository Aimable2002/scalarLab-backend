from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.adapters.datasets.download import ExternalDatasetDownloader
from app.modules.methods.forex_job import execute_forex_baseline_job


def make_ohlcv(rows=240):
    changes = np.resize(np.array([0.3, -0.2, 0.45, -0.15]), rows)
    close = 100 + np.cumsum(changes)
    previous_close = np.concatenate(([close[0]], close[:-1]))
    open_price = (close + previous_close) / 2
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=rows, freq="h"),
            "open": open_price,
            "high": np.maximum(open_price, close) + 0.1,
            "low": np.minimum(open_price, close) - 0.1,
            "close": close,
        }
    )


def make_ohlcv_csv(path: Path, rows=240):
    make_ohlcv(rows).to_csv(path, index=False)


def test_forex_job_downloads_trains_uploads_and_reports_artifact(tmp_path):
    captured_uploads = []
    temporary_paths = []

    def fake_hf_download(**kwargs):
        target = Path(kwargs["local_dir"]) / kwargs["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        make_ohlcv_csv(target)
        temporary_paths.append(target)
        return str(target)

    def capture_upload(upload_url, artifact_bytes):
        captured_uploads.append((upload_url, artifact_bytes))

    downloader = ExternalDatasetDownloader(huggingface_download=fake_hf_download)
    result = execute_forex_baseline_job(
        {
            "dataset": {
                "provider": "huggingface",
                "source_id": "owner/forex",
                "revision": "a" * 40,
                "file_path": "bars.csv",
            },
            "artifact_id": "artifact-123",
            "artifact_upload_url": "https://storage.example/signed",
        },
        downloader=downloader,
        artifact_uploader=capture_upload,
    )

    assert result["artifact_id"] == "artifact-123"
    assert result["metrics"]["train_rows"] > result["metrics"]["test_rows"]
    assert result["size_bytes"] == len(captured_uploads[0][1])
    assert captured_uploads[0][0] == "https://storage.example/signed"
    assert captured_uploads[0][1]
    assert not temporary_paths[0].exists()


def test_forex_job_rejects_unsupported_dataset_format(tmp_path):
    def fake_hf_download(**kwargs):
        target = Path(kwargs["local_dir"]) / kwargs["filename"]
        target.write_text("data", encoding="utf-8")
        return str(target)

    downloader = ExternalDatasetDownloader(huggingface_download=fake_hf_download)
    with pytest.raises(ValueError, match="CSV or Parquet"):
        execute_forex_baseline_job(
            {
                "dataset": {
                    "provider": "huggingface",
                    "source_id": "owner/forex",
                    "revision": "a" * 40,
                    "file_path": "bars.json",
                },
                "artifact_id": "artifact-123",
                "artifact_upload_url": "https://storage.example/signed",
            },
            downloader=downloader,
            artifact_uploader=lambda upload_url, artifact: None,
        )


def test_forex_job_reads_parquet_from_temporary_storage():
    uploaded = []

    def fake_hf_download(**kwargs):
        target = Path(kwargs["local_dir"]) / kwargs["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        make_ohlcv().to_parquet(target, index=False)
        return str(target)

    result = execute_forex_baseline_job(
        {
            "dataset": {
                "provider": "huggingface",
                "source_id": "owner/forex",
                "revision": "a" * 40,
                "file_path": "bars.parquet",
            },
            "artifact_id": "artifact-123",
            "artifact_upload_url": "https://storage.example/signed",
        },
        downloader=ExternalDatasetDownloader(huggingface_download=fake_hf_download),
        artifact_uploader=lambda upload_url, artifact: uploaded.append(artifact),
    )

    assert result["metrics"]["train_rows"] > result["metrics"]["test_rows"]
    assert len(uploaded) == 1