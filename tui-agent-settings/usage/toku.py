#!/usr/bin/env python3
"""toku — stacked token-usage dashboard for every agent found in local logs.

Aggregates the per-message token usage collected by collect_agent_usage.py
(Claude Code, pi, OpenCode — exactly the same parsers) into local-time
daily / weekly / monthly buckets, and renders each bucket as a bar stacked
by source: claude=cyan, pi=magenta, opencode=green.

Usage: toku.py [--period daily|weekly|monthly] [--no-color]

Stdlib only; reuses collect_agent_usage's parsers and ocgo's display
helpers. Symlinked to ~/.local/bin/toku by setup.sh.
"""
import argparse
import shutil
import sys
from datetime import datetime, timedelta

import collect_agent_usage as cau
from ocgo import c, DIM, BOLD, CYAN, GREEN  # ocgo is import-safe (main() guarded)

MAGENTA = "\033[35m"

SOURCES = ["claude", "pi", "opencode"]
SRC_COLOR = {"claude": CYAN, "pi": MAGENTA, "opencode": GREEN}
BLOCKS = " ▏▎▍▌▋▊▉█"  # 1/8-cell steps; index = filled eighths

LONG = {"daily": ("DAILY", "last 14 days", 14), "weekly": ("WEEKLY", "last 8 weeks", 8),
        "monthly": ("MONTHLY", "last 6 months", 6)}


def parse_ts_local(raw, tz=None):
    """ISO timestamp -> naive local datetime (tz-aware input converted first)."""
    if not raw:
        return None
    s = raw if isinstance(raw, str) else str(raw)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is not None:
        tz = tz or datetime.now().astimezone().tzinfo
        dt = dt.astimezone(tz).replace(tzinfo=None)
    return dt


def fmt(n):
    n = float(n or 0)
    if n >= 1e12:
        return f"{n / 1e12:.2f}T"
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    return f"{n:.1f}" if n != int(n) else f"{int(n)}"


def all_records():
    for _name, discover, parse in cau.SOURCES:
        yield from parse(discover())


def _add(buckets, date_key, src, toks):
    cell = buckets.setdefault(date_key, {})
    entry = cell.setdefault(src, {"tokens": 0, "msgs": 0})
    entry["tokens"] += toks
    entry["msgs"] += 1


def bucketize(records, tz=None):
    """Group records into daily / ISO-weekly / monthly buckets (local time).

    Returns {'daily': [(date, {src: {'tokens','msgs'}}), ...], ...}, ascending.
    """
    daily, weekly, monthly = {}, {}, {}
    local_tz = tz or datetime.now().astimezone().tzinfo
    for r in records:
        dt = parse_ts_local(r.get("timestamp"), local_tz)
        if dt is None:
            continue
        toks = r.get("total_tokens") or 0
        if toks <= 0:
            continue
        src = r.get("source")
        d = dt.date()
        _add(daily, d, src, toks)
        _add(weekly, d - timedelta(days=d.weekday()), src, toks)
        _add(monthly, d.replace(day=1), src, toks)
    return {
        "daily": sorted(daily.items()),
        "weekly": sorted(weekly.items()),
        "monthly": sorted(monthly.items()),
    }


def period_totals(records, now, tz=None):
    """Tokens since local midnight / Monday / month start — the headline."""
    local_tz = tz or datetime.now().astimezone().tzinfo
    now = now.replace(tzinfo=None) if now.tzinfo else now
    starts = {
        "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
        "week": now.replace(hour=0, minute=0, second=0, microsecond=0)
                - timedelta(days=now.date().weekday()),
        "month": now.replace(hour=0, minute=0, second=0, microsecond=0, day=1),
    }
    totals = {k: {"tokens": 0, "msgs": 0} for k in starts}
    for r in records:
        dt = parse_ts_local(r.get("timestamp"), local_tz)
        if dt is None:
            continue
        toks = r.get("total_tokens") or 0
        if toks <= 0:
            continue
        for k, start in starts.items():
            if dt >= start:
                totals[k]["tokens"] += toks
                totals[k]["msgs"] += 1
    return totals


def render_bar(values, max_total, bar_w):
    """Stack `values` (one per source) into bar_w colored 1/8-cell chars.

    Returns [(char, ansi_color|''), ...], bar_w entries. Segment edges are
    rounded to the cell grid; the trailing filled unit colors a mixed cell.
    """
    units = [None] * (bar_w * 8)
    if max_total <= 0:
        return [(BLOCKS[0], "")] * bar_w
    cur = 0.0
    pos = 0
    for idx, v in enumerate(values):
        if v <= 0:
            continue
        cur += v
        end = min(int(round(cur / max_total * (bar_w * 8))), bar_w * 8)
        for u in range(pos, end):
            units[u] = idx
        pos = end
    out = []
    for cell in range(bar_w):
        filled = [u for u in units[cell * 8:(cell + 1) * 8] if u is not None]
        color = SRC_COLOR[SOURCES[filled[-1]]] if filled else ""
        out.append((BLOCKS[len(filled)], color))
    return out


