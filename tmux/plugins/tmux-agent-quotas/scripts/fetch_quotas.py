#!/usr/bin/env python3
"""Aggregates Antigravity (agy) and Claude Code subscription quotas,
and generates pre-rendered tmux status segments.
"""
import os
import sys
import json
import time
import re
import subprocess
import http.client
import ssl
from datetime import datetime, timezone

CACHE_DIR = os.path.expanduser("~/.cache/agent-quotas")
AGY_CACHE_FILE = os.environ.get(
    "AGY_QUOTA_CACHE",
    os.path.expanduser("~/.antigravity/quota-cache.json"),
)
STATUS_STATE_FILE = os.environ.get(
    "AGY_STATUS_STATE",
    os.path.expanduser("~/.antigravity/status-state.json"),
)
CLAUDE_CACHE_FILE = os.path.join(CACHE_DIR, "claude.json")
OUTPUT_STATUS_JSON = os.path.join(CACHE_DIR, "status.json")
OUTPUT_AGY_TXT = os.path.join(CACHE_DIR, "agy.txt")
OUTPUT_CLAUDE_TXT = os.path.join(CACHE_DIR, "claude.txt")
OUTPUT_COMBINED_TXT = os.path.join(CACHE_DIR, "combined.txt")

USER_STATUS_PATH = "/exa.language_server_pb.LanguageServerService/GetUserStatus"


