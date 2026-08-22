#!/usr/bin/env python3
"""toku — stacked token-usage dashboard for every agent found in local logs.

Aggregates the per-message token usage collected by collect_agent_usage.py
(Claude Code, pi, OpenCode — exactly the same parsers) into local-time
daily / weekly / monthly buckets, and renders each bucket as a bar stacked
by source: claude=cyan, pi=magenta, opencode=green.

Usage: toku.py [-p daily|weekly|monthly] [-d] [-c] [-r] [-v] [-n]
       toku.py [--period daily|weekly|monthly] [--detail] [--costs] [--refresh] [--verbose] [--requests] [--no-color]

Stdlib only; reuses collect_agent_usage's parsers and ocgo's display
helpers. Symlinked to ~/.local/bin/toku by setup.sh.
"""
import argparse
import bisect
import json
import math
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

import collect_agent_usage as cau
import ocgo
from ocgo import c, pad, money, _table, DIM, BOLD, CYAN, GREEN, YELLOW  # ocgo is import-safe (main() guarded)

try:
    import openrouter_pricing as orp  # type: ignore[import-not-found]
except ImportError:
    orp = None  # type: ignore[assignment]

MAGENTA = "\033[35m"

SOURCES = ["claude", "pi", "opencode", "antigravity"]
SRC_COLOR = {"claude": CYAN, "pi": MAGENTA, "opencode": GREEN, "antigravity": YELLOW}
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
    try:
        n = float(n or 0)
    except (ValueError, TypeError):
        return "0"
    if n >= 1e12:
        return f"{n / 1e12:.2f}T"
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    try:
        is_int = n == int(n)
    except Exception:
        return f"{n:.1f}"
    if not is_int:
        return f"{n:.1f}"
    try:
        return f"{int(n)}"
    except Exception:
        return f"{n:.1f}"


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


def bucketize_costs(parsed_recs, pricing_map, tz=None):
    """Cost buckets stacked by source, mirroring bucketize but summing USD."""
    daily, weekly, monthly = {}, {}, {}
    if orp is None or not pricing_map:
        return {"daily": [], "weekly": [], "monthly": []}
    for r in parsed_recs:
        dt = r.get("dt")
        if dt is None:
            continue
        try:
            cost = orp.estimate_cost(r, pricing_map)  # type: ignore[union-attr]
        except Exception:
            cost = None
        if cost is None:
            continue
        src = r.get("source")
        d = dt.date()
        for bucket, key in ((daily, d), (weekly, d - timedelta(days=d.weekday())), (monthly, d.replace(day=1))):
            cell = bucket.setdefault(key, {})
            entry = cell.setdefault(src, {"cost": 0.0, "msgs": 0})
            entry["cost"] += cost
            entry["msgs"] += 1
    return {"daily": sorted(daily.items()), "weekly": sorted(weekly.items()), "monthly": sorted(monthly.items())}


def period_totals_costs(parsed_recs, pricing_map, now, tz=None):
    """Cost totals since today/week/month."""
    totals = {k: {"cost": 0.0, "msgs": 0} for k in ("today", "week", "month")}
    if orp is None or not pricing_map:
        return totals
    now_naive = now.replace(tzinfo=None) if getattr(now, "tzinfo", None) else now
    try:
        starts = {
            "today": now_naive.replace(hour=0, minute=0, second=0, microsecond=0),
            "week": now_naive.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_naive.date().weekday()),
            "month": now_naive.replace(hour=0, minute=0, second=0, microsecond=0, day=1),
        }
    except Exception:
        return totals
    for r in parsed_recs:
        dt = r.get("dt")
        if dt is None:
            continue
        try:
            cost = orp.estimate_cost(r, pricing_map)  # type: ignore[union-attr]
        except Exception:
            continue
        if cost is None:
            continue
        for k, start in starts.items():
            try:
                if dt >= start:
                    totals[k]["cost"] += cost
                    totals[k]["msgs"] += 1
            except Exception:
                continue
    return totals


