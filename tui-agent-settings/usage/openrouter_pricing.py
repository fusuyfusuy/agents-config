#!/usr/bin/env python3
"""openrouter_pricing — fetch + cache + resolve OpenRouter per-token pricing.

Stdlib only. Cache at $XDG_CACHE_HOME/toku/openrouter-pricing.json (or
~/.cache/toku/openrouter-pricing.json), 24h TTL. `get_pricing()` handles
fetch, stale fallback, and verbose warnings; `resolve_model()` does
best-effort mapping from log model names to OpenRouter ids; `estimate_cost()`
computes USD from a parsed toku record.
"""
import http.client
import json
import os
import sys
import time

HOST = "openrouter.ai"
PATH = "/api/v1/models"
TTL_SECONDS = 24 * 3600  # 24h


def _cache_path() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "toku", "openrouter-pricing.json")


def _parse_price(pricing: dict, key: str) -> float:
    try:
        v = pricing.get(key)
        if v is None:
            return 0.0
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(v) -> int:
    try:
        if v is None:
            return 0
        return int(v)
    except (ValueError, TypeError):
        return 0


def fetch_pricing(timeout: float = 5.0) -> dict | None:
    """GET openrouter.ai/api/v1/models → {model_id: pricing_dict} or None on failure."""
    try:
        conn = http.client.HTTPSConnection(HOST, timeout=timeout)
        try:
            conn.request("GET", PATH, headers={"Accept": "application/json"})
            res = conn.getresponse()
            if res.status != 200:
                return None
            raw = res.read().decode("utf-8", "replace")
            data = json.loads(raw)
            out = {}
            for m in data.get("data") or []:
                pid = m.get("id")
                pricing = m.get("pricing")
                if pid and isinstance(pricing, dict):
                    out[pid] = pricing
            return out
        finally:
            conn.close()
    except Exception:
        return None


def load_cached() -> tuple[dict | None, float | None]:
    path = _cache_path()
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
        fetched_at = blob.get("fetched_at")
        models = blob.get("models")
        if not isinstance(models, dict):
            return None, None
        return models, float(fetched_at) if fetched_at is not None else None
    except Exception:
        return None, None


def save_cached(pricing_map: dict) -> None:
    path = _cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        blob = {"fetched_at": time.time(), "models": pricing_map}
        # atomic write via temp file
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(blob, f)
        os.replace(tmp, path)
    except Exception:
        pass


def is_fresh(fetched_at: float | None, ttl: float = TTL_SECONDS) -> bool:
    if fetched_at is None:
        return False
    return (time.time() - fetched_at) < ttl


def get_pricing(refresh: bool = False, verbose: bool = False) -> tuple[dict, str]:
    """Return (pricing_map, source) handling cache/fetch/stale.

    source in {"cache","fetch","stale","none"} for status reporting.
    """
    cached, fetched_at = load_cached()
    fresh = is_fresh(fetched_at)

    if not refresh and cached is not None and fresh:
        if verbose:
            age_h = (time.time() - fetched_at) / 3600 if fetched_at else 0
            print(f"[toku] using cached pricing ({age_h:.1f}h old, {len(cached)} models) — {_cache_path()}", file=sys.stderr)
        return cached, "cache"

    fetched = fetch_pricing()
    if fetched is not None:
        save_cached(fetched)
        if verbose:
            print(f"[toku] fetched {len(fetched)} models from OpenRouter", file=sys.stderr)
        return fetched, "fetch"

    # fetch failed
    if cached is not None:
        age = ""
        if fetched_at is not None:
            age_h = (time.time() - fetched_at) / 3600
            age = f" ({age_h:.1f}h old)"
        print(f"[toku] OpenRouter fetch failed, using stale cache{age} — {_cache_path()}", file=sys.stderr)
        return cached, "stale"

    print("[toku] OpenRouter fetch failed and no cache present — costs will show —", file=sys.stderr)
    return {}, "none"


