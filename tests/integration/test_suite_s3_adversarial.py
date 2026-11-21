from asci.benchmarks.suite_s3 import PAYLOADS, SuiteS3Runner


def test_adversarial_corpus_is_isolated():
    report = SuiteS3Runner().run_suite()
    assert len(report["records"]) >= 2 * len(PAYLOADS) + 5
    assert report["passed"], report["failures"]
    assert report["catch_rate"] == 1.0
    assert report["graph_contamination_rate"] == 0.0
