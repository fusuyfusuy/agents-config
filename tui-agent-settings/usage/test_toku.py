#!/usr/bin/env python3
"""Tests for toku.py: timezone parsing, bucketing boundaries, stacked-bar
rendering, headline totals, formatting. Stdlib unittest, no fixtures."""
import unittest
from datetime import datetime, timezone

import toku
from toku import (parse_ts_local, parse_records, bucketize, period_totals, render_bar, panel_lines,
                  fmt, stats, percentile, log_bins, hist_chars, aggregate_models, aggregate_projects,
                  token_type_totals, cache_hit, rhythm_buckets, detail_model_table,
                  CYAN, MAGENTA)


def rec(ts, src, tokens):
    return {"timestamp": ts, "source": src, "total_tokens": tokens}


class ParseTs(unittest.TestCase):
    def test_z_suffix_to_utc(self):
        self.assertEqual(parse_ts_local("2026-08-19T12:00:00Z", tz=timezone.utc),
                         datetime(2026, 8, 19, 12, 0))

    def test_offset_shifted(self):
        self.assertEqual(parse_ts_local("2026-08-19T12:00:00+02:00", tz=timezone.utc),
                         datetime(2026, 8, 19, 10, 0))

    def test_naive_passthrough(self):
        self.assertEqual(parse_ts_local("2026-08-19T12:00:00", tz=timezone.utc),
                         datetime(2026, 8, 19, 12, 0))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_ts_local("not-a-date", tz=timezone.utc))
        self.assertIsNone(parse_ts_local("", tz=timezone.utc))


class Bucketize(unittest.TestCase):
    RECORDS = [
        rec("2026-08-16T12:00:00", "claude", 1000),   # Sun W33
        rec("2026-08-16T13:00:00", "pi", 500),        # Sun W33
        rec("2026-08-17T00:30:00", "opencode", 200),  # Mon W34
        rec("2026-07-31T09:00:00", "claude", 300),    # Fri W31
        rec("2026-08-01T09:00:00", "pi", 700),        # Sat W31
    ]

    def test_daily(self):
        b = bucketize(self.RECORDS, tz=timezone.utc)["daily"]
        keys = [d for d, _ in b]
        self.assertEqual(keys, [datetime(2026, 7, 31).date(), datetime(2026, 8, 1).date(),
                                datetime(2026, 8, 16).date(), datetime(2026, 8, 17).date()])
        day16 = dict(b[2][1])
        self.assertEqual(day16, {"claude": {"tokens": 1000, "msgs": 1},
                                 "pi": {"tokens": 500, "msgs": 1}})
        self.assertEqual(sum(e["tokens"] for e in b[0][1].values()), 300)

    def test_msgs_accumulate_per_bucket(self):
        b = bucketize([rec("2026-08-16T12:00:00", "claude", 100),
                       rec("2026-08-16T13:00:00", "claude", 50),
                       rec("2026-08-16T14:00:00", "pi", 0)], tz=timezone.utc)["daily"]
        self.assertEqual(b[0][1], {"claude": {"tokens": 150, "msgs": 2}})

    def test_weekly(self):
        b = bucketize(self.RECORDS, tz=timezone.utc)["weekly"]
        keys = [d for d, _ in b]
        # W31 anchors 07-27 (holds 07-31 + 08-01), W33 anchors 08-10, W34 anchors 08-17
        self.assertEqual(keys, [datetime(2026, 7, 27).date(), datetime(2026, 8, 10).date(),
                                datetime(2026, 8, 17).date()])
        self.assertEqual(sum(e["tokens"] for e in b[0][1].values()), 1000)   # 300 + 700
        self.assertEqual(sum(e["tokens"] for e in b[1][1].values()), 1500)   # 1000 + 500
        self.assertEqual(sum(e["tokens"] for e in b[2][1].values()), 200)

    def test_monthly(self):
        b = bucketize(self.RECORDS, tz=timezone.utc)["monthly"]
        keys = [d for d, _ in b]
        self.assertEqual(keys, [datetime(2026, 7, 1).date(), datetime(2026, 8, 1).date()])
        self.assertEqual(sum(e["tokens"] for e in b[1][1].values()), 2400)

    def test_skips_untimestamped_and_zero(self):
        b = bucketize([rec(None, "claude", 999), rec("2026-08-16T00:00:00", "pi", 0)],
                      tz=timezone.utc)["daily"]
        self.assertEqual(b, [])


