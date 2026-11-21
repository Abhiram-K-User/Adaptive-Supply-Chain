import json

import pytest

from asci.benchmarks.ablations.dataset import AblationConfig
from asci.benchmarks.metrics import auroc, ece, mean_ci, pareto_frontier, reduction, weighted_cvar
from asci.llm.client import LLMCompletionResult
from asci.policy.llm_planner import LLMPlannerPolicy
from asci.policy.model import ACTION_TO_IDX, CONTROLLER_ACTIONS, FEATURE_DIM


def test_auroc_ties_and_undefined_class():
    assert auroc([1, 0], [.5, .5]) == .5
    assert auroc([0, 1, 0, 1], [.1, .7, .4, .9]) == 1
    assert auroc([0, 1], [.9, .1]) == 0
    assert auroc([1, 1], [.1, .9]) is None
    with pytest.raises(ValueError):
        auroc([0, 1], [float("nan"), .2])


def test_ece_includes_one_endpoint_and_cvar_fractional_tail():
    assert ece([0, 1], [0, 1]) == 0
    assert ece([1, 0], [0, 1]) == 1
    assert weighted_cvar([0, 10], [.9, .1], .8) == pytest.approx(5)
    assert weighted_cvar([0, 10], [.9, .1], .95) == 10
    with pytest.raises(ValueError):
        ece([1], [1.1])


def test_bootstrap_determinism_and_measured_frontier():
    assert mean_ci([1, 3, 5], seed=9) == mean_ci([1, 3, 5], seed=9)
    points = [{"cost": 1, "regret": 5}, {"cost": 2, "regret": 3}, {"cost": 3, "regret": 4}]
    assert pareto_frontier(points) == points[:2]
    assert reduction(0, 0) is None


@pytest.mark.parametrize("values", [(), (.1, .1), (-1,), (.6,), (float("nan"),)])
def test_study_config_rejects_invalid_lambdas(values):
    with pytest.raises(ValueError):
        AblationConfig(lambdas=values)


def test_real_completion_cache_and_mask_validation(tmp_path):
    class Client:
        calls = 0
        def complete(self, *_args, **_kwargs):
            self.calls += 1
            return LLMCompletionResult(text='{"action":"SCENARIOS","probability_deeper_needed":0.2}',
                                       provider="test-provider", model="test-model", used_live_llm=True)
    client = Client()
    live = LLMPlannerPolicy(tmp_path, allow_live=True, client=client)
    mask = [op.value == "SCENARIOS" for op in CONTROLLER_ACTIONS]
    features = [0.]*FEATURE_DIM
    action, probs = live.predict_action(features, mask)
    assert probs[ACTION_TO_IDX[action]] == 1
    assert client.calls == 1
    replay = LLMPlannerPolicy(tmp_path, allow_live=False, client=client)
    assert replay.predict_action(features, mask) == (action, probs)
    assert client.calls == 1
    path = next(tmp_path.glob("*.json"))
    record = json.loads(path.read_text())
    record["completion"]["text"] = '{}'
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="checksum"):
        replay.predict_action(features, mask)
    with pytest.raises(RuntimeError, match="Missing real LLM"):
        replay.predict_action([.1]*FEATURE_DIM, mask)


def test_planner_rejects_masked_action_and_fallback(tmp_path):
    completion = {"completion": {"text": '{"action":"GRADE","probability_deeper_needed":0.2}', "used_live_llm": True}}
    with pytest.raises(ValueError, match="invalid action"):
        LLMPlannerPolicy._decode(completion, [False]*len(CONTROLLER_ACTIONS))
    completion["completion"]["used_live_llm"] = False
    with pytest.raises(ValueError, match="fallback"):
        LLMPlannerPolicy._decode(completion, [True]*len(CONTROLLER_ACTIONS))
