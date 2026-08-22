#!/usr/bin/env python3
"""Self-check for ocgo.py's non-trivial logic (window bucketing + provider
filtering + formatting). Run directly: python3 test_ocgo.py
"""
import time

import ocgo as O
import collect_agent_usage as cau


def test_summarize_window():
    now_ms = int(time.time() * 1000)
    old = now_ms - 8 * 3600 * 1000  # outside 5h window
    inwin = now_ms - 60 * 1000      # inside
    records = [
        {"ts_ms": old, "model": "hy3", "title": "old", "directory": "/a",
         "input": 100, "output": 10, "cache_read": 9, "cache_write": 8, "reasoning": 7,
         "total": 134, "cost": 0.001, "session_id": "s-old"},
        {"ts_ms": inwin, "model": "hy3", "title": "Fix X", "directory": "/b",
         "input": 200, "output": 20, "cache_read": 90, "cache_write": 80, "reasoning": 70,
         "total": 460, "cost": 0.02, "session_id": "s-1"},
        {"ts_ms": inwin, "model": "big-pickle", "title": "Fix X", "directory": "/b",
         "input": 50, "output": 5, "cache_read": 5, "cache_write": 0, "reasoning": 0,
         "total": 60, "cost": 0.0, "session_id": "s-1"},
    ]
    s = O.summarize(records, now_ms - 5 * 3600 * 1000)
    assert s["msgs"] == 2, s
    assert s["tokens"] == 460 + 60, s
    assert s["cost"] == 0.02, s
    assert s["toks"]["input"] == 250 and s["toks"]["cache_read"] == 95, s["toks"]
    # by model: two distinct models; by session: both in "Fix X" bucket
    assert set(s["by_model"]) == {"hy3", "big-pickle"}, s["by_model"]
    assert list(s["by_session"]) == ["Fix X"], s["by_session"]
    assert s["by_session"]["Fix X"]["msgs"] == 2
    print("summarize window bucketing: OK")


def test_window_bounds_fallback():
    """Weekly boundary = resetsAt - 7d; monthly = resetsAt - 1 calendar month."""
    now = time.time()
    # weekly resets in 2 days (future); current period started 5 days ago
    week_reset = now + 2 * 86400
    usage = {"weekly": {"resetsAt": __iso(week_reset)}, "monthly": {}}
    b = O.window_bounds(usage)
    expect_week = int((week_reset - 7 * 86400) * 1000)
    assert abs(b["weekly"] - expect_week) < 2000, b
    # no resetsAt for monthly -> falls back to now-30d
    assert abs(b["monthly"] - int((now - O.MONTH_FALLBACK) * 1000)) < 2000, b
    # rolling always relative to now
    assert abs(b["rolling"] - int((now - O.ROLLING_SECONDS) * 1000)) < 2000, b
    print("window bound fallback: OK")


def test_subtract_period_monthly():
    # monthly reset on 09-19 17:43 -> period starts 08-19 17:43 (same day/time)
    iso = "2026-09-19T17:43:09.220Z"
    start = O.subtract_period(iso, "monthly")
    assert start is not None, "monthly period start must be a float"
    from datetime import datetime, timezone
    got = datetime.fromtimestamp(start, tz=timezone.utc)
    assert (got.year, got.month, got.day) == (2026, 8, 19), got
    # weekly: 7 days back
    from datetime import datetime, timezone
    w_reset = datetime(2026, 8, 24, tzinfo=timezone.utc).timestamp()
    w = O.subtract_period("2026-08-24T00:00:00Z", "weekly")
    assert w is not None, "weekly period start must be a float"
    assert abs(w - (w_reset - 7 * 86400)) < 10, datetime.fromtimestamp(w, tz=timezone.utc)
    print("subtract_period month/week: OK")