class RenderBar(unittest.TestCase):
    def test_clean_split(self):
        cells = render_bar([60, 40], 100, 10)
        self.assertEqual(len(cells), 10)
        self.assertEqual([ch for ch, _ in cells], ["█"] * 10)
        self.assertEqual([col for _, col in cells], [CYAN] * 6 + [MAGENTA] * 4)

    def test_half_half_single_cell(self):
        # round(50/100*8)=4 -> first half claude, second half pi; cell colored
        # by the trailing filled unit (pi).
        self.assertEqual(render_bar([50, 50], 100, 1), [("█", MAGENTA)])

    def test_quarter_cell(self):
        # round(25/100*8)=2 -> "▌" (4 eighths), colored by pi.
        self.assertEqual(render_bar([25, 25], 100, 1)[0], ("▌", MAGENTA))

    def test_single_source(self):
        self.assertEqual(render_bar([0, 100], 100, 3),
                         [("█", MAGENTA)] * 3)

    def test_zero_total(self):
        self.assertEqual(render_bar([0, 0, 0], 0, 4),
                         [(" ", "")] * 4)


class PeriodTotals(unittest.TestCase):
    NOW = datetime(2026, 8, 19, 10, 0)  # Wednesday, naive UTC

    def test_headline_sums(self):
        records = [
            rec("2026-08-19T09:00:00Z", "claude", 100),   # today
            rec("2026-08-17T09:00:00Z", "pi", 200),       # this week (Mon)
            rec("2026-08-01T09:00:00Z", "opencode", 300), # this month
            rec("2026-07-15T09:00:00Z", "claude", 999),   # before month start
        ]
        t = period_totals(records, self.NOW, tz=timezone.utc)
        self.assertEqual(t, {"today": {"tokens": 100, "msgs": 1},
                             "week": {"tokens": 300, "msgs": 2},
                             "month": {"tokens": 600, "msgs": 3}})


class Stats(unittest.TestCase):
    def test_odd_count(self):
        s = stats([4, 8, 6])
        self.assertEqual(s["mean"], 6)
        self.assertEqual(s["median"], 6)
        self.assertEqual((s["min"], s["max"]), (4, 8))
        self.assertAlmostEqual(s["std"], (8 / 3) ** 0.5)

    def test_even_count_median_averages_middles(self):
        s = stats([1, 2, 3, 4])
        self.assertEqual(s["median"], 2.5)
        self.assertAlmostEqual(s["std"], 1.25 ** 0.5)

    def test_single_value(self):
        s = stats([7])
        self.assertEqual((s["mean"], s["median"], s["min"], s["max"], s["std"]), (7, 7, 7, 7, 0))

    def test_empty(self):
        self.assertIsNone(stats([]))


class PanelLines(unittest.TestCase):
    BUCKETS = [
        (datetime(2026, 8, 16).date(), {"claude": {"tokens": 100, "msgs": 2}}),
        (datetime(2026, 8, 17).date(), {"pi": {"tokens": 300, "msgs": 1}}),
    ]

    def test_token_rows_only_by_default(self):
        lines = panel_lines("T (x)", self.BUCKETS, toku.daily_label, 20, False, 2026, counts=False)
        self.assertEqual(len(lines), 4)  # title + 2 rows + 1 stats line
        self.assertTrue(lines[3].startswith("  stats  "))
        self.assertNotIn(" 1 ", lines[1])  # no count column

    def test_count_column_and_stats(self):
        lines = panel_lines("T (x)", self.BUCKETS, toku.daily_label, 20, False, 2026, counts=True)
        self.assertEqual(len(lines), 5)  # + 1 count-stats line
        self.assertRegex(lines[1], r"100\s+2$")     # token total + count column
        self.assertRegex(lines[2], r"300\s+1\s+← peak$")
        self.assertTrue(lines[4].startswith("         "))  # aligned under 'stats  '
        self.assertIn("mean 1.5", lines[4])
        self.assertIn("max 2", lines[4])