def panel_lines_cost(title, buckets, label_fn, bar_w, use_color, current_year=None):
    """Cost-stacked version of panel_lines (money formatting)."""
    totals = [
        {"anchor": a, "total": sum(e.get("cost", 0) for e in b.values()), "msgs": sum(e.get("msgs", 0) for e in b.values())}
        for a, b in buckets
    ]
    max_total = max((t["total"] for t in totals), default=0)
    lines = [c(title, BOLD, use_color)]
    if max_total:
        try:
            peak = max(totals, key=lambda t: t["total"])
            lines[0] += c(f"      peak {label_fn(peak['anchor'], current_year)} {money(peak['total'])}", DIM, use_color)
        except Exception:
            pass
    for (anchor, bucket), t in zip(buckets, totals):
        try:
            cells = render_bar([bucket.get(s, {}).get("cost", 0) for s in SOURCES], max_total, bar_w)
        except Exception:
            cells = [(" ", "")] * bar_w
        if not any(col for _, col in cells) and t["total"] > 0:
            cells[0] = ("▏", "")
        bar = "".join(c(ch, col, use_color) if col else (c(ch, DIM, use_color) if ch != " " else ch) for ch, col in cells)
        row = f"  {label_fn(anchor, current_year):<7} {bar}  {money(t['total']):>9}"
        if max_total and abs(t["total"] - max_total) < 1e-9:
            row += c("  ← peak", DIM, use_color)
        lines.append(row)
    if len(totals) >= 2:
        try:
            cols = shutil.get_terminal_size((120, 24)).columns
        except Exception:
            cols = 120
        vals = [t["total"] for t in totals]
        s = stats(vals)
        if s is not None:
            try:
                if cols < 70:
                    items = (("mean", s["mean"]), ("max", s["max"]))
                elif cols < 85:
                    items = (("mean", s["mean"]), ("median", s["median"]), ("max", s["max"]))
                else:
                    items = (("mean", s["mean"]), ("median", s["median"]), ("min", s["min"]), ("max", s["max"]), ("σ", s["std"]))
                stat_str = "  ".join(f"{k} {money(v)}" for k, v in items)
                if len("  stats  " + stat_str) > cols:
                    stat_str = stat_str[: max(0, cols - 12)] + "…"
                lines.append(c("  stats  " + stat_str, DIM, use_color))
            except Exception:
                pass
    return lines


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
        try:
            end = min(int(round(cur / max_total * (bar_w * 8))), bar_w * 8)
        except Exception:
            end = pos
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
        try:
            peak = max(totals, key=lambda t: t["total"])
            lines[0] += c(f"      peak {label_fn(peak['anchor'], current_year)} {fmt(peak['total'])}", DIM, use_color)
        except Exception:
            pass
    for (anchor, bucket), t in zip(buckets, totals):
        try:
            cells = render_bar([bucket.get(s, {}).get("tokens", 0) for s in SOURCES], max_total, bar_w)
        except Exception:
            cells = [(" ", "")] * bar_w
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
        # responsive stats: on narrow terminals (<70 cols) show fewer items to avoid wrap
        try:
            cols = shutil.get_terminal_size((120, 24)).columns
        except Exception:
            cols = 120
        s = stats([t["total"] for t in totals])
        if s is not None:
            # choose stats items based on available width
            if cols < 70:
                items = (("mean", s["mean"]), ("max", s["max"]))
            elif cols < 85:
                items = (("mean", s["mean"]), ("median", s["median"]), ("max", s["max"]))
            else:
                items = (("mean", s["mean"]), ("median", s["median"]), ("min", s["min"]), ("max", s["max"]), ("σ", s["std"]))
            stat_str = "  ".join(f"{k} {fmt(v)}" for k, v in items)
            # final guard: if still too long, truncate with …
            if len("  stats  " + stat_str) > cols:
                stat_str = stat_str[: max(0, cols - 12)] + "…"
            lines.append(c("  stats  " + stat_str, DIM, use_color))
        if counts:
            m = stats([t["msgs"] for t in totals])
            if m is not None:
                if cols < 70:
                    mitems = (("mean", m["mean"]), ("max", m["max"]))
                elif cols < 85:
                    mitems = (("mean", m["mean"]), ("median", m["median"]), ("max", m["max"]))
                else:
                    mitems = (("mean", m["mean"]), ("median", m["median"]), ("min", m["min"]), ("max", m["max"]), ("σ", m["std"]))
                mstr = "  ".join(f"{k} {fmt(v)}" for k, v in mitems)
                if len("         " + mstr) > cols:
                    mstr = mstr[: max(0, cols - 12)] + "…"
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
    out = []
    for cc in counts:
        try:
            idx = int(round(cc * 8 / m))
        except Exception:
            idx = 0
        idx = max(0, min(8, idx))
        out.append(BLOCKS[idx])
    return out


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


def aggregate_models_estimated(recs, pricing_map):
    """Aggregate with OpenRouter-estimated cost for every record.

    Returns (by_model, unmapped_set). When a model has no pricing, its
    cost_known stays False → shown as — in the table (best-effort skip).
    """
    by = {}
    unmapped: set[str] = set()
    if orp is None or not pricing_map:
        for r in recs:
            m = by.setdefault(r["model"], {"reqs": 0, "tokens": 0, "cost": 0.0, "cost_known": False})
            m["reqs"] += 1
            m["tokens"] += r["tokens"]
            unmapped.add(r["model"])
        return by, unmapped
    for r in recs:
        est = orp.estimate_cost(r, pricing_map)  # type: ignore[union-attr]
        m = by.setdefault(r["model"], {"reqs": 0, "tokens": 0, "cost": 0.0, "cost_known": False})
        m["reqs"] += 1
        m["tokens"] += r["tokens"]
        if est is not None:
            m["cost"] += est
            m["cost_known"] = True
        else:
            unmapped.add(r["model"])
    return by, unmapped


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


