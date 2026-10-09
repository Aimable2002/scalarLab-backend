from pathlib import Path

import pytest

from app.adapters.datasets.download import ExternalDatasetDownloader, validate_provider_file_path


def test_dataset_file_path_rejects_absolute_and_traversal_paths():
    for file_path in ("/etc/passwd", "../outside.csv", "data\\..\\outside.csv"):
        with pytest.raises(ValueError, match="provider-relative"):
            validate_provider_file_path(file_path)


def test_huggingface_dataset_is_downloaded_under_temporary_job_storage(tmp_path):
    downloaded_paths = []

    def fake_download(**kwargs):
        target = Path(kwargs["local_dir"]) / kwargs["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("timestamp,open,high,low,close\n", encoding="utf-8")
        downloaded_paths.append(target)
        return str(target)

    downloader = ExternalDatasetDownloader(huggingface_download=fake_download)
    with downloader.download(
        "huggingface", "owner/dataset", "a" * 40, "bars/hourly.csv"
    ) as path:
        temporary_root = path.parents[1]
        assert path.is_file()
        assert "scalar-lab-dataset-" in str(path)

    assert not temporary_root.exists()
    assert downloaded_paths == [path]


def test_kaggle_download_rejects_unpinned_provider_behavior():
    from app.adapters.datasets.download import DatasetProviderCapabilityError

    downloader = ExternalDatasetDownloader()
    with pytest.raises(DatasetProviderCapabilityError, match="Pinned Kaggle"):
        with downloader.download("kaggle", "author/dataset", "4", "bars.csv"):
            pass