def format_reset_time(reset_time_str: str) -> str:
    if not reset_time_str:
        return ""
    try:
        reset = datetime.fromisoformat(reset_time_str.replace("Z", "+00:00"))
        diff = int((reset - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return ""

    if diff <= 0:
        return "now"
    minutes = (diff + 59) // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        days, rem_hours = divmod(hours, 24)
        return f"{days}d{rem_hours}h" if rem_hours else f"{days}d"
    return f"{hours}h{mins}m" if mins else f"{hours}h"


def format_epoch_reset(epoch: float) -> str:
    if not epoch:
        return ""
    try:
        diff = int(epoch - time.time())
        if diff <= 0:
            return "now"
        minutes = (diff + 59) // 60
        if minutes < 60:
            return f"{minutes}m"
        hours, mins = divmod(minutes, 60)
        return f"{hours}h{mins}m" if mins else f"{hours}h"
    except Exception:
        return ""


def extract_arg(command_line: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}(?:=|\s+)([^\s\"']+|\"[^\"]+\"|'[^']+')", command_line)
    if not match:
        return ""
    return match.group(1).strip("\"'")


def find_server_candidates() -> list[dict]:
    try:
        ps = subprocess.check_output(["ps", "auxww"], text=True, stderr=subprocess.DEVNULL, timeout=1.5)
    except Exception:
        return []

    candidates = []
    for line in ps.splitlines():
        lower = line.lower()
        is_cli = re.search(r"\bagy(\s|$)", line) is not None
        is_language_server = "language_server" in lower
        if not is_cli and not is_language_server:
            continue
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        token = extract_arg(parts[10], "--csrf_token")
        score = 10
        if is_cli:
            score += 40
        if is_language_server:
            score += 20
        if token:
            score += 10
        candidates.append({
            "pid": pid,
            "csrf_token": token,
            "score": score,
            "kind": "cli" if is_cli else "language_server",
        })

    return sorted(candidates, key=lambda x: x["score"], reverse=True)


def get_listening_ports(pid: int) -> list[int]:
    try:
        socket_inodes = set()
        fd_dir = f"/proc/{pid}/fd"
        if os.path.exists(fd_dir):
            for fd in os.listdir(fd_dir):
                try:
                    link = os.readlink(os.path.join(fd_dir, fd))
                    if link.startswith("socket:[") and link.endswith("]"):
                        socket_inodes.add(link[8:-1])
                except Exception:
                    pass

        if socket_inodes:
            ports = set()
            for net_file in (f"/proc/{pid}/net/tcp", f"/proc/{pid}/net/tcp6", "/proc/net/tcp", "/proc/net/tcp6"):
                if not os.path.exists(net_file):
                    continue
                try:
                    with open(net_file, "r") as f:
                        lines = f.readlines()[1:]
                    for line in lines:
                        parts = line.strip().split()
                        if len(parts) >= 10:
                            state = parts[3]
                            inode = parts[9]
                            if state == "0A" and inode in socket_inodes:
                                local_addr = parts[1]
                                port_hex = local_addr.rsplit(":", 1)[-1]
                                ports.add(int(port_hex, 16))
                except Exception:
                    pass
            if ports:
                return sorted(list(ports))
    except Exception:
        pass

    try:
        out = subprocess.check_output(["ss", "-Htlpn"], text=True, stderr=subprocess.DEVNULL, timeout=1.5)
        ports = set()
        for line in out.splitlines():
            if re.search(rf"\bpid={pid}\b", line):
                parts = line.split()
                if len(parts) >= 4:
                    local_addr = parts[3]
                    port_str = local_addr.rsplit(":", 1)[-1]
                    if port_str.isdigit():
                        ports.add(int(port_str))
        if ports:
            return sorted(list(ports))
    except Exception:
        pass

    return []


def request_user_status(port: int, csrf_token: str, use_https: bool) -> dict:
    body = json.dumps({
        "metadata": {
            "ideName": "antigravity",
            "extensionName": "antigravity",
            "locale": "en",
        }
    })
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Connect-Protocol-Version": "1",
    }
    if csrf_token:
        headers["X-Codeium-Csrf-Token"] = csrf_token
    if use_https:
        conn = http.client.HTTPSConnection(
            "127.0.0.1",
            port,
            timeout=2,
            context=ssl._create_unverified_context(),
        )
    else:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("POST", USER_STATUS_PATH, body, headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8", "replace")
    if res.status < 200 or res.status >= 300:
        raise RuntimeError(f"HTTP {res.status}")
    return json.loads(raw)


def fetch_live_agy_quota() -> dict:
    for process_info in find_server_candidates():
        ports = get_listening_ports(process_info["pid"])
        for port in ports:
            for use_https in (True, False):
                try:
                    response = request_user_status(
                        port,
                        process_info.get("csrf_token", ""),
                        use_https,
                    )
                    user_status = response.get("userStatus", {})
                    cascade = user_status.get("cascadeModelConfigData", {})
                    models = {}
                    for model in cascade.get("clientModelConfigs", []) or []:
                        quota_info = model.get("quotaInfo") or {}
                        if "remainingFraction" not in quota_info:
                            continue
                        label = model.get("label") or model.get("modelOrAlias", {}).get("model") or "Unknown"
                        remaining = max(0.0, min(100.0, float(quota_info.get("remainingFraction", 0)) * 100))
                        entry = {
                            "name": label,
                            "remaining_percentage": remaining,
                        }
                        reset_time = quota_info.get("resetTime")
                        if reset_time:
                            entry["reset_time"] = reset_time
                            entry["refreshes_in"] = format_reset_time(reset_time)
                        models[label.lower()] = entry
                    if models:
                        return {
                            "timestamp": time.time(),
                            "source": "live",
                            "models": models,
                            "user": user_status.get("email", ""),
                        }
                except Exception:
                    continue
    return {}


def load_cached_agy_quota() -> dict:
    if not os.path.exists(AGY_CACHE_FILE):
        return {}
    try:
        with open(AGY_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception:
        return {}


def load_claude_quota() -> dict:
    if not os.path.exists(CLAUDE_CACHE_FILE):
        return {}
    try:
        with open(CLAUDE_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_color_tag(pct: float, high: str = "#[fg=colour120,bold]", med: str = "#[fg=colour221,bold]", low: str = "#[fg=colour203,bold]") -> str:
    if pct >= 50.0:
        return high
    elif pct >= 20.0:
        return med
    return low


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)

    # 1. Fetch Antigravity quota
    agy_data = fetch_live_agy_quota()
    if not agy_data:
        agy_data = load_cached_agy_quota()

    # Determine primary model / quota for AGY
    agy_models = agy_data.get("models", {})
    agy_summary = None
    if agy_models:
        # Prioritize key active models if present, else highest remaining or first
        preferred = ["gemini 2.5 pro", "claude 3.7 sonnet", "claude 3.5 sonnet", "gemini 2.0 flash", "flash"]
        selected_model = None
        for pref in preferred:
            for k, v in agy_models.items():
                if pref in k:
                    selected_model = v
                    break
            if selected_model:
                break
        if not selected_model:
            selected_model = next(iter(agy_models.values()))

        pct = float(selected_model.get("remaining_percentage", 0.0))
        refreshes_in = selected_model.get("refreshes_in") or format_reset_time(selected_model.get("reset_time", ""))
        agy_summary = {
            "name": selected_model.get("name", "AGY"),
            "remaining_pct": pct,
            "refreshes_in": refreshes_in,
        }

    # 2. Fetch Claude quota
    claude_data = load_claude_quota()
    claude_summary = None
    if claude_data:
        five_h_used = claude_data.get("five_hour_used_pct")
        seven_d_used = claude_data.get("seven_day_used_pct")
        five_h_reset = claude_data.get("five_hour_resets_at")
        seven_d_reset = claude_data.get("seven_day_resets_at")

        claude_summary = {
            "model": claude_data.get("model", "Claude"),
            "five_hour_used_pct": five_h_used,
            "five_hour_remaining_pct": (100.0 - float(five_h_used)) if five_h_used is not None else None,
            "five_hour_resets_in": format_epoch_reset(five_h_reset) if five_h_reset else "",
            "seven_day_used_pct": seven_d_used,
            "seven_day_remaining_pct": (100.0 - float(seven_d_used)) if seven_d_used is not None else None,
            "seven_day_resets_in": format_epoch_reset(seven_d_reset) if seven_d_reset else "",
        }

    # 3. Build tmux formatted strings
    # AGY Segment
    if agy_summary:
        pct = agy_summary["remaining_pct"]
        color = get_color_tag(pct)
        rst = agy_summary["refreshes_in"]
        rst_str = f" {rst}" if rst else ""
        agy_txt = f"{color}AGY {pct:.0f}%{rst_str}#[default]"
    else:
        agy_txt = "#[fg=colour244]AGY --#[default]"

    # Claude Segment (current 5h quota + countdown only, no 7d weekly)
    if claude_summary and claude_summary["five_hour_used_pct"] is not None:
        rem = claude_summary["five_hour_remaining_pct"]
        col = get_color_tag(rem)
        rst = claude_summary["five_hour_resets_in"]
        rst_str = f" {rst}" if rst else ""
        claude_txt = f"{col}CC {rem:.0f}%{rst_str}#[default]"
    else:
        claude_txt = "#[fg=colour244]CC --#[default]"

    # Combined Segment
    combined_parts = []
    if agy_summary:
        combined_parts.append(agy_txt)
    if claude_summary and claude_summary["five_hour_used_pct"] is not None:
        combined_parts.append(claude_txt)

    if combined_parts:
        combined_txt = " #[fg=colour240]│#[default] ".join(combined_parts)
    else:
        combined_txt = f"{agy_txt} #[fg=colour240]│#[default] {claude_txt}"

    # Write files atomically
    for target_file, content in [
        (OUTPUT_AGY_TXT, agy_txt),
        (OUTPUT_CLAUDE_TXT, claude_txt),
        (OUTPUT_COMBINED_TXT, combined_txt),
    ]:
        tmp = f"{target_file}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, target_file)

    # Save full status json
    status_payload = {
        "timestamp": time.time(),
        "antigravity": agy_summary,
        "claude": claude_summary,
    }
    tmp_json = f"{OUTPUT_STATUS_JSON}.tmp"
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(status_payload, f, indent=2)
    os.replace(tmp_json, OUTPUT_STATUS_JSON)


if __name__ == "__main__":
    main()
