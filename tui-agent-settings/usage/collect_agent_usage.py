#!/usr/bin/env python3
"""Discover local AI agent session logs (Claude Code, pi, OpenCode) and
combine their per-message token usage into one structured JSONL stream.

Antigravity (agy) is discovered but excluded from the combined output: its
local state (~/.antigravity/*.json) only ever holds a live remaining-quota
percentage per model, never a count of tokens actually consumed, so there is
no usage event to emit.

Usage: collect_agent_usage.py [--out FILE]   (default: JSONL to stdout)
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
PI_SESSIONS_DIR = os.path.expanduser("~/.pi/agent/sessions")
OPENCODE_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")
AGY_QUOTA_CACHE = os.path.expanduser("~/.antigravity/quota-cache.json")


def ms_to_iso(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def record(source, timestamp, session_id, project, model,
           input_tokens=0, output_tokens=0, cache_read_tokens=0,
           cache_write_tokens=0, reasoning_tokens=0, cost_usd=None,
           total_tokens=None):
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
    return {
        "source": source,
        "timestamp": timestamp,
        "session_id": session_id,
        "project": project,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
    }


def discover_claude():
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return []
    return sorted(
        os.path.join(dirpath, name)
        for dirpath, _dirs, names in os.walk(CLAUDE_PROJECTS_DIR)
        for name in names
        if name.endswith(".jsonl")
    )


def parse_claude(files):
    for path in files:
        try:
            f = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                message = entry.get("message") or {}
                usage = message.get("usage")
                if not usage:
                    continue
                yield record(
                    source="claude",
                    timestamp=entry.get("timestamp"),
                    session_id=entry.get("sessionId") or entry.get("session_id"),
                    project=entry.get("cwd"),
                    model=message.get("model"),
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
                    cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
                    cost_usd=None,  # not persisted in these logs
                )


def discover_pi():
    if not os.path.isdir(PI_SESSIONS_DIR):
        return []
    return sorted(
        os.path.join(dirpath, name)
        for dirpath, _dirs, names in os.walk(PI_SESSIONS_DIR)
        for name in names
        if name.endswith(".jsonl")
    )


def parse_pi(files):
    for path in files:
        project_slug = os.path.basename(os.path.dirname(path))
        try:
            f = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = entry.get("type")
                if etype == "message":
                    message = entry.get("message") or {}
                    usage = message.get("usage")
                    model = message.get("responseModel") or message.get("model")
                elif etype in ("compaction", "branch_summary"):
                    usage = entry.get("usage")
                    model = entry.get("model")
                else:
                    continue
                if not usage:
                    continue
                cost = (usage.get("cost") or {}).get("total")
                yield record(
                    source="pi",
                    timestamp=entry.get("timestamp"),
                    session_id=entry.get("id"),
                    project=project_slug,
                    model=model,
                    input_tokens=int(usage.get("input") or 0),
                    output_tokens=int(usage.get("output") or 0),
                    cache_read_tokens=int(usage.get("cacheRead") or 0),
                    cache_write_tokens=int(usage.get("cacheWrite") or 0),
                    reasoning_tokens=int(usage.get("reasoning") or 0),
                    total_tokens=usage.get("totalTokens"),
                    cost_usd=float(cost) if cost is not None else None,
                )


def discover_opencode():
    return [OPENCODE_DB] if os.path.isfile(OPENCODE_DB) else []


def parse_opencode(db_files):
    if not db_files:
        return
    con = sqlite3.connect(f"file:{db_files[0]}?mode=ro", uri=True)
    try:
        cur = con.execute("SELECT session_id, data FROM message")
        for session_id, raw in cur:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("role") != "assistant" or "tokens" not in data:
                continue
            tokens = data.get("tokens") or {}
            cache = tokens.get("cache") or {}
            created_ms = ((data.get("time") or {}).get("created"))
            model = data.get("modelID")
            provider = data.get("providerID")
            yield record(
                source="opencode",
                timestamp=ms_to_iso(created_ms) if created_ms else None,
                session_id=session_id,
                project=(data.get("path") or {}).get("cwd"),
                model=f"{provider}/{model}" if provider else model,
                input_tokens=int(tokens.get("input") or 0),
                output_tokens=int(tokens.get("output") or 0),
                cache_read_tokens=int(cache.get("read") or 0),
                cache_write_tokens=int(cache.get("write") or 0),
                reasoning_tokens=int(tokens.get("reasoning") or 0),
                total_tokens=tokens.get("total"),
                cost_usd=data.get("cost"),
            )
    finally:
        con.close()


def discover_antigravity():
    return [AGY_QUOTA_CACHE] if os.path.isfile(AGY_QUOTA_CACHE) else []


SOURCES = [
    ("claude", discover_claude, parse_claude),
    ("pi", discover_pi, parse_pi),
    ("opencode", discover_opencode, parse_opencode),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="write combined JSONL here instead of stdout")
    args = ap.parse_args()

    all_records = []
    for name, discover, parse in SOURCES:
        files = discover()
        recs = list(parse(files))
        all_records.extend(recs)
        print(f"[discover] {name}: {len(files)} log file(s) -> {len(recs)} usage record(s)", file=sys.stderr)

    agy_files = discover_antigravity()
    print(
        f"[discover] antigravity: {len(agy_files)} state file(s) found — "
        "no token counters exposed (only live remaining-quota %), excluded from output",
        file=sys.stderr,
    )

    all_records.sort(key=lambda r: r["timestamp"] or "")

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        for rec in all_records:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    finally:
        if args.out:
            out.close()

    totals = {}
    for rec in all_records:
        totals[rec["source"]] = totals.get(rec["source"], 0) + rec["total_tokens"]
    print(f"[combine] {len(all_records)} record(s) total; tokens by source: {totals}", file=sys.stderr)


if __name__ == "__main__":
    main()
