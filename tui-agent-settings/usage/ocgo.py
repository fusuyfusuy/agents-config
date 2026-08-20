#!/usr/bin/env python3
"""ocgo — OpenCode Go quota & usage report.

Section 1: live subscription quota windows (5h rolling / weekly / monthly)
from the official /zen/go/v1/usage endpoint.

Section 2: "what ate it" — aggregate the paid 'opencode-go' traffic from the
local opencode.db over each window (by model, by session, token-type split,
cost). Free providers (deepseek-v4-flash-free, etc.) ride in the same table but
do not count against the paid bucket, so they are excluded here.

Stdlib only (reuses collect_agent_usage for the message parsing). Symlinked to
~/.local/bin/ocgo by setup.sh.
"""
import argparse
import http.client
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from datetime import timedelta
import calendar

import collect_agent_usage as cau

OPENCODE_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")
USAGE_URL = "/zen/go/v1/usage"
HOST = "opencode.ai"
PAID_PROVIDER = "opencode-go"

ROLLING_SECONDS = 5 * 3600
WEEK_FALLBACK = 7 * 86400
MONTH_FALLBACK = 30 * 86400

# (api key, tmux-style label used in the windows table)
WINDOWS = [
    ("rolling", "5h rolling"),
    ("weekly", "weekly"),
    ("monthly", "monthly"),
]

# residual-risk: a key absconding, API down, or auth missing -> report shows
# "--" for the live section but still prints the local breakdown with
# relative window bounds, so "who ate it" stays useful offline.


def resolve_key() -> str:
    key = os.environ.get("OPENCODE_GO_API_KEY", "")
    if key:
        return key
    try:
        with open(os.path.expanduser("~/.pi/agent/auth.json"), "r") as f:
            return (json.load(f).get("opencode-go") or {}).get("key", "")
    except Exception:
        return ""


def fetch_windows() -> dict:
    """GET usage; returns {'rolling': {...}, 'weekly': {...}, 'monthly': {...}}."""
    key = resolve_key()
    if not key:
        return {}
    try:
        conn = http.client.HTTPSConnection(HOST, timeout=5)
        try:
            conn.request(
                "GET",
                USAGE_URL,
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            )
            res = conn.getresponse()
            if res.status != 200:
                return {}
            return (json.loads(res.read().decode("utf-8", "replace")).get("usage") or {})
        finally:
            conn.close()
    except Exception:
        return {}


def parse_epoch(iso: str) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def countdown(iso: str) -> str:
    epoch = parse_epoch(iso)
    if epoch is None:
        return ""
    diff = int(epoch - time.time())
    if diff <= 0:
        return "now"
    if diff < 3600:
        return f"{diff // 60}m"
    if diff < 86400:
        return f"{diff // 3600}h{(diff % 3600) // 60}m"
    return f"{diff // 86400}d{(diff % 86400) // 3600}h"


def human(n: float) -> str:
    n = float(n)
    if n >= 1e9:
        return f"{n / 1e9:.2f}G"
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}k"
    return f"{int(n)}"


def money(c: float) -> str:
    return "$0" if c == 0 else f"${c:.4f}"


def load_session_map() -> dict:
    """session_id -> (title, directory)."""
    if not os.path.isfile(OPENCODE_DB):
        return {}
    con = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True)
    try:
        return {
            sid: (title or "", directory or "")
            for sid, title, directory in con.execute("SELECT id, title, directory FROM session")
        }
    finally:
        con.close()


def load_paid_records() -> list[dict]:
    """Paid opencode-go messages, normalized per record, across BOTH the
    local opencode.db AND pi session logs (pi is where opencode-go models are
    actually run in this setup).

    Reuses collect_agent_usage.parse_opencode / parse_pi (already-tested
    message parsers); filters to the paid provider and joins session
    title/directory where available.
    """
    sessions = load_session_map()
    records = []

    for rec in cau.parse_opencode(cau.discover_opencode()):
        if not (rec["model"] or "").startswith(f"{PAID_PROVIDER}/"):
            continue
        ts_ms = int(parse_epoch(rec["timestamp"]) * 1000) if rec["timestamp"] else 0
        title, directory = sessions.get(rec["session_id"], ("", ""))
        records.append({
            "ts_ms": ts_ms,
            "model": rec["model"].split("/", 1)[1],
            "title": title,
            "directory": directory,
            "input": rec["input_tokens"],
            "output": rec["output_tokens"],
            "cache_read": rec["cache_read_tokens"],
            "cache_write": rec["cache_write_tokens"],
            "reasoning": rec["reasoning_tokens"],
            "total": rec["total_tokens"],
            "cost": rec["cost_usd"] or 0.0,
        })

    for rec in cau.parse_pi(cau.discover_pi()):
        if rec.get("provider") != PAID_PROVIDER:
            continue
        ts_ms = int(parse_epoch(rec["timestamp"]) * 1000) if rec["timestamp"] else 0
        # pi logs carry no per-session title, only the session-dir project slug.
        records.append({
            "ts_ms": ts_ms,
            "model": rec["model"],
            "title": "",
            "directory": rec.get("project") or "",
            "input": rec["input_tokens"],
            "output": rec["output_tokens"],
            "cache_read": rec["cache_read_tokens"],
            "cache_write": rec["cache_write_tokens"],
            "reasoning": rec["reasoning_tokens"],
            "total": rec["total_tokens"],
            "cost": rec["cost_usd"] or 0.0,
        })

    return records