class Detail(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50), 5)
        self.assertEqual(percentile([1, 2, 3, 4, 5], 90), 5)
        self.assertEqual(percentile([7], 50), 7)
        self.assertIsNone(percentile([], 50))

    def test_log_bins(self):
        b = log_bins([10, 100, 1000, 10000, 100000, 1000000], n=12)
        self.assertIsNotNone(b)
        edges, counts = b
        self.assertEqual(len(edges), 13)
        self.assertEqual(sum(counts), 6)
        self.assertIsNone(log_bins([5, 6, 7]))  # too narrow a range
        self.assertIsNone(log_bins([10]))       # single value

    def test_hist_chars(self):
        self.assertEqual(hist_chars([0, 4, 8]), [" ", "▌", "█"])
        self.assertEqual(hist_chars([0, 0]), [" ", " "])

    def _parsed(self, raws):
        return parse_records(raws, tz=timezone.utc)

    def test_aggregate_models(self):
        raws = [
            dict(rec("2026-08-16T12:00:00", "claude", 100), model="m1", project="/p/a", cost_usd=None),
            dict(rec("2026-08-16T13:00:00", "pi", 50), model="m2", project="/p/b", cost_usd=0.25),
            dict(rec("2026-08-16T14:00:00", "pi", 80), model="m1", project="/p/a", cost_usd=0.1),
        ]
        pr = self._parsed(raws)
        m = aggregate_models(pr)
        self.assertEqual(m["m1"], {"reqs": 2, "tokens": 180, "cost": 0.1, "cost_known": True})
        self.assertEqual(m["m2"], {"reqs": 1, "tokens": 50, "cost": 0.25, "cost_known": True})
        projs = aggregate_projects(pr)
        self.assertEqual(projs["a"]["tokens"], 180)
        self.assertEqual(projs["b"]["tokens"], 50)

    def test_token_types_and_cache_hit(self):
        raws = [
            dict(rec("2026-08-16T12:00:00", "pi", 1000), input_tokens=800, output_tokens=100,
                 cache_read_tokens=50, cache_write_tokens=50, reasoning_tokens=40),
            dict(rec("2026-08-16T13:00:00", "claude", 900), input_tokens=900, output_tokens=0,
                 cache_read_tokens=0, cache_write_tokens=0),
        ]
        pr = self._parsed(raws)
        by_src, totals = token_type_totals(pr)
        self.assertEqual(by_src["pi"], {"input": 800, "output": 100, "crd": 50, "cwr": 50, "reason": 40})
        self.assertEqual(totals["input"], 1700)
        self.assertAlmostEqual(cache_hit(50, 800), 50 / 850 * 100)
        self.assertEqual(cache_hit(0, 0), 0)

    def test_rhythm_buckets(self):
        raws = [rec(f"2026-08-16T{hh:02d}:00:00", "claude", 10) for hh in (0, 0, 6, 23)]
        pr = self._parsed(raws)
        hourly, weekday = rhythm_buckets(pr)
        self.assertEqual(hourly[0], 20)
        self.assertEqual(hourly[6], 10)
        self.assertEqual(hourly[23], 10)
        self.assertEqual(weekday[6], 40)  # 2026-08-16 is a Sunday

    def test_model_table_sorted_and_capped(self):
        models = {"a": {"reqs": 1, "tokens": 10, "cost": 0, "cost_known": False},
                  "b": {"reqs": 1, "tokens": 99, "cost": 0, "cost_known": False}}
        lines = detail_model_table(models, 109, False, cap=1)
        self.assertIn("b", lines[1])       # header is line 0; top row is the largest model
        self.assertIn("90.8%", lines[1])
        self.assertIn("+1 more models", lines[-1])
        self.assertIn("—", lines[1])       # no cost known -> em dash


class Fmt(unittest.TestCase):
    def test_units(self):
        self.assertEqual(fmt(2_000_000_000), "2.00B")
        self.assertEqual(fmt(468_813_755), "468.8M")
        self.assertEqual(fmt(1500), "2k")
        self.assertEqual(fmt(42), "42")
        self.assertEqual(fmt(0), "0")
        self.assertEqual(fmt(1.5), "1.5")   # sub-thousand fraction (count means)


if __name__ == "__main__":
    unittest.main()