def test_load_paid_records_filters_provider():
    orig_discover, orig_parse = cau.discover_opencode, cau.parse_opencode
    orig_pdisc, orig_pparse = cau.discover_pi, cau.parse_pi
    orig_map = O.load_session_map
    try:
        cau.discover_opencode = lambda: ["FAKE.db"]
        cau.parse_opencode = lambda files: iter([
            {"source": "opencode", "timestamp": "2026-08-19T12:00:00Z", "session_id": "s1",
             "project": "/p", "model": f"{O.PAID_PROVIDER}/big-pickle",
             "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0,
             "cache_write_tokens": 0, "reasoning_tokens": 0, "total_tokens": 15,
             "cost_usd": 0.001},
            {"source": "opencode", "timestamp": "2026-08-19T12:00:00Z", "session_id": "s2",
             "project": "/p", "model": "opencode/deepseek-v4-flash-free",
             "input_tokens": 99, "output_tokens": 99, "cache_read_tokens": 99,
             "cache_write_tokens": 0, "reasoning_tokens": 0, "total_tokens": 297,
             "cost_usd": 0.0},
        ])
        cau.discover_pi = lambda: ["FAKE_PI.jsonl"]
        cau.parse_pi = lambda files: iter([
            # pi ran an opencode-go model has a provider field -> included
            {"source": "pi", "timestamp": "2026-08-19T13:00:00Z", "session_id": "pids",
             "project": "--home-devhax-projects-fusuycorp-titirek--",
             "provider": O.PAID_PROVIDER, "model": "kimi-k3",
             "input_tokens": 60, "output_tokens": 6, "cache_read_tokens": 0,
             "cache_write_tokens": 0, "reasoning_tokens": 0, "total_tokens": 66,
             "cost_usd": 0.02},
            # pi openrouter/free model -> excluded
            {"source": "pi", "timestamp": "2026-08-19T13:00:00Z", "session_id": "pfree",
             "project": "--some--", "provider": "openrouter", "model": "~deepseek/x",
             "input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0,
             "cache_write_tokens": 0, "reasoning_tokens": 0, "total_tokens": 2,
             "cost_usd": 0.0},
        ])
        O.load_session_map = lambda: {"s1": ("Free too", "/p"), "s2": ("Ignored", "/q")}
        recs = O.load_paid_records()
        # one opencode paid + one pi opencode-go paid = 2
        assert len(recs) == 2, f"expected 2 paid records, got {len(recs)}: {recs}"
        oc = [r for r in recs if r["model"] == "big-pickle"]
        assert len(oc) == 1 and oc[0]["title"] == "Free too" and oc[0]["total"] == 15
        pi_kimi = [r for r in recs if r["model"] == "kimi-k3"]
        assert len(pi_kimi) == 1, f"kimi-k3 from pi missing: {recs}"
        assert pi_kimi[0]["total"] == 66 and pi_kimi[0]["cost"] == 0.02
        assert pi_kimi[0]["directory"] == "--home-devhax-projects-fusuycorp-titirek--"
        assert not any(r["model"] == "~deepseek/x" for r in recs)
        print("paid-provider filter (opencode + pi): OK")
    finally:
        cau.discover_opencode, cau.parse_opencode = orig_discover, orig_parse
        cau.discover_pi, cau.parse_pi = orig_pdisc, orig_pparse
        O.load_session_map = orig_map


def test_window_flag_aliases():
    # short letters map to canonical window keys (case/space-insensitive)
    assert O.window_type("m") == "monthly"
    assert O.window_type("w") == "weekly"
    assert O.window_type("r") == "rolling"
    assert O.window_type("MONTHLY") == "monthly"
    assert O.window_type(" rolling ") == "rolling"
    assert O.window_type("weekly") == "weekly"  # full name passes through
    # anything else is rejected with argparse's native error type
    for bad in ("x", "month", "foo", ""):
        try:
            O.window_type(bad)
        except O.argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"expected ArgumentTypeError for {bad!r}")
    print("window flag aliases (r|w|m, -w/-c/-d/-n): OK")


def test_human_and_money():
    assert O.human(999) == "999"
    assert O.human(1500) == "1.5k"
    assert O.human(4_200_000) == "4.20M"
    assert O.human(3_000_000_000) == "3.00G"
    assert O.money(0) == "$0"
    assert O.money(0.0417) == "$0.0417"
    print("human/money formatting: OK")


def __iso(epoch):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    test_summarize_window()
    test_window_bounds_fallback()
    test_subtract_period_monthly()
    test_load_paid_records_filters_provider()
    test_window_flag_aliases()
    test_human_and_money()
    print("all ocgo self-checks passed")
