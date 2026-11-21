import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from asci.api.evaluations import evaluation_router


def test_read_only_report_api_checks_integrity_and_missing_artifacts(tmp_path):
    app = FastAPI()
    app.include_router(evaluation_router(tmp_path))
    with TestClient(app) as client:
        assert client.get("/evaluations/phase8").status_code == 404
        manifest = {"phase": 8, "completed": False, "selected_studies": [1], "network_scales": ["v0_core"], "studies": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        assert client.get("/evaluations/phase8").json() == manifest
        assert client.post("/evaluations/phase8").status_code == 405
        assert client.get("/evaluations/phase8/10/v0_core").status_code == 422
        assert client.get("/evaluations/phase8/1/private").status_code == 422
        report = {"study": 1, "network_scale": "v0_core", "completed": True, "summary": {}}
        digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
        report.update({"generated_at": "2026-11-21", "report_sha256": digest})
        path = tmp_path / "study_1_v0_core.json"
        path.write_text(json.dumps(report))
        assert client.get("/evaluations/phase8/1/v0_core").json() == report
        report["completed"] = False
        path.write_text(json.dumps(report))
        assert client.get("/evaluations/phase8/1/v0_core").status_code == 503
        path.write_text('{"cost":NaN}')
        assert client.get("/evaluations/phase8/1/v0_core").status_code == 503


def test_invalid_manifest_is_not_presented_as_measurement(tmp_path):
    app = FastAPI()
    app.include_router(evaluation_router(tmp_path))
    with TestClient(app) as client:
        for content in ('[]', '{"phase":9,"studies":[]}', 'not json'):
            (tmp_path / "manifest.json").write_text(content)
            assert client.get("/evaluations/phase8").status_code == 503