def stats(vals):
    """Mean / median / min / max / population std of bucket totals."""
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return None
    mean = sum(vals) / n
    mid = n // 2
    median = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2
    var = sum((v - mean) ** 2 for v in vals) / n
    return {"mean": mean, "median": median, "min": vals[0], "max": vals[-1], "std": var ** 0.5}


def panel_lines(title, buckets, label_fn, bar_w, use_color, current_year=None, counts=False):
    """buckets: ascending [(anchor_date, {src: {'tokens','msgs'}})]."""
    totals = [
        {"anchor": a, "total": sum(e["tokens"] for e in b.values()),
         "msgs": sum(e["msgs"] for e in b.values())}
        for a, b in buckets
    ]
    max_total = max((t["total"] for t in totals), default=0)
    lines = [c(title, BOLD, use_color)]
    if max_total:
        peak = max(totals, key=lambda t: t["total"])
        lines[0] += c(f"      peak {label_fn(peak['anchor'], current_year)} {fmt(peak['total'])}", DIM, use_color)
    for (anchor, bucket), t in zip(buckets, totals):
        cells = render_bar([bucket.get(s, {}).get("tokens", 0) for s in SOURCES], max_total, bar_w)
        if not any(col for _, col in cells) and t["total"] > 0:
            cells[0] = ("▏", "")  # non-zero but below 1/8-cell resolution
        bar = "".join(
            c(ch, col, use_color) if col else (c(ch, DIM, use_color) if ch != " " else ch)
            for ch, col in cells
        )
        row = f"  {label_fn(anchor, current_year):<7} {bar}  {fmt(t['total']):>9}"
        if counts:
            row += f"  {fmt(t['msgs']):>9}"
        if max_total and t["total"] == max_total:
            row += c("  ← peak", DIM, use_color)
        lines.append(row)
    if len(totals) >= 2:
        s = stats([t["total"] for t in totals])
        stat_str = "  ".join(
            f"{k} {fmt(v)}" for k, v in
            (("mean", s["mean"]), ("median", s["median"]), ("min", s["min"]), ("max", s["max"]), ("σ", s["std"]))
        )
        lines.append(c("  stats  " + stat_str, DIM, use_color))
        if counts:
            m = stats([t["msgs"] for t in totals])
            mstr = "  ".join(
                f"{k} {fmt(v)}" for k, v in
                (("mean", m["mean"]), ("median", m["median"]), ("min", m["min"]), ("max", m["max"]), ("σ", m["std"]))
            )
            lines.append(c("         " + mstr, DIM, use_color))
    return lines


def daily_label(d, _y=None):
    return d.strftime("%m-%d")


def weekly_label(d, _y=None):
    return f"W{d.isocalendar().week:02d}"


def monthly_label(d, current_year):
    lab = d.strftime("%b")
    if d.year != current_year:
        lab += f" '{str(d.year)[2:]}"
    return lab


def main():
    ap = argparse.ArgumentParser(description="Stacked token-usage dashboard for all agents found in local logs")
    ap.add_argument("--period", choices=["daily", "weekly", "monthly"],
                    help="show one panel only (default: dashboard = all three)")
    ap.add_argument("--requests", action="store_true",
                    help="also show per-bucket request counts and count statistics")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI color")
    args = ap.parse_args()

    use_color = not args.no_color and sys.stdout.isatty()
    records = list(all_records())
    if not records:
        print("no token usage records found (checked Claude Code / pi / OpenCode logs)")
        sys.exit(1)

    buckets = bucketize(records)
    now = datetime.now()
    totals = period_totals(records, now)
    head = f"TOTAL TOKENS   today {fmt(totals['today']['tokens'])} · this week {fmt(totals['week']['tokens'])} · this month {fmt(totals['month']['tokens'])}"
    print(c(head, BOLD, use_color))
    if args.requests:
        req = (f"REQUESTS       today {fmt(totals['today']['msgs'])} · this week {fmt(totals['week']['msgs'])}"
               f" · this month {fmt(totals['month']['msgs'])}")
        print(c(req, BOLD, use_color))
    print()

    cols = shutil.get_terminal_size((120, 24)).columns
    bar_w = max(12, min(64, cols - (42 if args.requests else 30)))

    labels = {"daily": daily_label, "weekly": weekly_label, "monthly": monthly_label}
    picked = [args.period] if args.period else list(LONG)
    for key in picked:
        title, desc, n = LONG[key]
        lines = panel_lines(f"{title} ({desc})", buckets[key][-n:], labels[key], bar_w, use_color,
                            current_year=now.year, counts=args.requests)
        print("\n".join(lines))
        print()

    legend = "  " + " ".join(
        c(BLOCKS[-1], SRC_COLOR[s], use_color) + f" {s}" for s in SOURCES
    )
    print(legend + c("   · grouped by local time", DIM, use_color))


if __name__ == "__main__":
    main()