def detail_model_table(by_models, total_tokens, use_color, cap=12, estimated=False):
    rows = sorted(by_models.items(), key=lambda kv: -kv[1]["tokens"])
    # responsive: shrink MODEL column on narrow terminals, drop AVG/REQ first
    cols = shutil.get_terminal_size((120, 24)).columns
    # cost column needs 10 to fit "$1061.1043" (was 9, overflow by 1 for >$1000)
    # base other widths without MODEL: REQS 7, TOKENS 10, AVG 9, SHARE 7, COST 10 + seps
    base_other = 7 + 10 + 9 + 7 + 10 + 5 * 2 + 2  # 55
    avail_model = cols - base_other
    headers = ["MODEL", "REQS", "TOKENS", "AVG/REQ", "SHARE", "EST COST" if estimated else "COST"]
    widths = [34, 7, 10, 9, 7, 10]
    aligns = ["l", "r", "r", "r", "r", "r"]
    # truncate with … on narrow: drop AVG/REQ if needed, then SHARE
    if avail_model < 14:
        # drop AVG/REQ (index 3)
        headers = [headers[0], headers[1], headers[2], headers[4], headers[5]]
        widths = [widths[0], widths[1], widths[2], widths[4], widths[5]]
        aligns = [aligns[0], aligns[1], aligns[2], aligns[4], aligns[5]]
        base_other = 7 + 10 + 7 + 10 + 4 * 2 + 2  # 44
        avail_model = cols - base_other
    if avail_model < 14:
        # drop SHARE as well (now index 3)
        headers = [headers[0], headers[1], headers[2], headers[4]]
        widths = [widths[0], widths[1], widths[2], widths[4]]
        aligns = [aligns[0], aligns[1], aligns[2], aligns[4]]
        base_other = 7 + 10 + 10 + 3 * 2 + 2  # 35
        avail_model = cols - base_other
    model_w = max(14, min(34, avail_model))
    # final guard: if still too wide due to rounding, shrink model by 1
    while model_w + base_other > cols and model_w > 12:
        model_w -= 1
    widths[0] = model_w
    table_rows = []
    for name, m in rows[:cap]:
        # keep the TAIL: the distinguishing part is the suffix
        if len(name) > model_w:
            # use … (single char) + tail, keep within width
            keep = max(0, model_w - 1)
            name = "…" + name[-keep:] if keep > 0 else name[:model_w]
        share = m["tokens"] / total_tokens * 100 if total_tokens else 0
        cost = money(m["cost"]) if m["cost_known"] else "—"
        if len(headers) == 6:
            table_rows.append((name, fmt(m["reqs"]), fmt(m["tokens"]),
                               fmt(m["tokens"] / m["reqs"]), f"{share:.1f}%", cost))
        elif len(headers) == 5:
            table_rows.append((name, fmt(m["reqs"]), fmt(m["tokens"]),
                               f"{share:.1f}%", cost))
        else:
            table_rows.append((name, fmt(m["reqs"]), fmt(m["tokens"]), cost))
    lines = _table(headers, table_rows, widths, aligns, use_color)
    if len(rows) > cap:
        lines.append(c(f"  ⋯ +{len(rows) - cap} more models", DIM, use_color))
    return lines