def summarize(records: list[dict], since_ms: int) -> dict:
    """Aggregate records with ts_ms >= since_ms into by-model / by-session /
    token-type / total buckets. Pure function -> unit-testable."""
    by_model, by_session = {}, {}
    toks = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "reasoning": 0}
    msgs = total_tokens = 0
    cost = 0.0
    for r in records:
        if r["ts_ms"] < since_ms:
            continue
        msgs += 1
        total_tokens += r["total"]
        cost += r["cost"]
        for k in toks:
            toks[k] += r[k]
        m = by_model.setdefault(r["model"], {"msgs": 0, "tokens": 0, "cost": 0.0})
        m["msgs"] += 1
        m["tokens"] += r["total"]
        m["cost"] += r["cost"]
        key = r["title"] or r["directory"] or r["session_id"]
        s = by_session.setdefault(key, {"msgs": 0, "tokens": 0, "cost": 0.0, "dir": r["directory"]})
        s["msgs"] += 1
        s["tokens"] += r["total"]
        s["cost"] += r["cost"]
    by_project = {}
    for _key, s in by_session.items():
        proj = os.path.basename(s["dir"] or "") or "(no project)"
        p = by_project.setdefault(proj, {"msgs": 0, "tokens": 0, "cost": 0.0})
        p["msgs"] += s["msgs"]
        p["tokens"] += s["tokens"]
        p["cost"] += s["cost"]
    return {
        "msgs": msgs,
        "tokens": total_tokens,
        "cost": cost,
        "toks": toks,
        "by_model": by_model,
        "by_session": by_session,
        "by_project": by_project,
    }


GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
RESET = "\033[0m"


def color_for(remaining_pct: float) -> str:
    if remaining_pct >= 50:
        return GREEN
    if remaining_pct >= 20:
        return YELLOW
    return RED


def bar(remaining_pct: float, width: int = 10, use_color: bool = True) -> str:
    filled = int(round(remaining_pct / 100 * width))
    glyph = "█" * filled + "░" * (width - filled)
    if use_color:
        glyph = f"{color_for(remaining_pct)}{glyph}{RESET}"
    return glyph


def pad(text: str, width: int, align: str = "l") -> str:
    return text.rjust(width) if align == "r" else text.ljust(width)


def c(text: str, code: str, use_color: bool) -> str:
    return f"{code}{text}{RESET}" if use_color else text


def print_windows(usage: dict, use_color: bool) -> None:
    print("OpenCode Go — quota status")
    if not usage:
        print(f"{DIM}  quota endpoint unavailable (check OPENCODE_GO_API_KEY / network){RESET}")
        print()
        return
    hdr = c(
        "  " + "  ".join([pad("WINDOW", 12), pad("USED", 7, "r"), pad("LEFT", 7, "r"), pad("RESETS", 9)])
        + "   PROGRESS",
        BOLD + CYAN,
        use_color,
    )
    print(hdr)
    for key, label in WINDOWS:
        w = usage.get(key) or {}
        if w.get("status") != "ok":
            print("  " + pad(label, 12) + "  --")
            continue
        used = float(w.get("percent", 0))
        remaining = 100.0 - used
        col = color_for(remaining)
        cells = [
            pad(label, 12),
            c(pad(f"{used:5.1f}%", 7, "r"), col, use_color),
            c(pad(f"{remaining:4.1f}%", 7, "r"), col, use_color),
            pad(countdown(w.get("resetsAt")), 9),
        ]
        print("  " + "  ".join(cells) + "   " + bar(remaining, use_color=use_color))
    print()


def subtract_period(iso: str | None, kind: str) -> float | None:
    """resetsAt (next reset, in future) -> start of the current period.

    weekly: 7 days back. monthly: one calendar month back (rolls to the same
    day, clamped to month end). rolling is handled by the caller (now-5h).
    """
    dt = parse_epoch(iso)
    if dt is None:
        return None
    base = datetime.fromtimestamp(dt, tz=timezone.utc)
    if kind == "weekly":
        return (base - timedelta(days=7)).timestamp()
    if kind == "monthly":
        year, month = base.year, base.month - 1
        if month == 0:
            year, month = year - 1, 12
        day = min(base.day, calendar.monthrange(year, month)[1])
        return base.replace(year=year, month=month, day=day).timestamp()
    return None


