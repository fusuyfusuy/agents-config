#!/usr/bin/env python3
"""Self-check for openrouter_pricing helper + toku --costs integration."""
import json
import os
import tempfile
import time

import openrouter_pricing as orp  # type: ignore[import-not-found]
import toku  # type: ignore[import-not-found]


def test_resolve_exact():
    pricing = {
        "anthropic/claude-sonnet-5": {"prompt": "0.000003", "completion": "0.000015"},
        "deepseek/deepseek-v4-flash": {"prompt": "0.00000022", "completion": "0.00000066"},
        "deepseek/deepseek-v4-flash-0731": {"prompt": "0.00000022", "completion": "0.00000066"},
        "meta/muse-spark-1.2": {"prompt": "0.0000003", "completion": "0.0000009"},
        "xiaomi/mimo-v2.5": {"prompt": "0.00000014", "completion": "0.00000028"},
        "tencent/hy3": {"prompt": "0.0000002", "completion": "0.0000004"},
        "stealth/ox-alpha": {"prompt": "0", "completion": "0"},
    }
    assert orp.resolve_model("anthropic/claude-sonnet-5", pricing) == "anthropic/claude-sonnet-5"
    assert orp.resolve_model("claude-sonnet-5", pricing) == "anthropic/claude-sonnet-5"
    assert orp.resolve_model("deepseek/deepseek-v4-flash-0731", pricing) == "deepseek/deepseek-v4-flash-0731"
    assert orp.resolve_model("deepseek-v4-flash", pricing) == "deepseek/deepseek-v4-flash"
    print("resolve exact/prefix: OK")


def test_resolve_strip_suffix():
    pricing = {
        "meta/muse-spark-1.2": {"prompt": "0.0000003"},
        "deepseek/deepseek-v4-flash": {"prompt": "0.00000022"},
        "stealth/ox-alpha": {"prompt": "0"},
        "tencent/hy3": {"prompt": "0.0000002"},
    }
    # -contributor stripped
    assert orp.resolve_model("opencode-go/muse-spark-1.2-contributor", pricing) == "meta/muse-spark-1.2"
    assert orp.resolve_model("muse-spark-1.2-contributor", pricing) == "meta/muse-spark-1.2"
    # -free stripped
    assert orp.resolve_model("ox-alpha-free", pricing) == "stealth/ox-alpha"
    assert orp.resolve_model("opencode/deepseek-v4-flash-free", pricing) == "deepseek/deepseek-v4-flash"
    assert orp.resolve_model("opencode-go/ox-alpha-free", pricing) == "stealth/ox-alpha"
    assert orp.resolve_model("deepseek/deepseek-v4-flash:free", pricing) == "deepseek/deepseek-v4-flash"
    # opencode-go alias
    assert orp.resolve_model("opencode-go/hy3", pricing) == "tencent/hy3"
    assert orp.resolve_model("opencode-go/deepseek-v4-flash", pricing) == "deepseek/deepseek-v4-flash"
    print("resolve strip/alias: OK")


def test_resolve_miss():
    pricing = {"anthropic/claude-sonnet-5": {"prompt": "0.000003"}}
    assert orp.resolve_model("opencode/big-pickle", pricing) is None
    assert orp.resolve_model("unknown-model-xyz", pricing) is None
    assert orp.resolve_model("", pricing) is None
    assert orp.resolve_model("claude-sonnet-5", {}) is None
    print("resolve miss: OK")


def test_estimate_basic():
    pricing = {
        "anthropic/claude-sonnet-5": {
            "prompt": "0.000003", "completion": "0.000015",
            "input_cache_read": "0.0000003", "input_cache_write": "0.00000375",
        }
    }
    rec = {"model": "claude-sonnet-5", "input": 1000, "output": 500, "crd": 10000, "cwr": 2000, "reason": 0}
    cost = orp.estimate_cost(rec, pricing)
    assert cost is not None
    expected = 1000*0.000003 + 500*0.000015 + 10000*0.0000003 + 2000*0.00000375
    assert abs(cost - expected) < 1e-12, f"{cost} vs {expected}"
    print("estimate basic: OK")