def _candidates(model: str) -> list[str]:
    """Ordered exact-match candidates for a log model name."""
    cands: list[str] = []
    if not model:
        return cands
    raw = model.strip()
    cands.append(raw)
    # strip :free/:batch/:beta suffix (pricing distinguishes but logs often use :free)
    if ":" in raw:
        base_no_suffix = raw.split(":")[0]
        if base_no_suffix != raw:
            cands.append(base_no_suffix)
        # also try without colon variant already stripped; do not duplicate
    else:
        base_no_suffix = raw

    # provider-stripped suffix handling
    if "/" in base_no_suffix:
        suffix = base_no_suffix.split("/")[-1]
        if suffix and suffix not in cands:
            cands.append(suffix)
        # strip known variant tails from suffix
        for strip in ("-contributor", "-preview", "-free"):
            if suffix.endswith(strip):
                trimmed = suffix[: -len(strip)]
                if trimmed not in cands:
                    cands.append(trimmed)
        # :free after stripping slash already handled; no double
    else:
        # bare name like claude-sonnet-5 → try with known provider prefixes
        for prefix in ("anthropic/", "openai/", "deepseek/", "meta/", "xiaomi/", "tencent/", "stealth/", "google/", "qwen/"):
            cand = prefix + base_no_suffix
            if cand not in cands:
                cands.append(cand)
            # also try stripped -free/-contributor variant with prefix
            for strip in ("-free", "-contributor"):
                if base_no_suffix.endswith(strip):
                    cand2 = prefix + base_no_suffix[: -len(strip)]
                    if cand2 not in cands:
                        cands.append(cand2)

    # For provider-qualified input, also try swapping provider for known aliases
    # e.g. opencode-go/muse-spark-1.2-contributor → meta/muse-spark-1.2
    # We handle this via suffix fallback + tail scan below, but also add explicit
    # prefix swaps for common aliases to get exact hits before fuzzy scan.
    if "/" in base_no_suffix:
        suffix = base_no_suffix.split("/")[-1]
        # opencode-go alias table (best-effort)
        alias_map = {
            "muse-spark-1.2": "meta/muse-spark-1.2",
            "muse-spark-1.1": "meta/muse-spark-1.1",
            "mimo-v2.5": "xiaomi/mimo-v2.5",
            "mimo-v2.5-pro": "xiaomi/mimo-v2.5-pro",
            "hy3": "tencent/hy3",
            "ox-alpha": "stealth/ox-alpha",
            "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
            "deepseek-v4-flash-0731": "deepseek/deepseek-v4-flash-0731",
        }
        # strip variant tails for alias lookup
        lookup_suffix = suffix
        for strip in ("-contributor", "-free"):
            if lookup_suffix.endswith(strip):
                lookup_suffix = lookup_suffix[: -len(strip)]
                break
        if lookup_suffix in alias_map:
            ali = alias_map[lookup_suffix]
            if ali not in cands:
                cands.append(ali)
        if suffix in alias_map and alias_map[suffix] not in cands:
            cands.append(alias_map[suffix])

    # dedupe preserving order
    seen = set()
    out = []
    for cand in cands:
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


def resolve_model(model: str, pricing_map: dict) -> str | None:
    """Best-effort map log model name → OpenRouter id. Returns None on miss."""
    if not model or not pricing_map:
        return None
    cands = _candidates(model)
    for cand in cands:
        if cand in pricing_map:
            return cand
    # suffix-exact scan (case-insensitive) before substring-contains
    low_cands = [cand.lower() for cand in cands]
    # Build suffix set from stripped base
    base = model.split(":")[0].split("/")[-1].lower()
    base_stripped = base
    for strip in ("-contributor", "-preview", "-free"):
        if base_stripped.endswith(strip):
            base_stripped = base_stripped[: -len(strip)]
    # 1) exact suffix equality: id.split('/')[-1].lower() == base or base_stripped
    for target in (base, base_stripped):
        if not target:
            continue
        for pid in pricing_map:
            if pid.split("/")[-1].lower() == target:
                return pid
    # 2) for bare claude deepseek etc., try id endswith /base
    for target in (base, base_stripped):
        if not target:
            continue
        for pid in pricing_map:
            if pid.lower().endswith("/" + target):
                return pid
    # 3) substring contains as last resort (lowest confidence)
    # Only for non-tiny bases to avoid false positives
    if len(base_stripped) >= 6:
        for pid in pricing_map:
            if base_stripped in pid.split("/")[-1].lower():
                return pid
    return None


def estimate_cost(rec: dict, pricing_map: dict) -> float | None:
    """Estimate USD for a parsed toku record. Returns None if model unmapped."""
    if not pricing_map:
        return None
    model = rec.get("model") or ""
    pid = resolve_model(model, pricing_map)
    if pid is None:
        return None
    pricing = pricing_map[pid]
    # handle min_prompt_tokens override
    prompt_tokens = _safe_int(rec.get("input")) + _safe_int(rec.get("crd")) + _safe_int(rec.get("cwr"))
    overrides = pricing.get("overrides") if isinstance(pricing.get("overrides"), list) else []
    chosen = pricing
    # ponytail: time-window (utc_start/utc_end) pricing ignored — uses base price
    for ov in overrides:
        if not isinstance(ov, dict):
            continue
        if "min_prompt_tokens" in ov:
            try:
                threshold = int(ov["min_prompt_tokens"])
            except Exception:
                continue
            if prompt_tokens >= threshold:
                # merge override over base (only keys present in override replace base)
                merged = dict(pricing)
                for k, v in ov.items():
                    if k == "min_prompt_tokens":
                        continue
                    merged[k] = v
                chosen = merged
                break
    prompt_price = _parse_price(chosen, "prompt")
    completion_price = _parse_price(chosen, "completion")
    crd_price = _parse_price(chosen, "input_cache_read")
    cwr_price = _parse_price(chosen, "input_cache_write")
    # internal_reasoning fallback to completion
    reason_price = _parse_price(chosen, "internal_reasoning")
    if reason_price == 0:
        reason_price = completion_price

    cost = (
        _safe_int(rec.get("input")) * prompt_price
        + _safe_int(rec.get("output")) * completion_price
        + _safe_int(rec.get("crd")) * crd_price
        + _safe_int(rec.get("cwr")) * cwr_price
        + _safe_int(rec.get("reason")) * reason_price
    )
    return cost
