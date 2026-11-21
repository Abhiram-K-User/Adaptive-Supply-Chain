from asci.benchmarks.suite_s5 import SuiteS5Runner


def test_concurrent_episodes_and_feedback_survive_restart():
    report = SuiteS5Runner().run_suite()
    assert report["passed"]
    assert len(report["records"]) == 3
    assert len({r["session_id"] for r in report["records"]}) == 3
