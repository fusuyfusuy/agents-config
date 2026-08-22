#!/usr/bin/env python3
"""
ocgo_check.py — OpenCode Go live checker

Checks the live OpenCode Go catalog (docs + API), pulls benchmarks from
Artificial Analysis / LMArena / OpenRouter, and produces a cost/benefit
analysis against the Go usage limits ($12/5h, $30/wk, $60/mo pooled).

No API keys, stdlib only, graceful degradation when offline.
"""
import argparse
import datetime as dt
import html as html_lib
import json
import os
import pathlib
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# walk up to repo root (works whether file is at repo/scripts/ or repo/tui-agent-settings/usage/)
for _p in (HERE.parent, HERE.parent.parent, HERE.parent.parent.parent):
    if (_p / "setup.sh").exists() or (_p / ".git").exists():
        ROOT = _p
        break
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = ROOT / "outputs"

OCGO_DOCS = "https://opencode.ai/docs/go/"
OCGO_API = "https://opencode.ai/zen/go/v1/models"
OCGO_USAGE_API = "https://opencode.ai/zen/go/v1/usage"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
LMARENA_URL = "https://lmarena.ai/leaderboard/text"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

# ---------- fallback catalog (from docs snapshot 2026-08-21) ----------
# pricing per 1M tokens, usage = monthly_usage_limit_usd
FALLBACK_PRICING = {
    "grok-4.5": {"input": 2.00, "output": 6.00, "cached_read": 0.30, "cached_write": None, "usage": 15},
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cached_read": 0.02, "cached_write": 0.25, "usage": 15},
    "glm-5.3": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 15},
    "glm-5.2": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "glm-5.1": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "glm-5": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "kimi-k3": {"input": 3.00, "output": 15.00, "cached_read": 0.30, "cached_write": None, "usage": 15},
    "kimi-k2.7-code": {"input": 0.95, "output": 4.00, "cached_read": 0.19, "cached_write": None, "usage": 60},
    "kimi-k2.6": {"input": 0.95, "output": 4.00, "cached_read": 0.16, "cached_write": None, "usage": 60},
    "kimi-k2.5": {"input": 0.95, "output": 4.00, "cached_read": 0.16, "cached_write": None, "usage": 60},
    "mimo-v2.5": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "mimo-v2.5-pro": {"input": 0.435, "output": 0.87, "cached_read": 0.003625, "cached_write": None, "usage": 15},
    "mimo-v2-pro": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "mimo-v2-omni": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "minimax-m3": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": None, "usage": 60},
    "minimax-m2.7": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": 0.375, "usage": 60},
    "minimax-m2.5": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": 0.375, "usage": 60},
    "muse-spark-1.2-contributor": {"input": 0.10, "output": 0.20, "cached_read": 0.002, "cached_write": None, "usage": 60},
    "qwen3.8-max": {"input": 2.00, "output": 6.00, "cached_read": 0.25, "cached_write": 2.50, "usage": 15},
    "qwen3.7-max": {"input": 2.50, "output": 7.50, "cached_read": 0.50, "cached_write": 3.125, "usage": 60},
    "qwen3.7-plus": {"input": 0.40, "output": 1.60, "cached_read": 0.04, "cached_write": 0.50, "usage": 60},
    "qwen3.6-plus": {"input": 0.50, "output": 3.00, "cached_read": 0.05, "cached_write": 0.625, "usage": 60},
    "qwen3.5-plus": {"input": 0.40, "output": 1.60, "cached_read": 0.04, "cached_write": 0.50, "usage": 60},
    "deepseek-v4-pro": {"input": 0.66, "output": 1.98, "cached_read": 0.022, "cached_write": None, "usage": 15},
    "deepseek-v4-flash": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "usage": 30},
    "deepseek-v4-flash-vision-exp": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "usage": 15},
    "hy3": {"input": 0.14, "output": 0.58, "cached_read": 0.035, "cached_write": None, "usage": 60},
    "hy3-preview": {"input": 0.14, "output": 0.58, "cached_read": 0.035, "cached_write": None, "usage": 60},
    "ox-alpha-free": {"input": None, "output": None, "cached_read": None, "cached_write": None, "usage": None},
}

# Docs-backed models (exactly those on https://opencode.ai/docs/go/ pricing table, 23)
DOCS_IDS = {
    "grok-4.5", "gpt-5.6-luna", "glm-5.3", "glm-5.2", "glm-5.1",
    "kimi-k3", "kimi-k2.7-code", "kimi-k2.6",
    "mimo-v2.5", "mimo-v2.5-pro",
    "minimax-m3", "minimax-m2.7", "minimax-m2.5",
    "muse-spark-1.2-contributor",
    "qwen3.8-max", "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp",
    "hy3", "ox-alpha-free",
}

FALLBACK_TOKENS = {
    "grok-4.5": (1100, 71500, 220),
    "glm-5.3": (700, 52000, 150),
    "glm-5.2": (700, 52000, 150),
    "glm-5.1": (700, 52000, 150),
    "glm-5": (700, 52000, 150),
    "gpt-5.6-luna": (1000, 50000, 220),
    "kimi-k3": (1050, 76500, 300),
    "kimi-k2.7-code": (870, 55000, 200),
    "kimi-k2.6": (870, 55000, 200),
    "kimi-k2.5": (870, 55000, 200),
    "mimo-v2.5": (830, 71500, 295),
    "mimo-v2.5-pro": (790, 86000, 305),
    "mimo-v2-pro": (830, 71500, 295),
    "mimo-v2-omni": (830, 71500, 295),
    "minimax-m3": (510, 56000, 190),
    "minimax-m2.7": (300, 55000, 125),
    "minimax-m2.5": (300, 55000, 125),
    "muse-spark-1.2-contributor": (620, 71400, 300),
    "qwen3.8-max": (420, 66000, 200),
    "qwen3.7-max": (420, 66000, 200),
    "qwen3.7-plus": (500, 57000, 190),
    "qwen3.6-plus": (500, 57000, 190),
    "qwen3.5-plus": (500, 57000, 190),
    "deepseek-v4-pro": (750, 82000, 290),
    "deepseek-v4-flash": (410, 71300, 310),
    "deepseek-v4-flash-vision-exp": (410, 71300, 310),
    "hy3": (830, 71500, 295),
    "hy3-preview": (830, 71500, 295),
    "ox-alpha-free": (0, 0, 0),
}

ACC_5H, ACC_WK, ACC_MO = 12.0, 30.0, 60.0


def log(msg, verbose=False):
    if verbose or True:
        print(msg)


