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
import bisect
import math
import os
import shutil
import sys
from datetime import datetime, timedelta

import collect_agent_usage as cau
from ocgo import c, pad, money, _table, DIM, BOLD, CYAN, GREEN  # ocgo is import-safe (main() guarded)

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


def parse_records(records, tz=None):
    """Normalize raw collect records into flat dicts for detail aggregation."""
    tz = tz or datetime.now().astimezone().tzinfo
    out = []
    for r in records:
        dt = parse_ts_local(r.get("timestamp"), tz)
        if dt is None:
            continue
        toks = r.get("total_tokens") or 0
        if toks <= 0:
            continue
        out.append({
            "dt": dt,
            "model": r.get("model") or "unknown",
            "source": r.get("source") or "?",
            "project": r.get("project") or "",
            "tokens": toks,
            "input": r.get("input_tokens") or 0,
            "output": r.get("output_tokens") or 0,
            "crd": r.get("cache_read_tokens") or 0,
            "cwr": r.get("cache_write_tokens") or 0,
            "reason": r.get("reasoning_tokens") or 0,
            "cost": r.get("cost_usd"),
        })
    return out


def percentile(vals, p):
    """Nearest-rank percentile over an unsorted list."""
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return None
    return vals[max(0, min(n - 1, math.ceil(p / 100 * n) - 1))]


def log_bins(values, n=12):
    """Log-spaced histogram over positive values; None when the range is too narrow."""
    vals = sorted(v for v in values if v > 0)
    if len(vals) < 2:
        return None
    lo, hi = math.log10(vals[0]), math.log10(vals[-1])
    if hi - lo < 0.4:
        return None
    edges = [10 ** (lo + (hi - lo) * i / n) for i in range(n + 1)]
    counts = [0] * n
    for v in vals:
        counts[min(bisect.bisect_right(edges, v) - 1, n - 1)] += 1
    return edges, counts


def hist_chars(counts):
    m = max(counts) if counts else 0
    if m <= 0:
        return [BLOCKS[0]] * len(counts)
    return [BLOCKS[int(round(c * 8 / m))] for c in counts]


def aggregate_models(recs):
    by = {}
    for r in recs:
        m = by.setdefault(r["model"], {"reqs": 0, "tokens": 0, "cost": 0.0, "cost_known": False})
        m["reqs"] += 1
        m["tokens"] += r["tokens"]
        if r["cost"] is not None:
            m["cost"] += r["cost"]
            m["cost_known"] = True
    return by


def token_type_totals(recs):
    keys = ("input", "output", "crd", "cwr", "reason")
    by_src, totals = {}, {k: 0 for k in keys}
    for r in recs:
        s = by_src.setdefault(r["source"], {k: 0 for k in keys})
        for k in keys:
            s[k] += r[k]
            totals[k] += r[k]
    return by_src, totals


def cache_hit(crd, inp):
    denom = crd + inp
    return (crd / denom * 100) if denom > 0 else 0.0


def rhythm_buckets(recs):
    hourly, weekday = [0] * 24, [0] * 7
    for r in recs:
        hourly[r["dt"].hour] += r["tokens"]
        weekday[r["dt"].weekday()] += r["tokens"]
    return hourly, weekday


def aggregate_projects(recs):
    by = {}
    for r in recs:
        key = os.path.basename(r["project"]) if r["project"] else "(no project)"
        p = by.setdefault(key, {"reqs": 0, "tokens": 0})
        p["reqs"] += 1
        p["tokens"] += r["tokens"]
    return by


def detail_model_table(by_models, total_tokens, use_color, cap=12):
    rows = sorted(by_models.items(), key=lambda kv: -kv[1]["tokens"])
    table_rows = []
    for name, m in rows[:cap]:
        # keep the TAIL: the distinguishing part of a provider/model name is
        # the suffix (version/date), so front-truncate rather than back-truncate
        name = name if len(name) <= 34 else ".." + name[-(32):]
        share = m["tokens"] / total_tokens * 100 if total_tokens else 0
        cost = money(m["cost"]) if m["cost_known"] else "—"
        table_rows.append((name, fmt(m["reqs"]), fmt(m["tokens"]),
                           fmt(m["tokens"] / m["reqs"]), f"{share:.1f}%", cost))
    lines = _table(["MODEL", "REQS", "TOKENS", "AVG/REQ", "SHARE", "COST"],
                   table_rows, [34, 7, 10, 9, 7, 9], ["l", "r", "r", "r", "r", "r"], use_color)
    if len(rows) > cap:
        lines.append(c(f"  ⋯ +{len(rows) - cap} more models", DIM, use_color))
    return lines