def test_estimate_reason_fallback():
    pricing = {
        "deepseek/deepseek-v4-flash": {"prompt": "0.00000022", "completion": "0.00000066"},
    }
    rec = {"model": "deepseek-v4-flash", "input": 100, "output": 50, "crd": 0, "cwr": 0, "reason": 20}
    cost = orp.estimate_cost(rec, pricing)
    assert cost is not None
    # reason should use completion price
    expected = 100*0.00000022 + 50*0.00000066 + 20*0.00000066
    assert abs(cost - expected) < 1e-12
    # with internal_reasoning present
    pricing2 = {"deepseek/deepseek-v4-flash": {"prompt": "0.00000022", "completion": "0.00000066", "internal_reasoning": "0.000001"}}
    cost2 = orp.estimate_cost(rec, pricing2)
    assert cost2 is not None
    expected2 = 100*0.00000022 + 50*0.00000066 + 20*0.000001
    assert abs(cost2 - expected2) < 1e-12
    print("estimate reason fallback: OK")


def test_estimate_override():
    pricing = {
        "anthropic/claude-sonnet-4.5": {
            "prompt": "0.000003", "completion": "0.000015",
            "input_cache_read": "0.0000003", "input_cache_write": "0.00000375",
            "overrides": [{"min_prompt_tokens": 200000, "prompt": "0.000006", "completion": "0.0000225", "input_cache_read": "0.0000006"}]
        }
    }
    # below threshold -> base
    rec = {"model": "claude-sonnet-4.5", "input": 1000, "output": 100, "crd": 0, "cwr": 0, "reason": 0}
    cost = orp.estimate_cost(rec, pricing)
    assert cost is not None
    assert abs(cost - (1000*0.000003 + 100*0.000015)) < 1e-12
    # above threshold 200k prompt tokens -> override
    rec2 = {"model": "claude-sonnet-4.5", "input": 200000, "output": 100, "crd": 0, "cwr": 0, "reason": 0}
    cost2 = orp.estimate_cost(rec2, pricing)
    assert cost2 is not None
    assert abs(cost2 - (200000*0.000006 + 100*0.0000225)) < 1e-12
    print("estimate override: OK")


def test_estimate_zero_and_miss():
    pricing = {"stealth/ox-alpha": {"prompt": "0", "completion": "0"}}
    rec = {"model": "ox-alpha-free", "input": 1000, "output": 500, "crd": 0, "cwr": 0, "reason": 0}
    cost = orp.estimate_cost(rec, pricing)
    assert cost == 0.0
    # miss returns None
    assert orp.estimate_cost({"model": "opencode/big-pickle", "input": 1, "output": 1, "crd": 0, "cwr": 0, "reason": 0}, pricing) is None
    print("estimate zero/miss: OK")


def test_cache_path_xdg():
    orig = os.environ.get("XDG_CACHE_HOME")
    try:
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            p = orp._cache_path()
            assert p == os.path.join(td, "toku", "openrouter-pricing.json"), p
            # ensure save/load works in temp dir
            sample = {"a/b": {"prompt": "0.000001"}}
            orp.save_cached(sample)
            loaded, ts = orp.load_cached()
            assert loaded == sample and ts is not None
            assert orp.is_fresh(ts) is True
            # old timestamp not fresh
            assert orp.is_fresh(time.time() - 100_000) is False
            print("cache path/save/load/fresh: OK")
    finally:
        if orig is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = orig
        # cleanup real cache not touched; temp dir auto removed


