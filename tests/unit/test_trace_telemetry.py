import sqlite3
import threading

from fastapi.testclient import TestClient

from asci.api.main import create_app
from asci.core.state import OperatorTraceItem, OperatorType
from asci.uskl.decision_store import DecisionTraceStore


def test_trace_survives_restart_and_legacy_migration(tmp_path):
    path = tmp_path / "decisions.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE operator_traces (trace_id INTEGER PRIMARY KEY, session_id TEXT, step_index INTEGER, operator_type TEXT, duration_ms REAL, cost REAL, seed INTEGER, timestamp TEXT)")
    conn.commit()
    conn.close()
    store = DecisionTraceStore(path)
    trace = OperatorTraceItem(step_index=1, operator_type=OperatorType.REWRITE_QUERY,
                              input_summary="before", output_summary="after", duration_ms=1.0, cost=0.002,
                              seed=42, metrics={"query_before": "Chennai", "query_after": "Tamil Nadu cyclone",
                                                "sufficiency_before": 0.2, "sufficiency_after": 0.8})
    store.record_trace("SESS_TEST", [trace])
    store._conn.close()
    restarted = DecisionTraceStore(path)
    assert OperatorTraceItem.model_validate(restarted.get_traces_for_session("SESS_TEST")[0]) == trace
    restarted._conn.close()


def test_progress_is_visible_before_plan_completes(monkeypatch):
    from asci.stages.stage_c_controller import StageCController

    entered, release = threading.Event(), threading.Event()
    original = StageCController._step_grade

    def block_grade(self, *args):
        entered.set()
        assert release.wait(20)
        return original(self, *args)

    monkeypatch.setattr(StageCController, "_step_grade", block_grade)
    with TestClient(create_app()) as client:
        event = client.post("/events", json={"raw_headline": "Chennai Port cyclone", "raw_text": "Severe storm"}).json()
        results = []
        thread = threading.Thread(target=lambda: results.append(client.post(
            f"/events/{event['event_id']}/plan", json={"session_id": "SESS_LIVE_TEST_123"})))
        thread.start()
        try:
            assert entered.wait(20)
            trace = client.get("/traces/SESS_LIVE_TEST_123").json()
            assert trace[-1]["operator_type"] == "RETRIEVE_TEXT"
            assert trace[-1]["metrics"]["query"]
            assert not results
        finally:
            release.set()
            thread.join(20)
        assert results[0].status_code == 200
        final = client.get("/traces/SESS_LIVE_TEST_123").json()
        assert len(final) == len({t["step_index"] for t in final})
        assert final[-1]["operator_type"] == "STOP"
        assert client.post(f"/events/{event['event_id']}/plan", json={"session_id": "SESS_LIVE_TEST_123"}).status_code == 409