def fetch(url, timeout=20, verbose=False):
    """Fetch URL with UA header. Returns bytes or None."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if verbose:
                print(f"  fetched {url} -> {r.status} {len(body)} bytes")
            return body
    except Exception as e:
        print(f"  WARN fetch {url}: {e}", file=sys.stderr)
        return None


def parse_ocgo_docs(html, verbose=False):
    """Parse pricing, requests, and token estimates from Go docs HTML."""
    pricing = {}
    requests = {}
    tokens = {}
    # Tables: first = requests per window, second = pricing
    tables = re.findall(r"<table.*?</table>", html, flags=re.S)
    if verbose:
        print(f"  docs: found {len(tables)} tables")
    # --- pricing table (second) ---
    if len(tables) >= 2:
        # Use second table (index 1)
        # Extract rows
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[1], flags=re.S)
        for tr in rows[1:]:  # skip header
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
            if len(cells) < 6:
                continue
            # Clean cells
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            model_raw = clean[0]
            inp_raw = clean[1]
            out_raw = clean[2]
            cr_raw = clean[3]
            cw_raw = clean[4]
            usage_raw = clean[5]

            # Model name to id: normalize like "GLM-5.3" -> "glm-5.3"
            # Handle variants like "GPT 5.6 Luna (≤ 272K tokens)" -> "gpt-5.6-luna"
            # and "Qwen3.7 Plus (≤ 256K tokens)" -> "qwen3.7-plus"
            # and "DeepSeek V4 Pro (Off-Peak)" -> "deepseek-v4-pro"
            mid = model_to_id(model_raw)
            if not mid:
                continue
            # Skip duplicate tier rows where we already have a cheaper one?
            # For models with two tiers, keep the cheaper (first) entry
            if mid in pricing:
                continue
            def parse_price(s):
                s = s.replace("$", "").replace(",", "").strip()
                if s in ("", "-", "—"):
                    return None
                try:
                    return float(s)
                except Exception:
                    return None

            usage = parse_price(usage_raw)
            # For pricing, take first occurrence (cheapest tier)
            pricing[mid] = {
                "input": parse_price(inp_raw),
                "output": parse_price(out_raw),
                "cached_read": parse_price(cr_raw),
                "cached_write": parse_price(cw_raw),
                "usage": usage,
            }
            if verbose and mid in ("grok-4.5", "glm-5.3", "hy3"):
                print(f"    pricing {mid}: {pricing[mid]} from '{model_raw}'")

    # --- requests table (first) ---
    if len(tables) >= 1:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], flags=re.S)
        for tr in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
            if len(cells) < 4:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).replace(",", "").strip() for c in cells]
            model_raw = clean[0]
            mid = model_to_id(model_raw)
            if not mid:
                continue
            try:
                r5 = int(clean[1]) if clean[1] not in ("-", "—", "") else None
                rw = int(clean[2]) if clean[2] not in ("-", "—", "") else None
                rm = int(clean[3]) if clean[3] not in ("-", "—", "") else None
            except Exception:
                continue
            requests[mid] = {"per_5h": r5, "per_week": rw, "per_month": rm}

    # --- token estimates (ul after first table) ---
    # Find the <ul> that follows the first table
    ul_match = re.search(r"requests per month.*?</table>(.*?)<h2", html, flags=re.S)
    if ul_match:
        seg = ul_match.group(1)
        lis = re.findall(r"<li[^>]*>(.*?)</li>", seg, flags=re.S)
        for li in lis:
            txt = re.sub(r"<[^>]+>", "", li).strip()
            # e.g. "Grok 4.5 — 1,100 input, 71,500 cached, 220 output tokens per request"
            # or "GLM-5.3/5.2/5.1 — 700 input, 52,000 cached, 150 output..."
            m = re.search(r"([\d,]+)\s+input.*?([\d,]+)\s+cached.*?([\d,]+)\s+output", txt)
            if not m:
                continue
            try:
                inp = int(m.group(1).replace(",", ""))
                cac = int(m.group(2).replace(",", ""))
                out = int(m.group(3).replace(",", ""))
            except Exception:
                continue
            # Model part is before "—" or "-"
            model_part = re.split(r"[—-]", txt)[0].strip()
            # Handle slash-separated like "GLM-5.3/5.2/5.1"
            for part in re.split(r"\s*/\s*", model_part):
                part = part.strip()
                if "/" in part:
                    continue
                # part like "GLM-5.3" or "Kimi K2.7" or "DeepSeek V4 Pro"
                mid = model_to_id(part)
                if not mid:
                    # Try to map verbose names
                    # "Kimi K2.7" without "Code" should map to both k2.6/k2.7 code?
                    # We'll handle special cases
                    if "kimi k2.7" in part.lower() or "kimi k2.6" in part.lower():
                        for k in ("kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5"):
                            tokens[k] = (inp, cac, out)
                        continue
                    if "glm-5.3" in part.lower():
                        for k in ("glm-5.3", "glm-5.2", "glm-5.1", "glm-5"):
                            tokens[k] = (inp, cac, out)
                        continue
                    continue
                # For cases like "mimo-v2.5" the li says "MiMo-V2.5 — 830..."
                # So we get one id per li, but for slash groups we split above
                tokens[mid] = (inp, cac, out)
                # Handle special expanded cases
                if mid == "mimo-v2.5":
                    tokens["mimo-v2-pro"] = (inp, cac, out)
                    tokens["mimo-v2-omni"] = (inp, cac, out)
                if mid == "mimo-v2.5-pro":
                    pass
                if mid == "qwen3.7-plus":
                    # Also covers qwen3.6-plus? No, separate li
                    pass

    # Ensure every pricing entry has token estimate fallback
    for mid in pricing:
        if mid not in tokens and mid in FALLBACK_TOKENS:
            tokens[mid] = FALLBACK_TOKENS[mid]

    return pricing, requests, tokens


def model_to_id(raw):
    """Map docs display name to canonical model_id."""
    raw = raw.strip()
    # Remove parentheticals like "(≤ 272K tokens)" or "(Off-Peak)" or "(≤ 256K tokens)"
    raw = re.sub(r"\([^)]*\)", "", raw).strip()
    # Normalize spaces and dashes
    # Examples:
    # "Grok 4.5" -> "grok-4.5"
    # "GPT 5.6 Luna" -> "gpt-5.6-luna"
    # "GLM-5.3" -> "glm-5.3"
    # "MiMo V2.5 Pro" -> "mimo-v2.5-pro"
    # "MiniMax M3" -> "minimax-m3"
    # "Muse Spark 1.2 Contributor" -> "muse-spark-1.2-contributor"
    # "Qwen3.8 Max" -> "qwen3.8-max"
    # "Qwen3.7 Plus" -> "qwen3.7-plus"
    # "DeepSeek V4 Pro" -> "deepseek-v4-pro"
    # "DeepSeek V4 Flash Vision Exp" -> "deepseek-v4-flash-vision-exp"
    # "Hy3" -> "hy3"
    # "Ox Alpha Free" -> "ox-alpha-free"
    low = raw.lower()
    # Direct mappings for known oddities
    mapping = {
        "grok 4.5": "grok-4.5",
        "gpt 5.6 luna": "gpt-5.6-luna",
        "glm-5.3": "glm-5.3",
        "glm-5.2": "glm-5.2",
        "glm-5.1": "glm-5.1",
        "glm 5": "glm-5",
        "kimi k3": "kimi-k3",
        "kimi k2.7 code": "kimi-k2.7-code",
        "kimi k2.6": "kimi-k2.6",
        "kimi k2.5": "kimi-k2.5",
        "mimo v2.5": "mimo-v2.5",
        "mimo v2.5 pro": "mimo-v2.5-pro",
        "mimo-v2.5": "mimo-v2.5",
        "mimo-v2.5-pro": "mimo-v2.5-pro",
        "mimo v2 pro": "mimo-v2-pro",
        "mimo v2 omni": "mimo-v2-omni",
        "minimax m3": "minimax-m3",
        "minimax m2.7": "minimax-m2.7",
        "minimax m2.5": "minimax-m2.5",
        "muse spark 1.2 contributor": "muse-spark-1.2-contributor",
        "qwen3.8 max": "qwen3.8-max",
        "qwen3.7 max": "qwen3.7-max",
        "qwen3.7 plus": "qwen3.7-plus",
        "qwen3.6 plus": "qwen3.6-plus",
        "qwen3.5 plus": "qwen3.5-plus",
        "deepseek v4 pro": "deepseek-v4-pro",
        "deepseek v4 flash": "deepseek-v4-flash",
        "deepseek v4 flash vision exp": "deepseek-v4-flash-vision-exp",
        "hy3": "hy3",
        "hy3-preview": "hy3-preview",
        "ox alpha free": "ox-alpha-free",
    }
    if low in mapping:
        return mapping[low]
    # Try generic normalization: replace spaces with dashes, keep dots
    # e.g. "GLM-5.3" already, "Qwen3.8 Max" -> "qwen3.8-max"
    # Do: lower, replace " " with "-", strip
    generic = low.replace(" ", "-").replace("_", "-")
    generic = re.sub(r"-+", "-", generic).strip("-")
    # Check if generic matches any fallback key when dots/dashes normalized
    for k in FALLBACK_PRICING:
        if k.replace(".", "-") == generic.replace(".", "-"):
            return k
    # Fallback: if generic looks like a model id, return it
    if re.match(r"^[a-z0-9][a-z0-9\.\-]*$", generic) and len(generic) >= 2:
        return generic
    return None


def norm_id(s):
    return s.lower().replace(".", "-").replace("_", "-")


def parse_aa(html, verbose=False):
    """Parse AA leaderboard from RSC payload. Returns dict slug->record."""
    unescaped = html.replace('\\"', '"').replace("\\/", "/")
    # Find all '"models":[' occurrences
    idxs = []
    pos = 0
    while True:
        idx = unescaped.find('"models":[', pos)
        if idx == -1:
            break
        idxs.append(idx)
        pos = idx + 1
    if verbose:
        print(f"  AA: found {len(idxs)} models arrays")
    if not idxs:
        return {}
    # Pick the array that contains intelligenceIndex (second one is the full dataset)
    # Find the largest that contains intelligenceIndex
    best = None
    best_len = -1
    best_idx = -1
    for idx in idxs:
        snippet = unescaped[idx: idx + 3000]
        has_int = "intelligenceIndex" in snippet
        if not has_int:
            continue
        # Bracket-count to find end
        start = idx + len('"models":[')
        depth = 1
        p = start
        in_str = False
        esc = False
        while p < len(unescaped) and depth > 0:
            c = unescaped[p]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
            p += 1
            if p - idx > 4_000_000:
                break
        seg_len = p - idx
        if seg_len > best_len:
            best_len = seg_len
            best_idx = idx
            best = p
    if best_idx == -1:
        if verbose:
            print("  AA: no intelligenceIndex array found, falling back to last")
        best_idx = idxs[-1]
        # recompute best
        start = best_idx + len('"models":[')
        depth = 1
        p = start
        in_str = False
        esc = False
        while p < len(unescaped) and depth > 0:
            c = unescaped[p]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
            p += 1
        best = p

    seg = unescaped[best_idx:best]
    try:
        obj = json.loads("{" + seg + "}")
        models = obj["models"]
        out = {}
        for m in models:
            slug = m.get("slug")
            if slug:
                out[slug] = m
        if verbose:
            print(f"  AA: parsed {len(out)} models")
        return out
    except Exception as e:
        print(f"  WARN AA parse failed: {e}", file=sys.stderr)
        return {}


def parse_lmarena(html, verbose=False):
    """Parse LMArena HTML table. Returns dict slug-> {rank, elo, votes, price, context}."""
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S)
    if verbose:
        print(f"  LMArena: found {len(trs)} tr rows")
    out = {}
    for tr in trs[1:]:  # skip header
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(cells) < 7:
            continue
        # rank
        rank_raw = re.sub(r"<[^>]+>", "", cells[0]).strip()
        # model slug: prefer title="..." attribute inside cell[2] (most reliable)
        # e.g. <span title="hy3">hy3</span> or title="claude-fable-5"
        m_title = re.search(r'title="([^"]+)"', cells[2])
        if m_title:
            slug = m_title.group(1).strip().lower()
        else:
            # Fallback: href path (internal model pages) or visible text
            href_m = re.search(r'href="[^"]*?/([^"/\?]+)', cells[2])
            slug = href_m.group(1).lower() if href_m else ""
            if not slug or "." not in slug and "-" not in slug:
                # Try visible text token with digit and dash/dot
                text = re.sub(r"<[^>]+>", " ", cells[2]).strip()
                tokens = re.findall(r"[a-z0-9][a-z0-9\.\-]*", text.lower())
                with_digit = [t for t in tokens if any(ch.isdigit() for ch in t) and ("-" in t or "." in t)]
                if with_digit:
                    slug = with_digit[-1]
                elif tokens:
                    # Fallback to last token that looks like model
                    slug = tokens[-1]
        if not slug:
            continue
        slug = slug.strip().lower()
        # Score like "1507±5"
        score_raw = re.sub(r"<[^>]+>", "", cells[3]).strip()
        elo = score_raw.split("±")[0].strip()
        try:
            elo_f = float(elo.replace(",", ""))
        except Exception:
            elo_f = None
        try:
            rank_i = int(rank_raw)
        except Exception:
            rank_i = None
        votes_raw = re.sub(r"<[^>]+>", "", cells[4]).strip().replace(",", "")
        try:
            votes_i = int(votes_raw)
        except Exception:
            votes_i = None
        price_raw = re.sub(r"<[^>]+>", " ", cells[5]).strip()
        ctx_raw = re.sub(r"<[^>]+>", "", cells[6]).strip()
        out[slug] = {
            "rank": rank_i,
            "elo": elo_f,
            "votes": votes_i,
            "price_raw": price_raw,
            "context_raw": ctx_raw,
            "score_raw": score_raw,
        }
    if verbose:
        print(f"  LMArena: parsed {len(out)} entries")
    return out


def parse_openrouter(data_json, verbose=False):
    """Parse OpenRouter models API. Returns dict id->record."""
    try:
        items = data_json["data"] if isinstance(data_json, dict) and "data" in data_json else data_json
        out = {}
        for m in items:
            mid = m.get("id")
            if mid:
                out[mid] = m
        if verbose:
            print(f"  OpenRouter: {len(out)} models")
        return out
    except Exception as e:
        print(f"  WARN OpenRouter parse: {e}", file=sys.stderr)
        return {}


def find_aa_for_ocgo(ocgo_id, aa_map):
    """Find best AA record for an OC Go id."""
    n = norm_id(ocgo_id)
    # Exact
    if n in aa_map:
        return aa_map[n]
    # Try normalized slug match
    for slug, rec in aa_map.items():
        if norm_id(slug) == n:
            return rec
    # Contains
    for slug, rec in aa_map.items():
        ns = norm_id(slug)
        if n in ns or ns in n:
            # Prefer longer match? Pick first with intelligence
            if rec.get("intelligenceIndex") is not None:
                return rec
    # Fallback: prefix match on first token
    prefix = n.split("-")[0]
    for slug, rec in aa_map.items():
        if norm_id(slug).startswith(prefix) and rec.get("intelligenceIndex") is not None:
            # Check if ocgo id's second token also matches
            if len(n.split("-")) > 1 and n.split("-")[1] in norm_id(slug):
                return rec
    return None


def find_lm_for_ocgo(ocgo_id, lm_map):
    n = norm_id(ocgo_id)
    if n in lm_map:
        return lm_map[n]
    for slug, rec in lm_map.items():
        if norm_id(slug) == n:
            return rec
    # Loose contains, but prioritize exact digit match
    # For "kimi-k3" LMArena has "kimi-k3-quickstart" — should match loosely
    for slug, rec in lm_map.items():
        ns = norm_id(slug)
        if n in ns or ns in n:
            return rec
    return None


def find_or_for_ocgo(ocgo_id, or_map):
    n = norm_id(ocgo_id)
    # Try direct contains
    candidates = []
    for oid, rec in or_map.items():
        if n in norm_id(oid) or norm_id(oid) in n:
            candidates.append((oid, rec))
    if not candidates:
        return None, None
    # Prefer exact suffix match (after slash)
    for oid, rec in candidates:
        suffix = oid.split("/")[-1]
        if norm_id(suffix) == n:
            return oid, rec
    # Prefer shortest? Or most recent?
    # Pick candidate with pricing and smallest length difference
    candidates.sort(key=lambda x: abs(len(norm_id(x[0])) - len(n)))
    return candidates[0]


def compute_cost(input_per_1m, output_per_1m, cached_per_1m, est_input, est_cached, est_output):
    if None in (input_per_1m, output_per_1m, cached_per_1m) or None in (est_input, est_cached, est_output):
        return None
    if est_input == 0 and est_cached == 0 and est_output == 0:
        return 0.0
    return (input_per_1m * est_input / 1_000_000) + (cached_per_1m * est_cached / 1_000_000) + (output_per_1m * est_output / 1_000_000)


def _safe_int_round(v):
    try:
        return int(round(v)) if v is not None else None
    except Exception:
        return None


# ---------- usage API ----------
def _find_key_recursive(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and len(v) > 20 and any(s in k.lower() for s in ("key", "token", "secret")):
                return v
            r = _find_key_recursive(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_key_recursive(v)
            if r:
                return r
    return None


def get_api_key(args):
    if getattr(args, "key", None):
        return args.key
    env = os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENCODE_GO_KEY")
    if env:
        return env.strip()
    for p in [pathlib.Path.home() / ".local" / "share" / "opencode" / "auth.json", pathlib.Path.home() / ".config" / "opencode" / "auth.json"]:
        if p.exists():
            try:
                return _find_key_recursive(json.loads(p.read_text()))
            except Exception:
                continue
    return None


def fetch_usage(key, verbose=False):
    if not key:
        return None, "no key"
    req = urllib.request.Request(OCGO_USAGE_API, headers={"User-Agent": UA, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            data = json.loads(body)
            # usage may be at top level or under "usage"
            usage = data.get("usage", data) if isinstance(data, dict) else data
            if verbose:
                print(f"  usage: HTTP {r.status} keys={list(usage.keys()) if isinstance(usage, dict) else type(usage)}")
            return usage, None
    except urllib.error.HTTPError as e:
        try:
            b = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            b = str(e)
        return None, f"HTTP {e.code}: {b[:200]}"
    except Exception as e:
        return None, str(e)


def _pct_color(pct, for_html=False):
    # pct = remaining percent 0-100
    if pct is None:
        return ("", "") if for_html else ""
    if for_html:
        if pct > 50:
            return "#3fb950", ""  # green
        if pct > 25:
            return "#d29922", ""  # yellow
        if pct > 10:
            return "#f85149", ""  # red
        return "#f85149", "font-weight:700"
    # ANSI
    if pct > 50:
        return "\033[32m"  # green
    if pct > 25:
        return "\033[33m"  # yellow
    if pct > 10:
        return "\033[31m"  # red
    return "\033[31;1m"  # bold red


def main():
    ap = argparse.ArgumentParser(description="OpenCode Go live checker — benchmarks + cost/benefit")
    ap.add_argument("--offline", action="store_true", help="do not fetch network, use fallback/cached")
    ap.add_argument("--fetch", action="store_true", help="save raw snapshots to data/raw/")
    ap.add_argument("--check", action="store_true", help="dry-run: fetch and print summary, do not write outputs")
    ap.add_argument("--verbose", action="store_true", help="verbose logging")
    ap.add_argument("--out", type=str, default=None, help="override output dir")
    ap.add_argument("--key", type=str, default=None, help="OpenCode Go API key (or $OPENCODE_API_KEY / auth.json)")
    args = ap.parse_args()

    verbose = args.verbose
    do_fetch = args.fetch
    do_write = not args.check
    offline = args.offline

    if offline:
        do_fetch = False

    out_dir = Path(args.out) if args.out else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    print("OpenCode Go — live check")
    print(f"  date: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  mode: {'offline' if offline else 'live'}" + (" +fetch" if do_fetch else "") + (" check-only" if args.check else ""))

    # ---- 1. Fetch OC Go docs + API ----
    pricing_live = {}
    requests_live = {}
    tokens_live = {}
    ocgo_api_ids = []

    if not offline:
        body = fetch(OCGO_DOCS, verbose=verbose)
        if body:
            html = body.decode(errors="ignore")
            if do_fetch:
                snap = RAW / f"opencode_go_docs_{dt.date.today().isoformat().replace('-','')}.html"
                snap.write_text(html)
                print(f"  saved docs snapshot -> {snap.relative_to(ROOT)} ({len(html)} bytes)")
            pl, rl, tl = parse_ocgo_docs(html, verbose=verbose)
            if pl:
                pricing_live = pl
                print(f"  docs pricing: {len(pl)} models")
            if rl:
                requests_live = rl
            if tl:
                tokens_live = tl
            if verbose:
                print(f"  docs tokens: {len(tl)} models")
        else:
            print("  WARN docs fetch failed, using fallback", file=sys.stderr)

        body = fetch(OCGO_API, verbose=verbose)
        if body:
            try:
                j = json.loads(body)
                if do_fetch:
                    snap = RAW / f"opencode_go_models_{dt.date.today().isoformat().replace('-','')}.json"
                    snap.write_text(json.dumps(j, indent=2))
                    print(f"  saved API snapshot -> {snap.relative_to(ROOT)}")
                ids = [m["id"] for m in j.get("data", [])]
                ocgo_api_ids = ids
                if verbose:
                    print(f"  API models: {len(ids)} -> {ids}")
                else:
                    print(f"  API models: {len(ids)}")
            except Exception as e:
                print(f"  WARN API parse: {e}", file=sys.stderr)
        else:
            print("  WARN API fetch failed", file=sys.stderr)
    else:
        print("  offline: skipping docs/API fetch")

    # Fallback if live missing
    if not ocgo_api_ids:
        ocgo_api_ids = list(FALLBACK_PRICING.keys())
        print(f"  using fallback API ids: {len(ocgo_api_ids)}")

    # Merge pricing: live docs override fallback
    merged_pricing = {}
    for mid in ocgo_api_ids:
        if mid in pricing_live:
            merged_pricing[mid] = pricing_live[mid]
        elif mid in FALLBACK_PRICING:
            merged_pricing[mid] = FALLBACK_PRICING[mid]
        else:
            # Unknown new model not in fallback: try to find pricing from docs via normalized
            # If still not found, leave empty and will try OpenRouter later
            merged_pricing[mid] = {"input": None, "output": None, "cached_read": None, "cached_write": None, "usage": 60}

    merged_tokens = {}
    for mid in ocgo_api_ids:
        if mid in tokens_live:
            merged_tokens[mid] = tokens_live[mid]
        elif mid in FALLBACK_TOKENS:
            merged_tokens[mid] = FALLBACK_TOKENS[mid]
        else:
            merged_tokens[mid] = (500, 60000, 200)  # median fallback

    # ---- 2. Fetch OpenRouter ----
    or_map = {}
    if not offline:
        body = fetch(OPENROUTER_API, verbose=verbose)
        if body:
            try:
                j = json.loads(body)
                if do_fetch:
                    snap = RAW / f"openrouter_models_{dt.date.today().isoformat().replace('-','')}.json"
                    snap.write_text(json.dumps(j, indent=2))
                    print(f"  saved OpenRouter -> {snap.relative_to(ROOT)} ({len(body)} bytes)")
                or_map = parse_openrouter(j, verbose=verbose)
            except Exception as e:
                print(f"  WARN OpenRouter json: {e}", file=sys.stderr)
    # No fallback needed; or_map may be empty offline

    # ---- 3. Fetch AA ----
    aa_map = {}
    if not offline:
        body = fetch(AA_URL, verbose=verbose)
        if body:
            html = body.decode(errors="ignore")
            if do_fetch:
                snap = RAW / f"artificial_analysis_{dt.date.today().isoformat().replace('-','')}.html"
                snap.write_text(html)
                print(f"  saved AA -> {snap.relative_to(ROOT)} ({len(html)} bytes)")
            aa_map = parse_aa(html, verbose=verbose)
        else:
            print("  WARN AA fetch failed", file=sys.stderr)
    else:
        print("  offline: skipping AA")

    # ---- 4. Fetch LMArena ----
    lm_map = {}
    if not offline:
        body = fetch(LMARENA_URL, verbose=verbose)
        if body:
            html = body.decode(errors="ignore")
            if do_fetch:
                snap = RAW / f"lmarena_{dt.date.today().isoformat().replace('-','')}.html"
                snap.write_text(html)
                print(f"  saved LMArena -> {snap.relative_to(ROOT)} ({len(html)} bytes)")
            lm_map = parse_lmarena(html, verbose=verbose)
        else:
            print("  WARN LMArena fetch failed", file=sys.stderr)
    else:
        print("  offline: skipping LMArena")

    # ---- 4b. Fetch current usage (authenticated) ----
    usage_raw = None
    usage_err = None
    usage_percents = {}  # window -> percent used (0-100)
    usage_resets = {}
    usage_key_present = False
    if not offline:
        k = get_api_key(args)
        usage_key_present = bool(k)
        if k:
            usage_raw, usage_err = fetch_usage(k, verbose=verbose)
            if usage_raw and isinstance(usage_raw, dict):
                for w in ("rolling", "weekly", "monthly"):
                    ww = usage_raw.get(w)
                    if isinstance(ww, dict):
                        try:
                            pct = float(ww.get("percent", ww.get("usedPercent", ww.get("used", 0))))
                        except Exception:
                            pct = None
                        if pct is not None:
                            usage_percents[w] = pct
                        if "resetsAt" in ww:
                            usage_resets[w] = ww["resetsAt"]
                        elif "resetAt" in ww:
                            usage_resets[w] = ww["resetAt"]
                if usage_percents:
                    print(f"  usage: {', '.join(f'{w} {usage_percents[w]:.0f}% used' for w in usage_percents)}")
                elif usage_raw:
                    print(f"  usage: got data but no rolling/weekly/monthly percent — keys={list(usage_raw.keys())[:8]}", file=sys.stderr)
                    if verbose:
                        print(f"    raw={str(usage_raw)[:600]}", file=sys.stderr)
            elif usage_err:
                print(f"  usage: {usage_err} — remaining % will be N/A (use --key or $OPENCODE_API_KEY)", file=sys.stderr)
        else:
            if verbose:
                print("  usage: no key (--key / $OPENCODE_API_KEY / auth.json) — remaining % N/A")
    else:
        if verbose:
            print("  usage: offline — remaining % N/A")

    # most restrictive = max percent used
    usage_max_pct = max(usage_percents.values()) if usage_percents else None
    usage_remaining_pct = (100 - usage_max_pct) if usage_max_pct is not None else None

    # ---- 5. Build cost/benefit ----
    rows = []
    for mid in ocgo_api_ids:
        pr = merged_pricing.get(mid, {})
        inp = pr.get("input")
        outp = pr.get("output")
        cr = pr.get("cached_read")
        cw = pr.get("cached_write")
        usage = pr.get("usage")

        # For models where docs pricing is None (free) try OpenRouter pricing
        if inp is None and or_map:
            oid, rec = find_or_for_ocgo(mid, or_map)
            if rec:
                p = rec.get("pricing", {})
                try:
                    inp = float(p.get("prompt", 0)) * 1_000_000 if p.get("prompt") else inp
                    outp = float(p.get("completion", 0)) * 1_000_000 if p.get("completion") else outp
                    cr = float(p.get("input_cache_read", 0)) * 1_000_000 if p.get("input_cache_read") else cr
                except Exception:
                    pass

        est_in, est_ca, est_out = merged_tokens.get(mid, (500, 60000, 200))
        # DeepSeek flash off-peak vs peak: we use off-peak as Go likely uses off-peak pricing?
        # Docs show both; we already picked off-peak via first table entry.

        cost_req = compute_cost(inp, outp, cr, est_in, est_ca, est_out)

        # Scaled caps
        if usage is not None:
            try:
                cap_5h = ACC_5H * float(usage) / ACC_MO
                cap_wk = ACC_WK * float(usage) / ACC_MO
                cap_mo = float(usage)
            except Exception:
                cap_5h = cap_wk = cap_mo = None
        else:
            cap_5h = cap_wk = cap_mo = None

        # Requests per window (computed)
        if cost_req and cost_req > 0 and usage is not None:
            req_5h = cap_5h / cost_req if cap_5h else None
            req_wk = cap_wk / cost_req if cap_wk else None
            req_mo = cap_mo / cost_req if cap_mo else None
        else:
            req_5h = req_wk = req_mo = None

        # Docs estimated requests (if parsed)
        docs_req = requests_live.get(mid, {})

        # Benchmarks
        aa_rec = find_aa_for_ocgo(mid, aa_map) if aa_map else None
        lm_rec = find_lm_for_ocgo(mid, lm_map) if lm_map else None
        or_oid, or_rec = find_or_for_ocgo(mid, or_map) if or_map else (None, None)

        aa_int = aa_rec.get("intelligenceIndex") if aa_rec else None
        aa_cod = aa_rec.get("codingIndex") if aa_rec else None
        aa_age = aa_rec.get("agenticIndex") if aa_rec else None
        aa_tps = aa_rec.get("medianOutputTokensPerSecond") if aa_rec else None
        aa_ctx = aa_rec.get("contextWindowTokens") if aa_rec else None
        aa_slug = aa_rec.get("slug") if aa_rec else None

        lm_rank = lm_rec.get("rank") if lm_rec else None
        lm_elo = lm_rec.get("elo") if lm_rec else None
        lm_votes = lm_rec.get("votes") if lm_rec else None

        or_ctx = None
        or_price_prompt = None
        if or_rec:
            or_ctx = or_rec.get("context_length")
            try:
                or_price_prompt = float(or_rec.get("pricing", {}).get("prompt", 0)) * 1_000_000
            except Exception:
                pass

        # Value metrics
        intel_per_dollar = (aa_int / cost_req) if (aa_int is not None and cost_req and cost_req > 0) else None
        cost_per_intel = (cost_req / aa_int) if (aa_int and cost_req) else None
        req_per_dollar = (1 / cost_req) if cost_req else None
        # Leverage: $60 of API usage for $10 sub = 6x, but scaled by usage/60
        # Effective: if you max out monthly cap, you get `usage` dollars of API for $10
        leverage = (usage / 10.0) if usage else None

        # Usage remaining (per-window) — from authenticated /zen/go/v1/usage if key present
        # usage_percents holds percent *used* per window (0-100). Remaining % = 100 - used.
        remaining = {}
        remaining_req = {}
        overall_remaining_pct = None
        if usage_percents and cost_req and cost_req > 0 and usage is not None:
            for w, cap in (("rolling", cap_5h), ("weekly", cap_wk), ("monthly", cap_mo)):
                pct_used = usage_percents.get(w)
                if pct_used is None or cap is None:
                    continue
                try:
                    pct_rem = max(0.0, 100.0 - float(pct_used))
                except Exception:
                    continue
                try:
                    remaining[w] = round(pct_rem, 1)
                except Exception:
                    continue
                try:
                    rem_usd = cap * pct_rem / 100.0
                    remaining_req[w] = _safe_int_round(rem_usd / cost_req)
                except Exception:
                    continue
            if remaining:
                try:
                    overall_remaining_pct = min(remaining.values())  # most restrictive window
                except Exception:
                    overall_remaining_pct = None
        elif usage_percents and usage is None:
            # free model: no cap, remaining is same % but no request count
            for w, pct_used in usage_percents.items():
                try:
                    remaining[w] = round(max(0.0, 100.0 - float(pct_used)), 1)
                except Exception:
                    continue
        elif usage_key_present and not usage_percents:
            # key present but fetch failed — leave empty, UI will show N/A + error
            pass

        rows.append({
            "model_id": mid,
            "display": mid,
            "pricing": {"input_per_1m": inp, "output_per_1m": outp, "cached_read_per_1m": cr, "cached_write_per_1m": cw, "monthly_usage_limit_usd": usage},
            "caps": {"cap_5h_usd": cap_5h, "cap_wk_usd": cap_wk, "cap_mo_usd": cap_mo},
            "tokens": {"est_input": est_in, "est_cached": est_ca, "est_output": est_out},
            "cost_per_request_usd": round(cost_req, 6) if cost_req is not None else None,
            "requests": {
                "per_5h_computed": _safe_int_round(req_5h),
                "per_week_computed": _safe_int_round(req_wk),
                "per_month_computed": _safe_int_round(req_mo),
                "per_5h_docs": docs_req.get("per_5h"),
                "per_week_docs": docs_req.get("per_week"),
                "per_month_docs": docs_req.get("per_month"),
            },
            "remaining": {
                "percent": remaining,  # per-window remaining %
                "requests": remaining_req,  # per-window remaining requests
                "overall_pct": overall_remaining_pct,  # min across windows
                "overall_req": min(remaining_req.values()) if remaining_req else None,
            },
            "benchmarks": {
                "aa_slug": aa_slug,
                "aa_intelligence": aa_int,
                "aa_coding": aa_cod,
                "aa_agentic": aa_age,
                "aa_median_tps": aa_tps,
                "aa_context": aa_ctx,
                "lmarena_rank": lm_rank,
                "lmarena_elo": lm_elo,
                "lmarena_votes": lm_votes,
                "openrouter_id": or_oid,
                "openrouter_context": or_ctx,
                "openrouter_prompt_per_1m": or_price_prompt,
            },
            "value": {
                "intelligence_per_dollar": round(intel_per_dollar, 2) if intel_per_dollar else None,
                "cost_per_intelligence_pt_usd": round(cost_per_intel, 6) if cost_per_intel else None,
                "requests_per_dollar": round(req_per_dollar, 1) if req_per_dollar else None,
                "leverage_vs_10usd_sub": round(leverage, 2) if leverage else None,
            },
        })

    # Sort by intelligence_per_dollar desc, then by aa_intelligence desc
    rows_sorted = sorted(rows, key=lambda r: (
        -(r["value"]["intelligence_per_dollar"] or -1),
        -(r["benchmarks"]["aa_intelligence"] or -1),
        r["model_id"]
    ))

    # Pareto frontier (cost vs intelligence) — docs-backed only, for coloring
    pareto_ids = set()
    try:
        cand = [r for r in [r for r in rows_sorted if r["model_id"] in DOCS_IDS] if r["cost_per_request_usd"] and r["benchmarks"]["aa_intelligence"] is not None]
        for a in cand:
            dominated = False
            for b in cand:
                if b is a:
                    continue
                if b["cost_per_request_usd"] <= a["cost_per_request_usd"] and b["benchmarks"]["aa_intelligence"] >= a["benchmarks"]["aa_intelligence"]:
                    if b["cost_per_request_usd"] < a["cost_per_request_usd"] or b["benchmarks"]["aa_intelligence"] > a["benchmarks"]["aa_intelligence"]:
                        dominated = True
                        break
            if not dominated:
                pareto_ids.add(a["model_id"])
    except Exception:
        pareto_ids = set()

    # ---- 6. Console report ----
    # Only docs-backed models (23) to match website; API-only 6 (mimo-v2-pro/omni etc.) omitted from table but kept in JSON
    docs_rows = [r for r in rows_sorted if r["model_id"] in DOCS_IDS]
    # Remaining % column uses ANSI colors: green >50, yellow 25-50, red <25, bold red <10
    hdr_rem = "remain" if usage_percents else "remain*"
    print("\n" + "="*108)
    print(f"{'model':<28} {'$Usage':<7} {'$c/req':<8} {'req/5h':<7} {'intel':<6} {'cod':<6} {'LM rnk':<7} {'int/$':<7} {hdr_rem:<12} {'lev'}")
    print("-"*108)
    for r in docs_rows:
        mid = r["model_id"]
        usage = r["pricing"]["monthly_usage_limit_usd"]
        usage_s = f"${usage:.0f}" if usage is not None else "—"
        c = r["cost_per_request_usd"]
        c_s = f"${c:.4f}" if c is not None else "—"
        # Prefer docs estimate (authoritative per https://opencode.ai/docs/go/#usage-limits), fallback to computed
        req5 = r["requests"]["per_5h_docs"] if r["requests"]["per_5h_docs"] is not None else r["requests"]["per_5h_computed"]
        req5_s = f"{req5:,}" if req5 else "—"
        intel = r["benchmarks"]["aa_intelligence"]
        intel_s = f"{intel:.1f}" if isinstance(intel, (int, float)) else "—"
        cod = r["benchmarks"]["aa_coding"]
        cod_s = f"{cod:.1f}" if isinstance(cod, (int, float)) else "—"
        lm = r["benchmarks"]["lmarena_rank"]
        lm_s = f"#{lm}" if lm else "—"
        ipd = r["value"]["intelligence_per_dollar"]
        ipd_s = f"{ipd:.0f}" if isinstance(ipd, (int, float)) else "—"
        lev = r["value"]["leverage_vs_10usd_sub"]
        lev_s = f"{lev:.1f}x" if lev else "—"
        # Remaining % with color
        rem = r.get("remaining", {})
        overall = rem.get("overall_pct")
        overall_req = rem.get("overall_req")
        if overall is not None:
            col = _pct_color(overall, for_html=False)
            reset = "\033[0m"
            if overall_req is not None:
                rem_s = f"{col}{overall:.0f}% ({overall_req:,} req){reset}"
            else:
                rem_s = f"{col}{overall:.0f}%{reset}"
            # pad but keep ANSI invisible for alignment — use plain for width
            rem_plain = f"{overall:.0f}%"
            pad = 12 - len(rem_plain) - (6 if overall_req else 0)
            # we just print with color, no strict alignment for this col
        else:
            if usage_key_present and usage_err:
                rem_s = "ERR"
            elif not usage_key_present and not usage_percents:
                rem_s = "N/A*"
            else:
                rem_s = "—"
        flag = ""
        if r["model_id"] in pareto_ids:
            flag = "◆ pareto"
        elif r["pricing"]["monthly_usage_limit_usd"] is None:
            flag = "(free)"
        # color pareto model name in console (magenta)
        mid_disp = f"\033[35m{mid:<28}\033[0m" if mid in pareto_ids else f"{mid:<28}"
        print(f"{mid_disp} {usage_s:<7} {c_s:<8} {req5_s:<7} {intel_s:<6} {cod_s:<6} {lm_s:<7} {ipd_s:<7} {rem_s:<18} {lev_s} {flag}")
    print("="*108)
    if not usage_percents:
        if usage_key_present:
            print(f"remaining: {usage_err or 'no data'} — pass --key or set $OPENCODE_API_KEY (or auth.json)")
        else:
            print("remaining: N/A* — no key (use --key / $OPENCODE_API_KEY / ~/.local/share/opencode/auth.json to show live %)")

    # Write outputs
    if do_write:
        # data/ocgo_live.json
        live = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": {
                "opencode_docs": OCGO_DOCS,
                "opencode_api": OCGO_API,
                "openrouter_api": OPENROUTER_API,
                "artificial_analysis": AA_URL,
                "lmarena": LMARENA_URL,
                "usage_limits": "https://opencode.ai/docs/go/#usage-limits",
                "account_caps": {"cap_5h": ACC_5H, "cap_week": ACC_WK, "cap_month": ACC_MO},
                "note": "per-model caps = account_cap * usage/60; per-model Usage from docs pricing table"
            },
            "models": rows_sorted,
        }
        DATA.mkdir(parents=True, exist_ok=True)
        out_json = DATA / "ocgo_live.json"
        out_json.write_text(json.dumps(live, indent=2))
        if verbose:
            print(f"wrote {out_json.relative_to(ROOT)} ({len(json.dumps(live))} bytes)")

        # outputs json
        OUT.mkdir(parents=True, exist_ok=True)
        cb_json = OUT / "ocgo_cost_benefit.json"
        cb_json.write_text(json.dumps(rows_sorted, indent=2))
        if verbose:
            print(f"wrote {cb_json.relative_to(ROOT)}")

        # HTML — with one-sentence current work in footer next to path
        work = one_sentence_work(docs_rows, usage_percents)
        html_path = OUT / "ocgo_cost_benefit.html"
        html_path.write_text(render_html(docs_rows, work_sentence=work, pareto_ids=pareto_ids))
        if verbose:
            print(f"wrote {html_path.relative_to(ROOT)} ({html_path.stat().st_size} bytes)")
    else:
        print("\n(check-only, no files written)")


def render_html(rows, work_sentence=None, usage_percents=None, pareto_ids=None):
    if work_sentence is None:
        try:
            work_sentence = one_sentence_work(rows, usage_percents)
        except Exception:
            work_sentence = ""
    if pareto_ids is None:
        pareto_ids = set()
    title = f"OpenCode Go — Cost/Benefit ({dt.date.today().isoformat()})"
    rows_json = json.dumps(rows)
    # Build table rows
    trs = []
    for r in rows:
        mid = html_lib.escape(r["model_id"])
        usage = r["pricing"]["monthly_usage_limit_usd"]
        usage_s = f"${usage:.0f}" if usage is not None else "—"
        c = r["cost_per_request_usd"]
        c_s = f"${c:.5f}" if isinstance(c, float) else "—"
        # Use docs estimates when available (e.g. mimo-v2.5-pro 16,300 on web), fallback to computed
        req5 = r["requests"]["per_5h_docs"] if r["requests"]["per_5h_docs"] is not None else r["requests"]["per_5h_computed"]
        reqw = r["requests"]["per_week_docs"] if r["requests"]["per_week_docs"] is not None else r["requests"]["per_week_computed"]
        reqm = r["requests"]["per_month_docs"] if r["requests"]["per_month_docs"] is not None else r["requests"]["per_month_computed"]
        req5_s = f"{req5:,}" if isinstance(req5, int) else "—"
        reqw_s = f"{reqw:,}" if isinstance(reqw, int) else "—"
        reqm_s = f"{reqm:,}" if isinstance(reqm, int) else "—"
        aa_int = r["benchmarks"]["aa_intelligence"]
        aa_int_s = f"{aa_int:.1f}" if isinstance(aa_int, (int, float)) else "—"
        aa_cod = r["benchmarks"]["aa_coding"]
        aa_cod_s = f"{aa_cod:.1f}" if isinstance(aa_cod, (int, float)) else "—"
        aa_age = r["benchmarks"]["aa_agentic"]
        aa_age_s = f"{aa_age:.1f}" if isinstance(aa_age, (int, float)) else "—"
        lm_r = r["benchmarks"]["lmarena_rank"]
        lm_s = f"#{lm_r}" if isinstance(lm_r, int) else "—"
        elo = r["benchmarks"]["lmarena_elo"]
        elo_s = f"{elo:.0f}" if isinstance(elo, (int, float)) else "—"
        ipd = r["value"]["intelligence_per_dollar"]
        ipd_s = f"{ipd:.0f}" if isinstance(ipd, (int, float)) else "—"
        cpi = r["value"]["cost_per_intelligence_pt_usd"]
        cpi_s = f"${cpi:.5f}" if isinstance(cpi, float) else "—"
        lev = r["value"]["leverage_vs_10usd_sub"]
        lev_s = f"{lev:.1f}×" if isinstance(lev, (int, float)) else "—"
        aa_slug = html_lib.escape(r["benchmarks"]["aa_slug"] or "")
        # Remaining % visual
        rem = r.get("remaining", {})
        overall = rem.get("overall_pct")
        overall_req = rem.get("overall_req")
        if overall is not None:
            col, weight = _pct_color(overall, for_html=True)
            # bar width = remaining %
            try:
                pct = max(0, min(100, float(overall)))
            except Exception:
                pct = 0
            bar = f'<div style="background:var(--line);border-radius:4px;height:6px;width:60px;display:inline-block;vertical-align:middle;margin-left:6px"><div style="background:{col};height:6px;width:{pct:.0f}%;border-radius:4px"></div></div>'
            if overall_req is not None:
                rem_html = f'<span style="color:{col};{weight}">{overall:.0f}%</span><span class="mid">{overall_req:,} req</span>{bar}'
            else:
                rem_html = f'<span style="color:{col};{weight}">{overall:.0f}%</span>{bar}'
        else:
            # no key / error / free
            if r["pricing"]["monthly_usage_limit_usd"] is None:
                rem_html = '<span class="mid">free</span>'
            else:
                rem_html = '<span class="mid">N/A*</span>'
        # Highlight — pareto first (gold)
        cls = ""
        if r["model_id"] in pareto_ids:
            cls = "pareto"
        elif aa_int and aa_int >= 58:
            cls = "flagship"
        elif r["pricing"]["monthly_usage_limit_usd"] == 60 and ipd and ipd > 800:
            cls = "value"
        elif r["pricing"]["monthly_usage_limit_usd"] is None:
            cls = "free"

        trs.append(
            f'<tr class="{cls}">'
            f'<td class="m">{mid}</td>'
            f'<td class="n">{usage_s}</td>'
            f'<td class="n">{c_s}</td>'
            f'<td class="n">{req5_s}</td><td class="n">{reqw_s}</td><td class="n">{reqm_s}</td>'
            f'<td class="n">{aa_int_s}<span class="mid">{aa_slug}</span></td>'
            f'<td class="n">{aa_cod_s}</td><td class="n">{aa_age_s}</td>'
            f'<td class="n">{lm_s}<span class="mid">{elo_s}</span></td>'
            f'<td class="n">{ipd_s}</td><td class="n">{cpi_s}</td><td class="n">{lev_s}</td>'
            f'<td class="n">{rem_html}</td>'
            f'</tr>'
        )
    body = f"""
