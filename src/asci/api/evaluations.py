"""Read-only access to measured Phase 8 artifacts; never launches benchmarks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_REPORT_BYTES = 32 * 1024 * 1024


class MeanMeasurement(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    mean: float
    ci95: tuple[float, float]
    n: int = Field(ge=1)


class StudySummary(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    study: int = Field(ge=1, le=9)
    network_scale: Literal["v0_core", "v1_corridor"]
    completed: bool
    targets: dict[str, bool] = Field(default_factory=dict)
    summary: dict[str, dict[str, MeanMeasurement | float | str | bool | None]]
    limitations: list[str]
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="allow")
    phase: Literal[8]
    completed: bool
    selected_studies: list[int] = Field(min_length=1, max_length=9)
    network_scales: list[Literal["v0_core", "v1_corridor"]] = Field(min_length=1, max_length=2)
    studies: list[StudySummary] = Field(max_length=18)

    @model_validator(mode="after")
    def check_coverage(self):
        if len(set(self.selected_studies)) != len(self.selected_studies) or not set(self.selected_studies) <= set(range(1, 10)):
            raise ValueError("Invalid selected studies")
        if len(set(self.network_scales)) != len(self.network_scales):
            raise ValueError("Duplicate network scale")
        expected = {(study, scale) for study in self.selected_studies for scale in self.network_scales}
        actual = {(row.study, row.network_scale) for row in self.studies}
        if len(actual) != len(self.studies) or not actual <= expected:
            raise ValueError("Duplicate or unexpected study results")
        if self.completed and (actual != expected or not all(row.completed for row in self.studies)):
            raise ValueError("Completed manifest has missing or incomplete studies")
        return self


def _reject_constant(_value):
    raise ValueError("Nonfinite JSON")


def evaluation_router(directory: Path) -> APIRouter:
    router = APIRouter(prefix="/evaluations/phase8", tags=["Evaluations"])

    def load(name):
        path = directory / name  # Names are generated internally; no client file paths.
        try:
            if path.stat().st_size > MAX_REPORT_BYTES:
                raise ValueError("Report exceeds size limit")
            data = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
            if not isinstance(data, dict):
                raise ValueError("Report must be an object")
            return data
        except FileNotFoundError as exc:
            raise HTTPException(404, "No measured report available. Run the Phase 8 ablation CLI first.") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "Evaluation artifact is unavailable or invalid; regenerate it with the CLI.") from exc

    @router.get("")
    def manifest():
        data = load("manifest.json")
        try:
            return EvaluationManifest.model_validate(data).model_dump()
        except ValidationError as exc:
            raise HTTPException(503, "Invalid Phase 8 manifest") from exc

    @router.get("/{study}/{scale}")
    def study_report(study: int = PathParam(ge=1, le=9), scale: Literal["v0_core", "v1_corridor"] = "v1_corridor"):
        data = load(f"study_{study}_{scale}.json")
        digest = data.get("report_sha256")
        numerical = {k: v for k, v in data.items() if k not in ("generated_at", "report_sha256")}
        computed = hashlib.sha256(json.dumps(numerical, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if data.get("study") != study or data.get("network_scale") != scale or computed != digest:
            raise HTTPException(503, "Evaluation artifact integrity check failed")
        return data

    return router
