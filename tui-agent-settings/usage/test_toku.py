#!/usr/bin/env python3
"""Tests for toku.py: timezone parsing, bucketing boundaries, stacked-bar
rendering, headline totals, formatting. Stdlib unittest, no fixtures."""
import unittest
from datetime import datetime, timezone

import toku
from toku import (parse_ts_local, bucketize, period_totals, render_bar, fmt,
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
        self.assertEqual(day16, {"claude": 1000, "pi": 500})
        self.assertEqual(sum(b[0][1].values()), 300)

    def test_weekly(self):
        b = bucketize(self.RECORDS, tz=timezone.utc)["weekly"]
        keys = [d for d, _ in b]
        # W31 anchors 07-27 (holds 07-31 + 08-01), W33 anchors 08-10, W34 anchors 08-17
        self.assertEqual(keys, [datetime(2026, 7, 27).date(), datetime(2026, 8, 10).date(),
                                datetime(2026, 8, 17).date()])
        self.assertEqual(sum(b[0][1].values()), 1000)   # 300 + 700
        self.assertEqual(sum(b[1][1].values()), 1500)   # 1000 + 500
        self.assertEqual(sum(b[2][1].values()), 200)

    def test_monthly(self):
        b = bucketize(self.RECORDS, tz=timezone.utc)["monthly"]
        keys = [d for d, _ in b]
        self.assertEqual(keys, [datetime(2026, 7, 1).date(), datetime(2026, 8, 1).date()])
        self.assertEqual(sum(b[1][1].values()), 2400)

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
        self.assertEqual(t, {"today": 100, "week": 300, "month": 600})


class Fmt(unittest.TestCase):
    def test_units(self):
        self.assertEqual(fmt(2_000_000_000), "2.00B")
        self.assertEqual(fmt(468_813_755), "468.8M")
        self.assertEqual(fmt(1500), "2k")
        self.assertEqual(fmt(42), "42")
        self.assertEqual(fmt(0), "0")


if __name__ == "__main__":
    unittest.main()