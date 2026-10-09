from io import BytesIO

import joblib
import numpy as np
import pandas as pd
import pytest

from app.modules.methods.forex_baseline import DatasetValidationError, train_ohlcv_direction_baseline


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
            "volume": np.arange(rows, dtype=float),
        }
    )


def test_forex_baseline_uses_chronological_split_and_serializes_model():
    result = train_ohlcv_direction_baseline(make_ohlcv())

    assert result.train_rows > result.test_rows
    assert result.test_rows > 0
    assert result.metrics["accuracy"] >= 0
    assert result.metrics["balanced_accuracy"] >= 0
    artifact = joblib.load(BytesIO(result.artifact_bytes))
    assert artifact["target"] == "next_bar_close_up"
    assert artifact["feature_columns"]
    assert result.split_timestamp.startswith("2025-")


def test_forex_baseline_rejects_missing_candle_columns():
    with pytest.raises(DatasetValidationError, match="missing required columns"):
        train_ohlcv_direction_baseline(pd.DataFrame({"timestamp": ["2025-01-01"]}))


def test_forex_baseline_rejects_duplicate_timestamps():
    data = make_ohlcv()
    data.loc[1, "timestamp"] = data.loc[0, "timestamp"]

    with pytest.raises(DatasetValidationError, match="timestamps must be unique"):
        train_ohlcv_direction_baseline(data)