import pytest

from backend.app.render import cost
from backend.app.settings import load_pricing


def test_gemini_720p_rate_matches_official_token_math():
    # 5,792 tokens per second of 720p x $17.50 per 1M output tokens (Gemini API pricing page)
    assert cost.gemini_cost_from_tokens(5792) == pytest.approx(0.1014, abs=1e-4)
    assert load_pricing()["omni-gemini"]["720p"] == pytest.approx(5792 * 17.50 / 1e6, rel=1e-3)


def test_estimate_three_clip_fal_render():
    est = cost.estimate(load_pricing(), "omni-fal", "720p", 3, 10)
    assert est.base_usd == pytest.approx(3.00) and est.max_usd == pytest.approx(3.75)


def test_unverified_rate_refuses_to_estimate():
    with pytest.raises(cost.PricingUnknown):
        cost.estimate(load_pricing(), "omni-gemini", "4k", 3)


def test_budget_cap_is_hard():
    assert cost.within_budget(9.0, 1.0, 10.0)
    assert not cost.within_budget(9.5, 1.0, 10.0)
    assert cost.estimate(load_pricing(), "mock", "720p", 6).max_usd == 0