<h1>{html_lib.escape(title)}</h1>
<p class="sub">Live check — OpenCode Go subscription <code>$5 first month, then $10/mo</code> ·Limits: <b>$12/5h · $30/wk · $60/mo</b> pooled, scaled by per-model Usage/60 · <a href="https://opencode.ai/docs/go/#usage-limits" style="color:#58a6ff">docs</a> · Generated {dt.datetime.now(dt.timezone.utc).isoformat()}</p>

<div class="card"><b>How to read:</b> <span style="color:#d29922">■ pareto</span> cost/intelligence frontier · <span style="color:#3fb950">■ flagship</span> intelligence ≥58 · <span style="color:#58a6ff">■ value</span> $60-usage + high int/$ · <b>int/$</b> = AA Intelligence per $1 of request cost · <b>c/int</b> = cost per intelligence point · <b>lev</b> = monthly leverage vs $10 sub (<code>usage/10</code>) — a $60-usage model gives 6×.</div>

<div class="card">
<table id="tbl">
<thead><tr>
<th>model</th><th>$Usage/mo</th><th>$c/req</th><th>req/5h</th><th>req/wk</th><th>req/mo</th><th>AA intel</th><th>AA cod</th><th>AA agent</th><th>LMArena</th><th>int/$</th><th>$c/int</th><th>lev</th><th>remain</th>
</tr></thead>
<tbody>
{''.join(trs)}
</tbody>
</table>
<div class="legend">Click headers to sort. “—” = not benchmarked / free. AA Intelligence/Coding/Agentic from artificialanalysis.ai leaderboard; LMArena rank/ELO from lmarena.ai text leaderboard; pricing from opencode.ai/docs/go. Cross-source scores incomparable.</div>
</div>

