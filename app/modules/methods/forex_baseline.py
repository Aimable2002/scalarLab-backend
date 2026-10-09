from dataclasses import dataclass
from io import BytesIO

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class ForexBaselineResult:
    artifact_bytes: bytes
    metrics: dict[str, float | int]
    train_rows: int
    test_rows: int
    split_timestamp: str


class DatasetValidationError(ValueError):
    pass


def train_ohlcv_direction_baseline(data: pd.DataFrame) -> ForexBaselineResult:
    required_columns = {"timestamp", "open", "high", "low", "close"}
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        raise DatasetValidationError(
            f"Dataset is missing required columns: {', '.join(sorted(missing_columns))}"
        )

    frame = data.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if frame["timestamp"].isna().any():
        raise DatasetValidationError("Dataset timestamps must be valid")
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise DatasetValidationError("Dataset timestamps must be unique")

    price_columns = ["open", "high", "low", "close"]
    for column in price_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(frame[price_columns].to_numpy(dtype=float)).all():
        raise DatasetValidationError("OHLC values must be finite numeric values")
    if (frame[price_columns] <= 0).any().any():
        raise DatasetValidationError("OHLC values must be greater than zero")
    if (
        (frame["high"] < frame[["open", "close"]].max(axis=1)).any()
        or (frame["low"] > frame[["open", "close"]].min(axis=1)).any()
        or (frame["high"] < frame["low"]).any()
    ):
        raise DatasetValidationError("OHLC values contain inconsistent candle ranges")

    previous_close = frame["close"].shift(1)
    feature_frame = pd.DataFrame(
        {
            "close_return": frame["close"].pct_change(),
            "open_gap": frame["open"].div(previous_close).sub(1),
            "candle_body": frame["close"].sub(frame["open"]).div(previous_close),
            "candle_range": frame["high"].sub(frame["low"]).div(previous_close),
        }
    )
    if "volume" in frame:
        volume = pd.to_numeric(frame["volume"], errors="coerce")
        if not np.isfinite(volume.to_numpy(dtype=float)).all() or (volume < 0).any():
            raise DatasetValidationError("Volume values must be finite and non-negative")
        feature_frame["log_volume"] = np.log1p(volume)

    next_bar_up = frame["close"].shift(-1).gt(frame["close"]).astype("int8")
    valid_rows = feature_frame.notna().all(axis=1) & frame["close"].shift(-1).notna()
    features = feature_frame.loc[valid_rows]
    targets = next_bar_up.loc[valid_rows]
    timestamps = frame.loc[valid_rows, "timestamp"]
    if len(features) < 50:
        raise DatasetValidationError("At least 50 valid OHLCV rows are required")

    split_index = int(len(features) * 0.8)
    train_features = features.iloc[:split_index]
    test_features = features.iloc[split_index:]
    train_targets = targets.iloc[:split_index]
    test_targets = targets.iloc[split_index:]
    if train_targets.nunique() < 2 or test_targets.nunique() < 2:
        raise DatasetValidationError("Train and test periods must each contain both target classes")

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
    )
    model.fit(train_features, train_targets)
    predictions = model.predict(test_features)
    metrics: dict[str, float | int] = {
        "accuracy": float(accuracy_score(test_targets, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(test_targets, predictions)),
        "train_rows": len(train_features),
        "test_rows": len(test_features),
    }

    serialized_model = BytesIO()
    joblib.dump(
        {
            "estimator": model,
            "feature_columns": list(features.columns),
            "target": "next_bar_close_up",
            "split_timestamp": timestamps.iloc[split_index].isoformat(),
        },
        serialized_model,
        compress=3,
    )
    return ForexBaselineResult(
        artifact_bytes=serialized_model.getvalue(),
        metrics=metrics,
        train_rows=len(train_features),
        test_rows=len(test_features),
        split_timestamp=timestamps.iloc[split_index].isoformat(),
    )