def detail_request_stats(recs, use_color):
    toks = sorted(r["tokens"] for r in recs)
    line = "  ".join(
        f"{k} {fmt(v)}" for k, v in
        (("avg", sum(toks) / len(toks)), ("p50", percentile(toks, 50)),
         ("p90", percentile(toks, 90)), ("p99", percentile(toks, 99)), ("max", toks[-1]))
    )
    lines = [c("TOKENS PER REQUEST  " + line, DIM, use_color)]
    bins = log_bins(toks)
    if bins:
        edges, counts = bins
        lines.append("  " + "".join(hist_chars(counts)))
        lines.append(c(f"   sizes {fmt(edges[0])} .. {fmt(edges[-1])}", DIM, use_color))
    return lines


def detail_token_types(recs, use_color):
    keys = ("input", "output", "crd", "cwr", "reason")
    by_src, totals = token_type_totals(recs)
    rows = []
    for src in SOURCES:
        s = by_src.get(src)
        if not s or not any(s.values()):
            continue
        reason = "—" if src == "claude" else fmt(s["reason"])
        rows.append((src, *(fmt(s[k]) for k in keys[:4]), reason,
                     f"{cache_hit(s['crd'], s['input']):.0f}%"))
    if totals and any(totals.values()):
        rows.append(("TOTAL", *(fmt(totals[k]) for k in keys[:4]), fmt(totals["reason"]),
                     f"{cache_hit(totals['crd'], totals['input']):.0f}%"))
    return _table(["SOURCE", "INPUT", "OUTPUT", "CACHE-R", "CACHE-W", "REASON", "HIT"],
                  rows, [10, 9, 9, 9, 9, 9, 6], ["l", "r", "r", "r", "r", "r", "r"], use_color)


def detail_rhythm(recs, use_color):
    hourly, weekday = rhythm_buckets(recs)
    max_h, max_w = max(hourly) or 1, max(weekday) or 1
    lines = [c("ACTIVITY · tokens by hour (local)", BOLD, use_color)]
    for row in range(6):
        cells = []
        for col in range(4):
            h = row * 4 + col
            bar = BLOCKS[int(round(hourly[h] / max_h * 8))] * 10
            cells.append(f"{h:02d} {bar} {fmt(hourly[h])}")
        lines.append("  " + "  ".join(cells))
    lines.append(c("ACTIVITY · tokens by weekday (Mon..Sun)", BOLD, use_color))
    for i, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        bar = BLOCKS[int(round(weekday[i] / max_w * 8))] * 10
        lines.append(f"  {name} {bar} {fmt(weekday[i])}")
    return lines


def detail_projects(recs, total_tokens, use_color, cap=12):
    rows = sorted(aggregate_projects(recs).items(), key=lambda kv: -kv[1]["tokens"])
    table_rows = []
    for name, p in rows[:cap]:
        name = name if len(name) <= 28 else name[:25] + "..."
        share = p["tokens"] / total_tokens * 100 if total_tokens else 0
        table_rows.append((name, fmt(p["reqs"]), fmt(p["tokens"]),
                           fmt(p["tokens"] / p["reqs"]), f"{share:.1f}%"))
    lines = _table(["PROJECT", "REQS", "TOKENS", "AVG/REQ", "SHARE"],
                   table_rows, [30, 7, 10, 9, 7], ["l", "r", "r", "r", "r"], use_color)
    if len(rows) > cap:
        lines.append(c(f"  ⋯ +{len(rows) - cap} more projects", DIM, use_color))
    return lines


def run_detail(recs, label, use_color):
    total_tokens = sum(r["tokens"] for r in recs)
    print(c(f"MODELS · {label} · {fmt(len(recs))} requests · {fmt(total_tokens)} tokens", BOLD, use_color))
    for section in (detail_model_table(aggregate_models(recs), total_tokens, use_color),
                    detail_request_stats(recs, use_color),
                    detail_token_types(recs, use_color),
                    detail_rhythm(recs, use_color),
                    detail_projects(recs, total_tokens, use_color)):
        print("\n".join(section))
        print()


def main():
    ap = argparse.ArgumentParser(description="Stacked token-usage dashboard for all agents found in local logs")
    ap.add_argument("--period", choices=["daily", "weekly", "monthly"],
                    help="show one panel only (default: dashboard = all three)")
    ap.add_argument("--detail", action="store_true",
                    help="detail report (models, per-request stats, token types, activity, projects) "
                         "instead of the dashboard; --period scopes it to that window")
    ap.add_argument("--requests", action="store_true",
                    help="also show per-bucket request counts and count statistics")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI color")
    args = ap.parse_args()

    use_color = not args.no_color and sys.stdout.isatty()
    records = list(all_records())
    if not records:
        print("no token usage records found (checked Claude Code / pi / OpenCode logs)")
        sys.exit(1)

    parsed = parse_records(records)
    if args.detail:
        recs = parsed
        label = "all history"
        if args.period:
            _, desc, n = LONG[args.period]
            buckets = bucketize(records)
            span = buckets[args.period][-n:]
            if span:
                start = datetime(span[0][0].year, span[0][0].month, span[0][0].day)
                recs = [r for r in recs if r["dt"] >= start]
                label = f"{desc} (since {span[0][0].strftime('%m-%d')})"
        run_detail(recs, label, use_color)
        return

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