<div class="call"><b>Takeaway:</b> Cheapest per-request (MiMo-V2.5, Muse Spark, Hy3, DeepSeek Flash) buy the most requests from the pooled cap — ideal for high-volume use. Flagship intelligence (Kimi K3, GLM-5.3, Qwen3.8-Max, Grok 4.5, GPT-5.6-Luna) cost more per request but score higher. Best “intelligence per dollar” usually sits in the middle (DeepSeek Flash, Qwen3.7-Plus, GLM-5.2, MiniMax M3). Use the <code>int/$</code> column to pick your tier.</div>

<p class="note">Full JSON: <a href="ocgo_cost_benefit.json" style="color:#58a6ff">ocgo_cost_benefit.json</a> · Raw snapshots in <code>data/raw/</code> when run with <code>--fetch</code>. Stdlib only, no API keys. Re-run: <code>python3 scripts/ocgo_check.py</code> / <code>ocheck</code>.</p>
<div class="footer"><span class="path">path: outputs/ocgo_cost_benefit.html</span><span class="work">{html_lib.escape(work_sentence)}</span></div>
<script>
(function(){{
  var tbl=document.getElementById('tbl');
  function getVal(tr,i){{
    var td=tr.children[i];
    var t=(td.innerText||'').replace(/[^0-9.\\-]/g,'').trim();
    var n=parseFloat(t);
    return isNaN(n)? (td.innerText||'').toLowerCase() : n;
  }}
  tbl.querySelectorAll('th').forEach(function(th,i){{
    th.addEventListener('click',function(){{
      var tbody=tbl.tBodies[0];
      var rows=[].slice.call(tbody.rows);
      var asc=th.asc=!th.asc;
      rows.sort(function(a,b){{
        var av=getVal(a,i), bv=getVal(b,i);
        if(typeof av==='number' && typeof bv==='number') return asc? av-bv : bv-av;
        return asc? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      }});
      rows.forEach(function(r){{tbody.appendChild(r);}});
    }});
  }});
}})();
</script>
"""
    css = """
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--txt:#e6edf3;--mut:#8b949e;--gr:#3fb950;--bl:#58a6ff;--yl:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:28px}
.wrap{max-width:1280px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}a{color:var(--bl)}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}th:hover{color:var(--bl)}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.m{font-weight:600}.mid{display:block;color:var(--mut);font-size:10px;font-weight:400;white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.call{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--yl);border-radius:8px;padding:12px 16px;margin:14px 0}
.call b{color:var(--yl)}.sub{color:var(--mut);margin:0 0 14px;font-size:13px}
.legend{color:var(--mut);font-size:11px;margin-top:8px}.note{color:var(--mut);font-size:12px;margin-top:14px;border-top:1px solid var(--line);padding-top:10px}
.footer{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center}
.footer .path{color:var(--mut);font-size:12px}
.footer .work{color:var(--txt);font-size:12px;font-style:italic;max-width:60%}
tr.flagship{background:rgba(63,185,80,0.07)}tr.value{background:rgba(88,166,255,0.07)}tr.pareto{background:rgba(210,153,34,0.18);border-left:3px solid #d29922}tr.free{opacity:0.6}
"""
    return f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html_lib.escape(title)}</title><style>{css}</style></head><body><div class=\"wrap\">{body}</div></body></html>\n"


def one_sentence_work(rows, usage_percents=None):
    try:
        n = len(rows)
        have_int = sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None)
        # best value among $60 usage
        best = None
        for r in sorted(rows, key=lambda x: -(x["value"]["intelligence_per_dollar"] or -1)):
            if r["pricing"]["monthly_usage_limit_usd"] == 60 and r["value"]["intelligence_per_dollar"]:
                best = r["model_id"]
                break
        # flagship
        flagship = None
        for r in rows:
            if r["benchmarks"]["aa_intelligence"] and r["benchmarks"]["aa_intelligence"] >= 59:
                flagship = r["model_id"]
                break
        rem = "" 
        if usage_percents:
            mx = max(usage_percents.values())
            rem = f", {100-mx:.0f}% quota remaining"
        if best and flagship:
            return f"Current work: live cost/benefit of {n} Go models ({have_int} ranked) — best value {best}, flagship {flagship}{rem}."
        if best:
            return f"Current work: live check of {n} Go models ({have_int} ranked) — best value {best}{rem}."
        return f"Current work: live check of {n} Go models ({have_int} ranked){rem}."
    except Exception:
        return f"Current work: live check of {len(rows)} Go models."


if __name__ == "__main__":
    main()
