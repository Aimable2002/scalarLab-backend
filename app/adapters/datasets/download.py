from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from typing import Literal

from huggingface_hub import hf_hub_download


DatasetProvider = Literal["kaggle", "huggingface"]


class DatasetProviderCapabilityError(ValueError):
    pass


def validate_provider_file_path(file_path: str) -> PurePosixPath:
    path = PurePosixPath(file_path)
    if (
        not file_path
        or "\\" in file_path
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("Dataset file path must be a safe provider-relative path")
    return path


class ExternalDatasetDownloader:
    def __init__(
        self,
        huggingface_download: Callable[..., str] = hf_hub_download,
    ) -> None:
        self.huggingface_download = huggingface_download

    @contextmanager
    def download(
        self,
        provider: DatasetProvider,
        source_id: str,
        revision: str,
        file_path: str,
    ) -> Iterator[Path]:
        relative_path = validate_provider_file_path(file_path)
        if provider == "huggingface" and re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None:
            raise DatasetProviderCapabilityError(
                "Hugging Face downloads require an immutable 40-character commit SHA"
            )
        with TemporaryDirectory(prefix="scalar-lab-dataset-") as temporary_directory:
            temporary_root = Path(temporary_directory).resolve()
            if provider == "huggingface":
                downloaded_path = self.huggingface_download(
                    repo_id=source_id,
                    filename=relative_path.as_posix(),
                    repo_type="dataset",
                    revision=revision,
                    local_dir=temporary_root,
                    token=None,
                )
            elif provider == "kaggle":
                raise DatasetProviderCapabilityError(
                    "Pinned Kaggle dataset revision downloads are not supported yet"
                )
            else:
                raise ValueError(f"Unsupported dataset provider: {provider}")

            resolved_path = Path(downloaded_path).resolve()
            if temporary_root not in resolved_path.parents or not resolved_path.is_file():
                raise ValueError("Dataset provider returned a file outside temporary job storage")
            yield resolved_path