def detail_request_stats(recs, use_color, bar_w=None):
    toks = sorted(r["tokens"] for r in recs)
    try:
        avg_line = sum(toks) / len(toks) if toks else 0
    except Exception:
        avg_line = 0
    try:
        cols = shutil.get_terminal_size((120, 24)).columns
    except Exception:
        cols = 120
    # responsive header: on narrow (<70 cols) show only 3 stats to avoid wrap
    if cols < 65:
        items = (("avg", avg_line), ("p50", percentile(toks, 50)), ("max", toks[-1] if toks else 0))
    elif cols < 80:
        items = (("avg", avg_line), ("p50", percentile(toks, 50)), ("p90", percentile(toks, 90)), ("max", toks[-1] if toks else 0))
    else:
        items = (("avg", avg_line), ("p50", percentile(toks, 50)), ("p90", percentile(toks, 90)), ("p99", percentile(toks, 99)), ("max", toks[-1] if toks else 0))
    line = "  ".join(f"{k} {fmt(v)}" for k, v in items)
    header = "TOKENS PER REQUEST  " + line
    # final guard: if still too long, truncate
    if len(header) > cols:
        header = header[: max(0, cols - 1)] + "…" if cols > 10 else header[:cols]
    lines = [c(header, DIM, use_color)]
    # widen histogram to bar width (full redesign: use terminal width)
    if bar_w is None:
        try:
            bar_w = max(12, min(64, shutil.get_terminal_size((120, 24)).columns - 30))
        except Exception:
            bar_w = 32
    # use more bins when wide, keep 12 minimum
    try:
        n_bins = max(12, min(32, bar_w // 2 + 2))
    except Exception:
        n_bins = 12
    bins = log_bins(toks, n=n_bins)
    if bins:
        edges, counts = bins
        hist = "".join(hist_chars(counts))
        # stretch hist to bar_w by repeating each bin block
        try:
            if len(hist) < bar_w and len(hist) > 0:
                # repeat each char to fill width: scale = bar_w // len(hist)
                scale = max(1, bar_w // len(hist))
                hist = "".join(ch * scale for ch in hist)[:bar_w]
        except Exception:
            pass
        lines.append("  " + hist)
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
    # responsive widths: shrink numeric cols on narrow terminals to avoid wrap
    try:
        cols = shutil.get_terminal_size((120, 24)).columns
    except Exception:
        cols = 120
    if cols < 65:
        widths = [8, 6, 6, 6, 6, 6, 4]
    elif cols < 80:
        widths = [9, 7, 7, 7, 7, 7, 5]
    else:
        widths = [10, 9, 9, 9, 9, 9, 6]
    return _table(["SOURCE", "INPUT", "OUTPUT", "CACHE-R", "CACHE-W", "REASON", "HIT"],
                  rows, widths, ["l", "r", "r", "r", "r", "r", "r"], use_color)


def detail_rhythm(recs, use_color):
    hourly, weekday = rhythm_buckets(recs)
    max_h, max_w = max(hourly) or 1, max(weekday) or 1
    cols = shutil.get_terminal_size((120, 24)).columns
    # responsive: compute bar length and cols per row from terminal width
    # per-cell: "HH " (3) + bar (bar_len) + " " (1) + fmt (~6) = 10+bar_len
    bar_len = 10
    # keep bar_len 10 on wide, shrink to 6 on narrow to avoid wrap
    if cols < 80:
        bar_len = 6
    elif cols < 100:
        bar_len = 8
    per_cell = 3 + bar_len + 1 + 7  # ~21 for bar_len 10
    avail = cols - 2  # indent
    cols_per_row = max(1, min(4, avail // (per_cell + 2)))
    lines = [c("ACTIVITY · tokens by hour (local)", BOLD, use_color)]
    # variable-length bars: filled proportion of bar_len
    for row in range((24 + cols_per_row - 1) // cols_per_row):
        cells = []
        for col in range(cols_per_row):
            h = row * cols_per_row + col
            if h >= 24:
                break
            try:
                filled = int(round(hourly[h] / max_h * bar_len)) if max_h else 0
            except Exception:
                filled = 0
            filled = max(0, min(bar_len, filled))
            # use █ for filled, ░ for remainder; color DIM for empty part when use_color
            bar_filled = "█" * filled
            bar_empty = "░" * (bar_len - filled)
            if use_color:
                # filled part keeps default, empty part DIM
                bar = bar_filled + c(bar_empty, DIM, True) if bar_empty else bar_filled
            else:
                bar = bar_filled + bar_empty
                # without color, empty part still visible as ░
                # keep length fixed
            cells.append(f"{h:02d} {bar} {fmt(hourly[h]):>6}")
        lines.append("  " + "  ".join(cells))
    lines.append(c("ACTIVITY · tokens by weekday (Mon..Sun)", BOLD, use_color))
    # weekday: one per line is more readable than inline; keep 1-per-line to avoid overflow
    for i, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        try:
            filled = int(round(weekday[i] / max_w * bar_len)) if max_w else 0
        except Exception:
            filled = 0
        filled = max(0, min(bar_len, filled))
        bar_filled = "█" * filled
        bar_empty = "░" * (bar_len - filled)
        bar = bar_filled + (c(bar_empty, DIM, use_color) if use_color and bar_empty else bar_empty)
        lines.append(f"  {name} {bar} {fmt(weekday[i]):>7}")
    return lines


def detail_projects(recs, total_tokens, use_color, cap=12):
    rows = sorted(aggregate_projects(recs).items(), key=lambda kv: -kv[1]["tokens"])
    cols = shutil.get_terminal_size((120, 24)).columns
    # responsive project name width
    other = 7 + 10 + 9 + 7 + 4 * 2 + 2  # REQS/TOKENS/AVG/SHARE + seps + indent
    proj_w = max(12, min(30, cols - other))
    table_rows = []
    for name, p in rows[:cap]:
        if len(name) > proj_w:
            # front-truncate preserving tail, use …
            keep = max(0, proj_w - 1)
            name = "…" + name[-keep:] if keep > 0 else name[:proj_w]
        share = p["tokens"] / total_tokens * 100 if total_tokens else 0
        table_rows.append((name, fmt(p["reqs"]), fmt(p["tokens"]),
                           fmt(p["tokens"] / p["reqs"]), f"{share:.1f}%"))
    lines = _table(["PROJECT", "REQS", "TOKENS", "AVG/REQ", "SHARE"],
                   table_rows, [proj_w, 7, 10, 9, 7], ["l", "r", "r", "r", "r"], use_color)
    if len(rows) > cap:
        lines.append(c(f"  ⋯ +{len(rows) - cap} more projects", DIM, use_color))
    return lines


def run_detail(recs, label, use_color, estimated=False, pricing_map=None, verbose=False, source=""):
    total_tokens = sum(r["tokens"] for r in recs)
    # histogram should stretch to terminal width
    try:
        cols = shutil.get_terminal_size((120, 24)).columns
        bar_w_hist = max(12, min(64, cols - 30))
    except Exception:
        cols = 120
        bar_w_hist = 32
    if estimated:
        by_models, unmapped = aggregate_models_estimated(recs, pricing_map or {})
        total_cost = sum(m["cost"] for m in by_models.values() if m["cost_known"])
        cost_str = money(total_cost) if total_cost else "—"
        cache_note = f" · {source}" if verbose and source else ""
        # responsive headline: on narrow (<70) drop request count to save ~15 chars
        if cols < 70:
            head = f"MODELS · {label} · {fmt(total_tokens)} tokens · {cost_str} est{cache_note}"
        else:
            head = f"MODELS · {label} · {fmt(len(recs))} requests · {fmt(total_tokens)} tokens · {cost_str} est{cache_note}"
        if len(head) > cols:
            # truncate label if still too long (e.g. verbose cache note)
            head = head[: max(0, cols - 1)] + "…" if cols > 10 else head[:cols]
        print(c(head, BOLD, use_color))
        if unmapped and verbose:
            sample = ", ".join(sorted(unmapped)[:5])
            more = f" +{len(unmapped)-5} more" if len(unmapped) > 5 else ""
            print(c(f"  unmapped {len(unmapped)} models: {sample}{more} (no OpenRouter pricing)", DIM, use_color))
        for section in (detail_model_table(by_models, total_tokens, use_color, estimated=True),
                        detail_request_stats(recs, use_color, bar_w=bar_w_hist),
                        render_quotas_panel(quota_window_tokens(recs), use_color),
                        detail_token_types(recs, use_color),
                        detail_rhythm(recs, use_color),
                        detail_projects(recs, total_tokens, use_color)):
            print("\n".join(section))
            print()
        return
    # non-estimated headline also responsive
    if cols < 70:
        head2 = f"MODELS · {label} · {fmt(total_tokens)} tokens"
    else:
        head2 = f"MODELS · {label} · {fmt(len(recs))} requests · {fmt(total_tokens)} tokens"
    if len(head2) > cols:
        head2 = head2[: max(0, cols - 1)] + "…" if cols > 10 else head2[:cols]
    print(c(head2, BOLD, use_color))
    for section in (detail_model_table(aggregate_models(recs), total_tokens, use_color),
                    detail_request_stats(recs, use_color, bar_w=bar_w_hist),
                    render_quotas_panel(quota_window_tokens(recs), use_color),
                    detail_token_types(recs, use_color),
                    detail_rhythm(recs, use_color),
                    detail_projects(recs, total_tokens, use_color)):
        print("\n".join(section))
        print()


AGY_QUOTA_CACHE = os.path.expanduser("~/.antigravity/quota-cache.json")

QUOTA_CONFIGS = [
    ("claude", 5, 288_000_000, "Claude 5h (Opus 2x)"),
    ("claude", 24 * 7, 2_140_000_000, "Claude 7d (+50% promo)"),
    ("antigravity", 5, 300_000_000, "AGY 5h (Flash 3.7)"),
    ("antigravity", 24 * 7, 1_000_000_000, "AGY 7d (Weekly 1B)"),
]


def load_agy_live_quota() -> dict | None:
    if not os.path.isfile(AGY_QUOTA_CACHE):
        return None
    try:
        with open(AGY_QUOTA_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
            models = data.get("models") or {}
            target = models.get("gemini37flashmedium") or models.get("gemini37flashhigh")
            if not target:
                for k, v in models.items():
                    if "flash" in k.lower():
                        target = v
                        break
            if not target and models:
                target = next(iter(models.values()))
            if target:
                return {
                    "name": target.get("name") or "Flash 3.7",
                    "remaining_pct": float(target.get("remaining_percentage", 100.0)),
                    "refreshes_in": target.get("refreshes_in") or "",
                    "reset_time": target.get("reset_time") or "",
                }
    except Exception:
        return None
    return None


def agy_weekly_reset_start(now_dt: datetime) -> datetime:
    """Antigravity weekly limit resets weekly on Friday at 16:30 UTC (19:30 TRT).
    Returns the naive local datetime when the current weekly cycle began.
    """
    now_utc = now_dt.astimezone(timezone.utc) if getattr(now_dt, "tzinfo", None) else now_dt
    days_since_friday = (now_utc.weekday() - 4) % 7
    candidate = (now_utc - timedelta(days=days_since_friday)).replace(hour=16, minute=30, second=0, microsecond=0)
    if candidate > now_utc:
        candidate -= timedelta(days=7)
    local_tz = datetime.now().astimezone().tzinfo
    return candidate.replace(tzinfo=timezone.utc).astimezone(local_tz).replace(tzinfo=None)


def claude_weekly_reset_start(now_dt: datetime) -> datetime:
    """Claude weekly limit resets weekly on Thursday at 01:59 TRT (Wednesday 22:59 UTC).
    Returns the naive local datetime when the current weekly cycle began.
    """
    now_utc = now_dt.astimezone(timezone.utc) if getattr(now_dt, "tzinfo", None) else now_dt
    days_since_wed = (now_utc.weekday() - 2) % 7
    candidate = (now_utc - timedelta(days=days_since_wed)).replace(hour=22, minute=59, second=0, microsecond=0)
    if candidate > now_utc:
        candidate -= timedelta(days=7)
    local_tz = datetime.now().astimezone().tzinfo
    return candidate.replace(tzinfo=timezone.utc).astimezone(local_tz).replace(tzinfo=None)


def format_compact_td(td) -> str:
    if not td or td.total_seconds() <= 0:
        return ""
    total_secs = int(td.total_seconds())
    days = total_secs // 86400
    hours = (total_secs % 86400) // 3600
    mins = (total_secs % 3600) // 60
    if days > 0:
        return f"{days}d{hours}h" if hours > 0 else f"{days}d"
    if hours > 0:
        return f"{hours}h{mins}m" if mins > 0 else f"{hours}h"
    return f"{max(1, mins)}m"


def quota_window_tokens(recs, now=None, tz=None, include_ocgo=True):
    """Compute token usage in rolling 5h and weekly cycles for Claude & Antigravity,
    and fetch live OpenCode Go subscription windows if reachable.

    Claude: tracks USED tokens against capacity (Opus counts 2.0x).
    Antigravity: tracks REMAINING allowance out of 5h (300M) and weekly cycle (1.00B) caps + live cache.
    OpenCode Go: tracks REMAINING percentage across rolling, weekly, monthly from live API.
    """
    local_tz = tz or datetime.now().astimezone().tzinfo
    now_dt = now or datetime.now(local_tz)
    now_naive = now_dt.replace(tzinfo=None) if getattr(now_dt, "tzinfo", None) else now_dt

    res = {}
    for src, hours, limit, label in QUOTA_CONFIGS:
        if src == "antigravity" and hours == 24 * 7:
            cutoff = agy_weekly_reset_start(now_naive)
        elif src == "claude" and hours == 24 * 7:
            cutoff = claude_weekly_reset_start(now_naive)
        else:
            cutoff = now_naive - timedelta(hours=hours)
        used = 0
        earliest_inside = None
        for r in recs:
            if r.get("source") != src:
                continue
            dt = r.get("dt")
            if dt is None or dt < cutoff:
                continue
            if earliest_inside is None or dt < earliest_inside:
                earliest_inside = dt
            tok = r.get("tokens") or 0
            if src == "claude" and "opus" in (r.get("model") or "").lower():
                tok *= 2
            used += tok
        used_pct = (used / limit * 100) if limit > 0 else 0.0
        remaining_pct = max(0.0, 100.0 - used_pct)
        resets_in = ""
        if hours == 24 * 7:
            next_reset = cutoff + timedelta(days=7)
            if next_reset > now_naive:
                resets_in = format_compact_td(next_reset - now_naive)
        elif earliest_inside and used > 0:
            drop_off = earliest_inside + timedelta(hours=hours)
            if drop_off > now_naive:
                resets_in = format_compact_td(drop_off - now_naive)
        res[label] = {
            "source": src,
            "hours": hours,
            "limit": limit,
            "used": used,
            "used_pct": used_pct,
            "remaining_pct": remaining_pct,
            "resets_in": resets_in,
            "label": label,
            "mode": "used" if src == "claude" else "remaining",
        }

    agy_live = load_agy_live_quota()
    if agy_live and "AGY 5h (Flash 3.7)" in res:
        res["AGY 5h (Flash 3.7)"]["live"] = agy_live
        if agy_live.get("refreshes_in"):
            res["AGY 5h (Flash 3.7)"]["resets_in"] = agy_live["refreshes_in"]

    if include_ocgo:
        try:
            oc_usage = ocgo.fetch_windows()
            if oc_usage:
                for wkey, wlabel in ocgo.WINDOWS:
                    wdata = oc_usage.get(wkey) or {}
                    if wdata.get("status") == "ok":
                        used_p = float(wdata.get("percent", 0))
                        rem_p = 100.0 - used_p
                        res[f"OC Go {wlabel}"] = {
                            "source": "opencode",
                            "used_pct": used_p,
                            "remaining_pct": rem_p,
                            "resets_in": ocgo.countdown(wdata.get("resetsAt")),
                            "label": f"OC Go {wlabel}",
                            "mode": "remaining",
                            "is_live_ocgo": True,
                        }
        except Exception:
            pass

    return res


def render_quotas_panel(quotas, use_color, bar_w=20):
    lines = [c("QUOTA WINDOWS (Rolling)", BOLD, use_color)]
    for label, q in quotas.items():
        src = q.get("source", "")
        mode = q.get("mode", "used")
        col = SRC_COLOR.get(src, CYAN)

        if q.get("is_live_ocgo"):
            rem_p = q["remaining_pct"]
            used_p = q["used_pct"]
            countdown_str = f" · in {q['resets_in']}" if q.get("resets_in") else ""
            fill_units = max(0, min(int(round(rem_p / 100 * bar_w)), bar_w))
            bar_glyph = c("█" * fill_units, ocgo.color_for(rem_p), use_color) + c("░" * (bar_w - fill_units), DIM, use_color)
            warn = ""
            if rem_p <= 5:
                warn = c("  🚨 LOW QUOTA", "\033[91m", use_color)
            elif rem_p <= 20:
                warn = c("  ⚠️ WARNING", "\033[93m", use_color)
            info = f"{rem_p:>5.1f}% left ({int(used_p)}% used{countdown_str})"
            lines.append(f"  {label:<24} {bar_glyph}  {info:<35}{warn}")
        elif mode == "remaining":
            rem_p = q["remaining_pct"]
            used = q["used"]
            limit = q["limit"]
            live_note = ""
            if q.get("live"):
                live_note = f" · live {q['live']['remaining_pct']:.1f}%"
            resets_note = f" · in {q['resets_in']}" if q.get("resets_in") else ""
            fill_units = max(0, min(int(round(rem_p / 100 * bar_w)), bar_w))
            bar_glyph = c("█" * fill_units, col, use_color) + c("░" * (bar_w - fill_units), DIM, use_color)
            warn = ""
            if rem_p <= 2.0:
                warn = c("  🚨 LOW QUOTA", "\033[91m", use_color)
            elif rem_p <= 15.0:
                warn = c("  ⚠️ WARNING", "\033[93m", use_color)
            info = f"{rem_p:>5.1f}% left ({fmt(used)} / {fmt(limit)} used{live_note}{resets_note})"
            lines.append(f"  {label:<24} {bar_glyph}  {info:<35}{warn}")
        else:
            used = q["used"]
            limit = q["limit"]
            rem_p = max(0.0, 100.0 - q["used_pct"])
            used_p = q["used_pct"]
            resets_note = f" · in {q['resets_in']}" if q.get("resets_in") else ""
            fill_units = max(0, min(int(round(rem_p / 100 * bar_w)), bar_w))
            bar_glyph = c("█" * fill_units, col, use_color) + c("░" * (bar_w - fill_units), DIM, use_color)
            warn = ""
            if rem_p <= 5.0:
                warn = c("  🚨 LOW QUOTA", "\033[91m", use_color)
            elif rem_p <= 20.0:
                warn = c("  ⚠️ WARNING", "\033[93m", use_color)
            info = f"{rem_p:>5.1f}% left ({fmt(used)} / {fmt(limit)} used{resets_note})"
            lines.append(f"  {label:<24} {bar_glyph}  {info:<35}{warn}")
    return lines


DEFAULT_QUOTA_CACHE_PATH = os.path.expanduser("~/.cache/toku/quotas.json")


def format_quotas_dict(quotas, now=None) -> dict:
    now_dt = now or datetime.now(timezone.utc)
    ts_iso = now_dt.isoformat() if hasattr(now_dt, "isoformat") else str(now_dt)
    ts_epoch = int(now_dt.timestamp()) if hasattr(now_dt, "timestamp") else int(datetime.now().timestamp())

    out = {
        "updated_at": ts_iso,
        "timestamp": ts_epoch,
        "harnesses": {},
    }

    # Claude
    c_5h = quotas.get("Claude 5h (Opus 2x)")
    c_7d = quotas.get("Claude 7d (+50% promo)") or quotas.get("Claude 7d (Opus 2x)")
    if c_5h or c_7d:
        c_dict = {"mode": "remaining"}
        if c_5h:
            c_dict["session_used"] = c_5h["used"]
            c_dict["session_limit"] = c_5h["limit"]
            c_dict["session_pct"] = round(c_5h["used_pct"], 1)
            rem_5h = max(0.0, round(100.0 - c_5h["used_pct"], 1))
            c_dict["session_remaining_pct"] = rem_5h
            c_dict["session_warn"] = rem_5h <= 20.0
            c_dict["session_display"] = f"{int(round(rem_5h))}% left"
            if c_5h.get("resets_in"):
                c_dict["session_resets_in"] = c_5h["resets_in"]
        if c_7d:
            c_dict["week_used"] = c_7d["used"]
            c_dict["week_limit"] = c_7d["limit"]
            c_dict["week_pct"] = round(c_7d["used_pct"], 1)
            rem_7d = max(0.0, round(100.0 - c_7d["used_pct"], 1))
            c_dict["week_remaining_pct"] = rem_7d
            c_dict["week_warn"] = rem_7d <= 20.0
            c_dict["week_display"] = f"{int(round(rem_7d))}% left"
            if c_7d.get("resets_in"):
                c_dict["week_resets_in"] = c_7d["resets_in"]
        out["harnesses"]["claude"] = c_dict

    # Antigravity
    agy_5h = quotas.get("AGY 5h (Flash 3.7)")
    agy_7d = quotas.get("AGY 7d (Weekly 1B)")
    if agy_5h or agy_7d:
        a_dict = {"mode": "remaining"}
        if agy_5h:
            a_dict["session_used"] = agy_5h["used"]
            a_dict["session_limit"] = agy_5h["limit"]
            a_dict["session_remaining_pct"] = round(agy_5h["remaining_pct"], 1)
            a_dict["session_warn"] = agy_5h["remaining_pct"] <= 15.0
            a_dict["session_display"] = f"{int(round(agy_5h['remaining_pct']))}% left"
            res_5h = agy_5h.get("live", {}).get("refreshes_in") or agy_5h.get("resets_in")
            if res_5h:
                a_dict["session_resets_in"] = res_5h
        if agy_7d:
            a_dict["week_used"] = agy_7d["used"]
            a_dict["week_limit"] = agy_7d["limit"]
            a_dict["week_remaining_pct"] = round(agy_7d["remaining_pct"], 1)
            a_dict["week_warn"] = agy_7d["remaining_pct"] <= 15.0
            a_dict["week_display"] = f"{int(round(agy_7d['remaining_pct']))}% left"
            if agy_7d.get("resets_in"):
                a_dict["week_resets_in"] = agy_7d["resets_in"]
        out["harnesses"]["antigravity"] = a_dict

    # OpenCode Go
    oc_roll = quotas.get("OC Go 5h rolling")
    oc_week = quotas.get("OC Go weekly")
    oc_month = quotas.get("OC Go monthly")
    if oc_roll or oc_week or oc_month:
        o_dict = {"mode": "remaining"}
        if oc_roll:
            o_dict["session_pct"] = round(oc_roll["used_pct"], 1)
            o_dict["session_remaining_pct"] = round(oc_roll["remaining_pct"], 1)
            o_dict["session_display"] = f"{int(round(oc_roll['remaining_pct']))}% left"
            if oc_roll.get("resets_in"):
                o_dict["session_resets_in"] = oc_roll["resets_in"]
        if oc_week:
            o_dict["week_pct"] = round(oc_week["used_pct"], 1)
            o_dict["week_remaining_pct"] = round(oc_week["remaining_pct"], 1)
            o_dict["week_warn"] = oc_week["remaining_pct"] <= 20.0
            o_dict["week_display"] = f"{int(round(oc_week['remaining_pct']))}% left"
            if oc_week.get("resets_in"):
                o_dict["week_resets_in"] = oc_week["resets_in"]
        if oc_month:
            o_dict["month_pct"] = round(oc_month["used_pct"], 1)
            o_dict["month_remaining_pct"] = round(oc_month["remaining_pct"], 1)
            o_dict["month_display"] = f"{int(round(oc_month['remaining_pct']))}% left"
            if oc_month.get("resets_in"):
                o_dict["month_resets_in"] = oc_month["resets_in"]
        out["harnesses"]["opencode"] = o_dict

    return out


def export_quota_cache(quotas, path=None, now=None) -> str:
    target_path = path or DEFAULT_QUOTA_CACHE_PATH
    data = format_quotas_dict(quotas, now=now)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    tmp_path = target_path + f".tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, target_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    return target_path


def main():
    ap = argparse.ArgumentParser(description="Stacked token-usage dashboard for all agents found in local logs")
    ap.add_argument("-p", "--period", choices=["daily", "weekly", "monthly"],
                    help="show one panel only (default: dashboard = all three)")
    ap.add_argument("-d", "--detail", action="store_true",
                    help="detail report (models, per-request stats, token types, activity, projects) "
                         "instead of the dashboard; --period scopes it to that window")
    ap.add_argument("-c", "--costs", action="store_true",
                    help="estimate costs via OpenRouter pricing (cached 24h XDG cache; "
                         "in detail shows EST COST, in dashboard shows cost-stacked bars; "
                         "always estimates, ignores logged cost)")
    ap.add_argument("-r", "--refresh", action="store_true",
                    help="force refresh OpenRouter pricing cache (use with --costs/-c)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="verbose pricing fetch and unmapped models (use with --costs/-c)")
    ap.add_argument("-j", "--json", action="store_true",
                    help="output current quota status as JSON and exit (for Herdr / statusline integration)")
    ap.add_argument("-o", "--ocgo", action="store_true",
                    help="show OpenCode Go subscription windows and 'who-ate-it' traffic report (from ocgo)")
    ap.add_argument("-w", "--window",
                    type=ocgo.window_type, metavar="W",
                    help="window for --ocgo report: r|w|m or rolling|weekly|monthly (default: rolling)")
    ap.add_argument("--requests", action="store_true",
                    help="also show per-bucket request counts and count statistics")
    ap.add_argument("-n", "--no-color", action="store_true", help="disable ANSI color")
    args = ap.parse_args()

    use_color = not args.no_color and sys.stdout.isatty()

    if args.ocgo:
        usage = ocgo.fetch_windows()
        records = ocgo.load_paid_records()
        if not records:
            print("no 'opencode-go' traffic found in local opencode.db")
            return
        ocgo.print_windows(usage, use_color)
        picked = [args.window] if args.window else (list(dict(ocgo.WINDOWS).keys()) if args.detail else ["rolling"])
        ocgo.run_report(records, usage, args.detail, picked, use_color)
        return

    estimated = bool(args.costs)
    if args.refresh and not estimated:
        print("[toku] --refresh only applies with --costs", file=sys.stderr)
    records = list(all_records())
    if not records:
        print("no token usage records found (checked Claude Code / pi / OpenCode logs)")
        sys.exit(1)

    parsed = parse_records(records)
    now = datetime.now()
    quotas = quota_window_tokens(parsed, now)
    export_quota_cache(quotas, now=now)

    if args.json:
        print(json.dumps(format_quotas_dict(quotas, now=now), indent=2))
        return

    # fetch pricing once if needed (detail or dashboard)
    pricing_map = None
    pricing_source = ""
    if estimated:
        if orp is None:
            print("[toku] openrouter_pricing module missing — costs will show —", file=sys.stderr)
        else:
            pricing_map, pricing_source = orp.get_pricing(refresh=bool(args.refresh), verbose=bool(args.verbose))  # type: ignore[union-attr]
            if pricing_source == "none" or not pricing_map:
                # fallback to token-only if no pricing
                pass

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
        if estimated and pricing_map:
            run_detail(recs, label, use_color, estimated=True, pricing_map=pricing_map, verbose=bool(args.verbose), source=pricing_source)
        elif estimated:
            run_detail(recs, label, use_color)
        else:
            run_detail(recs, label, use_color)
        return

    # dashboard mode (token bars, plus cost bars when --costs)
    buckets = bucketize(records)
    now = datetime.now()
    totals = period_totals(records, now)
    cols = shutil.get_terminal_size((120, 24)).columns
    # responsive headlines: on narrow (<70) drop TOTAL prefix to save 15 chars
    if cols < 70:
        head = f"today {fmt(totals['today']['tokens'])} · week {fmt(totals['week']['tokens'])} · month {fmt(totals['month']['tokens'])}"
    else:
        head = f"TOTAL TOKENS   today {fmt(totals['today']['tokens'])} · this week {fmt(totals['week']['tokens'])} · this month {fmt(totals['month']['tokens'])}"
    # final guard: truncate if still too long (e.g. 60 cols with long numbers)
    if len(head) > cols:
        head = head[: max(0, cols - 1)] + "…" if cols > 10 else head[:cols]
    print(c(head, BOLD, use_color))
    if estimated and pricing_map:
        cost_totals = period_totals_costs(parsed, pricing_map, now)
        if cols < 70:
            cost_head = f"cost  today {money(cost_totals['today']['cost'])} · week {money(cost_totals['week']['cost'])} · month {money(cost_totals['month']['cost'])}"
        else:
            cost_head = f"TOTAL COST     today {money(cost_totals['today']['cost'])} · this week {money(cost_totals['week']['cost'])} · this month {money(cost_totals['month']['cost'])}"
        if args.verbose and pricing_source:
            # only append cache note if it still fits, else omit to avoid wrap
            note = f"  ({pricing_source})"
            if len(cost_head + note) <= cols:
                cost_head += c(note, DIM, use_color)
        if len(cost_head) > cols:
            # strip ANSI for length check: approximate
            cost_head = cost_head[: max(0, cols - 1)] + "…" if cols > 10 else cost_head[:cols]
        print(c(cost_head, BOLD, use_color))
    if args.requests:
        req = (f"REQUESTS       today {fmt(totals['today']['msgs'])} · this week {fmt(totals['week']['msgs'])}"
               f" · this month {fmt(totals['month']['msgs'])}")
        print(c(req, BOLD, use_color))
    print()

    cols = shutil.get_terminal_size((120, 24)).columns
    bar_w = max(12, min(64, cols - (42 if args.requests else 30)))

    labels = {"daily": daily_label, "weekly": weekly_label, "monthly": monthly_label}
    picked = [args.period] if args.period else list(LONG)
    if estimated and pricing_map:
        # cost-stacked dashboard (vs token bars) — full redesign
        cost_buckets = bucketize_costs(parsed, pricing_map)
        for key in picked:
            title, desc, n = LONG[key]
            lines = panel_lines_cost(f"COST {title} ({desc})", cost_buckets[key][-n:], labels[key], bar_w, use_color,
                                     current_year=now.year)
            print("\n".join(lines))
            print()
        # also show token panels when verbose, otherwise cost-only is the vs view
        if args.verbose:
            print(c("── token panels (for reference) ──", DIM, use_color))
            for key in picked:
                title, desc, n = LONG[key]
                lines = panel_lines(f"{title} ({desc})", buckets[key][-n:], labels[key], bar_w, use_color,
                                    current_year=now.year, counts=args.requests)
                print("\n".join(lines))
                print()
    else:
        for key in picked:
            title, desc, n = LONG[key]
            lines = panel_lines(f"{title} ({desc})", buckets[key][-n:], labels[key], bar_w, use_color,
                                current_year=now.year, counts=args.requests)
            print("\n".join(lines))
            print()

    # Quota rolling windows summary
    q_lines = render_quotas_panel(quotas, use_color)
    print("\n".join(q_lines))
    print()

    legend = "  " + " ".join(
        c(BLOCKS[-1], SRC_COLOR[s], use_color) + f" {s}" for s in SOURCES
    )
    print(legend + c("   · grouped by local time", DIM, use_color))


if __name__ == "__main__":
    main()