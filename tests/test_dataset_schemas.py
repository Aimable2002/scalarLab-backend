import pytest
from pydantic import ValidationError

from app.schemas import DatasetCreate


def test_huggingface_dataset_requires_a_commit_sha():
    with pytest.raises(ValidationError, match="immutable 40-character commit SHAs"):
        DatasetCreate(
            name="Forex bars",
            provider="huggingface",
            source_id="research/forex-bars",
            revision="main",
        )


def test_huggingface_dataset_accepts_a_commit_sha():
    dataset = DatasetCreate(
        name="Forex bars",
        provider="huggingface",
        source_id="research/forex-bars",
        revision="a" * 40,
    )

    assert dataset.revision == "a" * 40