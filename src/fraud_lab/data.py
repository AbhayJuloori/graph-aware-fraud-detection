"""PaySim ingestion and chronological splitting."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAW_COLUMNS = [
    "step", "type", "amount", "nameOrig", "oldbalanceOrg", "nameDest",
    "oldbalanceDest", "isFraud",
]
DTYPES = {
    "step": "int16", "type": "category", "amount": "float32",
    "nameOrig": "string", "oldbalanceOrg": "float32", "nameDest": "string",
    "oldbalanceDest": "float32", "isFraud": "int8",
}


def load_paysim(path: str | Path, sample_fraction: float = 1.0, seed: int = 42,
                sample_start: float = 0.0) -> pd.DataFrame:
    """Uniform row sample window without labels; preserve row order within steps.

    Nonoverlapping windows with the same seed create disjoint row cohorts.
    """
    if not 0 < sample_fraction <= 1 or not 0 <= sample_start < 1 or sample_start + sample_fraction > 1:
        raise ValueError("sample window must lie within [0, 1]")
    rng = np.random.default_rng(seed)
    batches = []
    for chunk in pd.read_csv(path, usecols=RAW_COLUMNS, dtype=DTYPES, chunksize=200_000):
        if sample_fraction < 1:
            draws = rng.random(len(chunk))
            chunk = chunk.loc[(draws >= sample_start) & (draws < sample_start + sample_fraction)]
        batches.append(chunk)
    data = pd.concat(batches, ignore_index=True)
    if data.empty:
        raise ValueError("sample contains no transactions")
    if not data.step.is_monotonic_increasing:
        raise ValueError("PaySim rows must be sorted by step")
    return data


def chronological_split(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Assign whole time steps to train, validation, and never-used test windows."""
    train_end = int(data.step.quantile(0.60))
    validation_end = int(data.step.quantile(0.80))
    train = data.loc[data.step <= train_end].copy()
    validation = data.loc[(data.step > train_end) & (data.step <= validation_end)].copy()
    test = data.loc[data.step > validation_end].copy()
    for name, frame in (("train", train), ("validation", validation), ("test", test)):
        if frame.empty or frame.isFraud.nunique() < 2:
            raise ValueError(f"{name} window needs both fraud and legitimate transactions")
    return train, validation, test, {"train_end_step": train_end, "validation_end_step": validation_end}