def window_bounds(usage: dict) -> dict[str, int]:
    """since-ms lower bound for each window's breakdown."""
    now = time.time()
    rolling = int((now - ROLLING_SECONDS) * 1000)
    weekly = subtract_period((usage.get("weekly") or {}).get("resetsAt"), "weekly")
    monthly = subtract_period((usage.get("monthly") or {}).get("resetsAt"), "monthly")
    return {
        "rolling": rolling,
        "weekly": int((weekly or (now - WEEK_FALLBACK)) * 1000),
        "monthly": int((monthly or (now - MONTH_FALLBACK)) * 1000),
    }


def _table(headers, rows, widths, aligns, use_color) -> list[str]:
    """Aligned column table; headers cyan-bold, first (top-consumer) row bold.
    Returns lines ready to print."""
    lines = [c("  " + "  ".join(pad(h, w, a) for h, w, a in zip(headers, widths, aligns)),
                BOLD + CYAN, use_color)]
    for i, row in enumerate(rows):
        line = "  " + "  ".join(pad(str(v), w, a) for v, w, a in zip(row, widths, aligns))
        if use_color and i == 0:
            line = f"{BOLD}{line}{RESET}"
        lines.append(line)
    return lines


def window_detail(label: str, sum: dict, use_color: bool, detail: bool) -> list[str]:
    title = f"── {label} window · {sum['msgs']} msgs · {human(sum['tokens'])} tokens · {money(sum['cost'])} ──"
    lines = [c(title, BOLD, use_color)]

    models = [(m, d) for m, d in sum["by_model"].items() if d["cost"] > 0 or d["tokens"] > 0]
    models.sort(key=lambda kv: -kv[1]["cost"])
    if not detail:
        models = models[:5]
    if models:
        lines += _table(
            ["MODEL", "MSGS", "TOKENS", "COST"],
            [(m, d["msgs"], human(d["tokens"]), money(d["cost"])) for m, d in models],
            [28, 6, 9, 9],
            ["l", "r", "r", "r"],
            use_color,
        )

    if detail:
        sess = sorted(sum["by_session"].items(), key=lambda kv: -kv[1]["cost"])
        if sess:
            lines += _table(
                ["SESSION", "MSGS", "TOKENS", "COST"],
                [(k + (f" ({s['dir']})" if s["dir"] else ""), s["msgs"],
                  human(s["tokens"]), money(s["cost"])) for k, s in sess],
                [44, 6, 9, 9],
                ["l", "r", "r", "r"],
                use_color,
            )
        toks = sum["toks"]
        split = (
            f"tokens in {human(toks['input'])} · out {human(toks['output'])}"
            f" · cache {human(toks['cache_read'] + toks['cache_write'])}"
            f" · reasoning {human(toks['reasoning'])}"
        )
        lines.append(c("  " + split, DIM, use_color))
    else:
        projs = sorted(sum["by_project"].items(), key=lambda kv: -kv[1]["cost"])[:5]
        extra = len(sum["by_project"]) - len(projs)
        lines.append("")
        lines += _table(
            ["PROJECT", "TOKENS", "COST"],
            [(p, human(d["tokens"]), money(d["cost"])) for p, d in projs],
            [24, 9, 9],
            ["l", "r", "r"],
            use_color,
        )
        if extra:
            lines.append(c(f"  ⋯ +{extra} more projects", DIM, use_color))
    lines.append("")
    return lines


def run_report(records: list[dict], usage: dict, detail: bool, picked: list[str], use_color: bool) -> None:
    bounds = window_bounds(usage)
    for key in picked:
        sum = summarize(records, bounds[key])
        label = dict(WINDOWS)[key]
        if not detail and sum["msgs"] == 0:
            continue
        print("\n".join(window_detail(label, sum, use_color, detail)))


def main() -> None:
    ap = argparse.ArgumentParser(description="OpenCode Go quota status + who-ate-it report")
    ap.add_argument(
        "--window",
        choices=["rolling", "weekly", "monthly"],
        help="show one window's who-ate-it table (default: rolling = active gate)",
    )
    ap.add_argument("--cost", action="store_true", help="total spent per window only, no tables")
    ap.add_argument("--detail", action="store_true", help="all windows, full per-session tables (long)")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI color")
    args = ap.parse_args()

    use_color = not args.no_color and sys.stdout.isatty()
    usage = fetch_windows()

    records = load_paid_records()
    if not records:
        print("no 'opencode-go' traffic found in local opencode.db")
        return

    if args.cost:
        picked = [args.window] if args.window else [k for k, _ in WINDOWS]
        bounds = window_bounds(usage)
        for key in picked:
            s = summarize(records, bounds[key])
            print(f"  {pad(dict(WINDOWS)[key], 12)}  {money(s['cost'])}")
        return

    print_windows(usage, use_color)

    if args.detail:
        picked = [k for k, _ in WINDOWS]
    else:
        picked = [args.window] if args.window else ["rolling"]
    run_report(records, usage, args.detail, picked, use_color)


if __name__ == "__main__":
    main()
