#!/usr/bin/env python3
"""Self-check for collect_agent_usage.py's per-source parsers.
Run directly: python3 test_collect_agent_usage.py
"""
import json
import os
import sqlite3
import tempfile

import collect_agent_usage as cau


def test_claude():
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"type": "system"}) + "\n")  # no usage, must be skipped
        f.write(json.dumps({
            "type": "assistant",
            "timestamp": "2026-08-05T17:16:12.633Z",
            "sessionId": "sess-1",
            "cwd": "/home/devhax/proj",
            "message": {
                "model": "claude-opus-5",
                "usage": {
                    "input_tokens": 2,
                    "output_tokens": 297,
                    "cache_read_input_tokens": 12774,
                    "cache_creation_input_tokens": 7254,
                },
            },
        }) + "\n")
        path = f.name
    try:
        recs = list(cau.parse_claude([path]))
        assert len(recs) == 1, f"expected 1 record, got {len(recs)}"
        r = recs[0]
        assert r["session_id"] == "sess-1"
        assert r["total_tokens"] == 2 + 297 + 12774 + 7254, r
        print("parse_claude: OK")
    finally:
        os.unlink(path)


def test_pi():
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"type": "user"}) + "\n")  # no usage, must be skipped
        f.write(json.dumps({
            "type": "message",
            "id": "msg-1",
            "timestamp": "2026-08-18T21:25:04.490Z",
            "message": {
                "role": "assistant",
                "responseModel": "deepseek/deepseek-v4-flash-0731",
                "usage": {
                    "input": 276, "output": 140, "cacheRead": 12544, "cacheWrite": 0,
                    "reasoning": 56, "totalTokens": 12960,
                    "cost": {"total": 0.000240878512},
                },
            },
        }) + "\n")
        path = f.name
    try:
        recs = list(cau.parse_pi([path]))
        assert len(recs) == 1, f"expected 1 record, got {len(recs)}"
        r = recs[0]
        assert r["total_tokens"] == 12960, r
        assert abs(r["cost_usd"] - 0.000240878512) < 1e-12, r
        print("parse_pi: OK")
    finally:
        os.unlink(path)


def test_opencode():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE message (id TEXT, session_id TEXT, data TEXT)")
        con.execute(
            "INSERT INTO message VALUES (?, ?, ?)",
            ("msg-1", "ses-1", json.dumps({
                "role": "assistant",
                "modelID": "big-pickle",
                "providerID": "opencode",
                "path": {"cwd": "/home/devhax/proj"},
                "cost": 0.0083,
                "tokens": {"total": 8452, "input": 8311, "output": 83, "reasoning": 58,
                           "cache": {"read": 0, "write": 0}},
                "time": {"created": 1781619828758},
            })),
        )
        con.execute(
            "INSERT INTO message VALUES (?, ?, ?)",
            ("msg-2", "ses-1", json.dumps({"role": "user"})),  # no tokens, must be skipped
        )
        con.commit()
        con.close()

        recs = list(cau.parse_opencode([path]))
        assert len(recs) == 1, f"expected 1 record, got {len(recs)}"
        r = recs[0]
        assert r["session_id"] == "ses-1"
        assert r["total_tokens"] == 8452, r
        assert r["model"] == "opencode/big-pickle", r
        print("parse_opencode: OK")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_claude()
    test_pi()
    test_opencode()
    print("all collect_agent_usage self-checks passed")