def test_get_pricing_stale_fallback():
    orig_fetch = orp.fetch_pricing
    orig_xdg = os.environ.get("XDG_CACHE_HOME")
    try:
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            # seed cache with old data
            sample = {"anthropic/claude-sonnet-5": {"prompt": "0.000003"}}
            orp.save_cached(sample)
            # make fetch fail
            orp.fetch_pricing = lambda timeout=5: None
            # without refresh but cache is fresh (just saved) -> should return cache without fetching
            m, src = orp.get_pricing(refresh=False, verbose=False)
            assert m == sample and src == "cache", (m, src)
            # force stale by making file old: rewrite with old timestamp via monkey-patching time.time for load?
            # Simulate fetch failure with stale: set file mtime old and call with refresh=True
            # Instead directly test stale path: make cache old by manipulating fetched_at in file
            path = orp._cache_path()
            with open(path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            blob["fetched_at"] = time.time() - 200_000  # >24h
            with open(path, "w", encoding="utf-8") as f:
                json.dump(blob, f)
            m2, src2 = orp.get_pricing(refresh=True, verbose=False)
            assert m2 == sample and src2 == "stale", (m2, src2)
            # no cache + fetch fail -> empty
            os.remove(path)
            m3, src3 = orp.get_pricing(refresh=True, verbose=False)
            assert m3 == {} and src3 == "none"
            print("get_pricing cache/stale/none: OK")
    finally:
        orp.fetch_pricing = orig_fetch
        if orig_xdg is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = orig_xdg


def test_aggregate_estimated():
    pricing = {
        "anthropic/claude-sonnet-5": {"prompt": "0.000003", "completion": "0.000015", "input_cache_read": "0.0000003"},
        "deepseek/deepseek-v4-flash": {"prompt": "0.00000022", "completion": "0.00000066"},
    }
    recs = [
        {"model": "claude-sonnet-5", "tokens": 11000, "input": 1000, "output": 0, "crd": 10000, "cwr": 0, "reason": 0},
        {"model": "claude-sonnet-5", "tokens": 500, "input": 0, "output": 500, "crd": 0, "cwr": 0, "reason": 0},
        {"model": "opencode/big-pickle", "tokens": 800, "input": 800, "output": 0, "crd": 0, "cwr": 0, "reason": 0},
    ]
    by, unmapped = toku.aggregate_models_estimated(recs, pricing)
    # claude aggregated
    assert by["claude-sonnet-5"]["reqs"] == 2
    assert by["claude-sonnet-5"]["cost_known"] is True
    # cost = 1000*0.000003 + 10000*0.0000003 + 500*0.000015 = 0.003+0.003+0.0075=0.0135
    expected = 1000*0.000003 + 10000*0.0000003 + 500*0.000015
    assert abs(by["claude-sonnet-5"]["cost"] - expected) < 1e-12
    assert "opencode/big-pickle" in unmapped
    assert by["opencode/big-pickle"]["cost_known"] is False
    print("aggregate estimated: OK")


def test_toku_detail_estimated_header():
    pricing = {"anthropic/claude-sonnet-5": {"prompt": "0.000003", "completion": "0.000015"}}
    recs = [
        {"dt": toku.parse_ts_local("2026-08-19T12:00:00Z"), "model": "claude-sonnet-5", "source": "claude", "project": "/p", "tokens": 100, "input": 50, "output": 50, "crd": 0, "cwr": 0, "reason": 0, "cost": None},
    ]
    # normal table header COST, estimated header EST COST
    normal = toku.detail_model_table(toku.aggregate_models(recs), 100, False)
    est_by, _ = toku.aggregate_models_estimated(recs, pricing)
    est = toku.detail_model_table(est_by, 100, False, estimated=True)
    assert any("COST" in line and "EST" not in line for line in normal) or any("COST" in line for line in normal)
    assert any("EST COST" in line for line in est)
    print("detail header est: OK")


if __name__ == "__main__":
    test_resolve_exact()
    test_resolve_strip_suffix()
    test_resolve_miss()
    test_estimate_basic()
    test_estimate_reason_fallback()
    test_estimate_override()
    test_estimate_zero_and_miss()
    test_cache_path_xdg()
    test_get_pricing_stale_fallback()
    test_aggregate_estimated()
    test_toku_detail_estimated_header()
    print("all openrouter_pricing self-checks passed")
