"""Stateless scoring API backed by the MLflow champion alias."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from fraud_lab.serving import get_service

app = FastAPI(title="Graph-Aware Fraud Detector", version="0.1.0")


class Transaction(BaseModel):
    step: int = Field(ge=1)
    type: str
    amount: float = Field(ge=0)
    nameOrig: str = Field(min_length=1)
    oldbalanceOrg: float = Field(ge=0)
    nameDest: str = Field(min_length=1)
    oldbalanceDest: float = Field(ge=0)


def project_root() -> str:
    return os.environ.get("FRAUD_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))


@app.get("/health")
def health() -> dict:
    try:
        service = get_service(project_root())
        return {"status": "ok", "model_version": service.version}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"model unavailable: {exc}") from exc


@app.post("/score")
def score(transaction: Transaction) -> dict:
    if transaction.type not in {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}:
        raise HTTPException(status_code=422, detail="unsupported transaction type")
    try:
        service = get_service(project_root())
        frame = pd.DataFrame([transaction.model_dump()])
        return service.score(frame)[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"model unavailable: {exc}") from exc
