import os
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from models import RecordInput
from db import ErrorDatabase

SEED_RECORDS = [
    RecordInput(
        error_type="GitLockError",
        error_message="Fatal: Unable to create '.git/index.lock': File exists.",
        stack_trace="""fatal: Unable to create '/home/devhax/workspace/.git/index.lock': File exists.
Another git process seems to be running in this repository, e.g.
an editor opened by 'git commit'. Please make sure all processes
are terminated then try again. If it still fails, a git process may
have crashed in this repository earlier: remove the file manually to continue.""",
        cause="Parallel git operations initiated by autonomous background subagents created a lingering stale '.git/index.lock' lockfile.",
        patch_or_fix="""# Check if git process is currently active, if not safe to remove lock:
pgrep -f "git " || rm -f .git/index.lock""",
        explanation="Stale lockfile left behind when an async background git task terminates unexpectedly or when concurrent subagents access index simultaneously.",
        tags=["git", "concurrency", "lockfile", "subagent"],
        agent_environment={"os": "linux", "runtime": "git 2.39.0", "framework": "agent-orchestrator"},
        verification_score=4.8
    ),
    RecordInput(
        error_type="SQLiteLockedError",
        error_message="sqlite3.OperationalError: database is locked",
        stack_trace="""Traceback (most recent call last):
  File "/home/devhax/app/service.py", line 42, in execute_transaction
    cursor.execute("UPDATE state SET value = ? WHERE key = ?", (val, key))
sqlite3.OperationalError: database is locked""",
        cause="Concurrent write transactions attempted on SQLite database operating in default rollback journal mode without WAL enabled.",
        patch_or_fix="""import sqlite3

conn = sqlite3.connect("app.db", timeout=30.0)
# Enable Write-Ahead Logging (WAL) mode for concurrency
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout = 30000;")""",
        explanation="WAL (Write-Ahead Logging) mode allows readers to read while writers write, avoiding locked database exceptions in concurrent Python microservices.",
        tags=["sqlite", "database", "concurrency", "python"],
        agent_environment={"os": "linux", "python": "3.12", "sqlite_version": "3.42.0"},
        verification_score=5.0
    ),
    RecordInput(
        error_type="JSONDecodeError",
        error_message="json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
        stack_trace="""Traceback (most recent call last):
  File "/home/devhax/agent/tool_runner.py", line 85, in parse_tool_output
    result = json.loads(stdout)
  File "/usr/lib/python3.12/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)""",
        cause="Subprocess tool emitted diagnostic logs or warnings preceding the raw JSON output payload, breaking direct `json.loads` parsing.",
        patch_or_fix="""import re
import json

def extract_and_parse_json(text: str) -> dict:
    match = re.search(r'(\\{.*\\}|\\[.*\\])', text, re.DOTALL)
    if not match:
        raise ValueError(f"No valid JSON object found in raw string: {text[:100]}")
    return json.loads(match.group(1))""",
        explanation="Extracting JSON substring using regex ensures leading/trailing non-JSON stdout messages don't break agent structured tool output parsing.",
        tags=["json", "parsing", "tool-call", "regex"],
        agent_environment={"os": "linux", "python": "3.12"},
        verification_score=4.9
    ),
    RecordInput(
        error_type="NPMGlobalPermissionError",
        error_message="EACCES: permission denied, mkdir '/usr/local/lib/node_modules'",
        stack_trace="""npm ERR! code EACCES
npm ERR! syscall mkdir
npm ERR! path /usr/local/lib/node_modules/bun
npm ERR! errno -13
npm ERR! Error: EACCES: permission denied, mkdir '/usr/local/lib/node_modules'""",
        cause="Attempting global npm package installation into system-protected `/usr/local/lib` directory without root privileges.",
        patch_or_fix="""# Configure custom user-level npm prefix
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
export PATH=~/.npm-global/bin:$PATH""",
        explanation="Setting a user-owned npm global directory eliminates root/sudo requirement for global CLI tools.",
        tags=["npm", "bun", "permissions", "eacces", "node"],
        agent_environment={"os": "linux", "node": "20.11.0", "npm": "10.2.4"},
        verification_score=4.7
    ),
    RecordInput(
        error_type="DockerPermissionError",
        error_message="PermissionError: [Errno 13] Permission denied: '/var/run/docker.sock'",
        stack_trace="""docker.errors.DockerException: Error while fetching server API version: 
('Connection aborted.', PermissionError(13, 'Permission denied'))
[Errno 13] Permission denied: '/var/run/docker.sock'""",
        cause="Agent executed Docker container management commands without user membership in the system `docker` security group.",
        patch_or_fix="""# Add current user to docker group and adjust socket permissions if needed:
sudo usermod -aG docker $USER
# Or adjust socket access for dev environment:
sudo chmod 666 /var/run/docker.sock""",
        explanation="Docker daemon Unix socket requires docker group membership or direct socket access permissions.",
        tags=["docker", "permissions", "linux", "socket"],
        agent_environment={"os": "linux", "docker": "24.0.5"},
        verification_score=4.6
    ),
    RecordInput(
        error_type="ModuleNotFoundError",
        error_message="ModuleNotFoundError: No module named 'fastapi'",
        stack_trace="""Traceback (most recent call last):
  File "/home/devhax/projects/agent-error-kb/backend/api_server.py", line 2, in <module>
    from fastapi import FastAPI
ModuleNotFoundError: No module named 'fastapi'""",
        cause="Executing Python script with global system python interpreter instead of active virtualenv or `uv run` launcher.",
        patch_or_fix="""# Run using uv which automatically executes in the project's virtualenv:
uv run python backend/api_server.py

# Or activate virtualenv explicitly:
source .venv/bin/activate""",
        explanation="Using `uv run` guarantees that all dependencies declared in pyproject.toml and installed in .venv are loaded into sys.path.",
        tags=["uv", "python", "virtualenv", "imports"],
        agent_environment={"os": "linux", "uv": "0.4.0", "python": "3.12"},
        verification_score=5.0
    ),
    RecordInput(
        error_type="SubprocessTimeoutError",
        error_message="subprocess.TimeoutExpired: Command 'git log' timed out after 30 seconds",
        stack_trace="""Traceback (most recent call last):
  File "/home/devhax/agent/tools.py", line 110, in run_cmd
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
  File "/usr/lib/python3.12/subprocess.py", line 575, in run
    raise TimeoutExpired(process.args, timeout, output=stdout, stderr=stderr)
subprocess.TimeoutExpired: Command 'git log' timed out after 30 seconds""",
        cause="Interactive terminal CLI command (e.g. `git log`, `less`) launched in subprocess without setting `PAGER=cat` waiting infinitely for user keystrokes.",
        patch_or_fix="""import os
import subprocess

env = os.environ.copy()
env["PAGER"] = "cat"
env["GIT_PAGER"] = "cat"

res = subprocess.run(["git", "log", "-n", "10"], capture_output=True, text=True, env=env, timeout=10)""",
        explanation="Setting PAGER=cat prevents subprocesses from waiting for terminal interactive pagination.",
        tags=["subprocess", "timeout", "git", "pager", "cli"],
        agent_environment={"os": "linux", "python": "3.12"},
        verification_score=4.9
    ),
    RecordInput(
        error_type="OpenAIRateLimitError",
        error_message="openai.RateLimitError: Rate limit reached for model gpt-4o",
        stack_trace="""openai.RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-4o in organization org-xxx on requests per min (RPM): Limit 500, Used 500, Requested 1.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}""",
        cause="High-frequency parallel LLM tool invocation burst exceeded API organization Requests Per Minute (RPM) quota.",
        patch_or_fix="""from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
import openai

@retry(
    wait=wait_random_exponential(min=1, max=60),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(openai.RateLimitError)
)
def call_llm_with_backoff(prompt):
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])""",
        explanation="Exponential backoff with randomized jitter spreads retries dynamically, satisfying API rate limit controllers.",
        tags=["openai", "rate-limit", "backoff", "tenacity", "llm"],
        agent_environment={"os": "linux", "python": "3.12", "openai_version": "1.30.0"},
        verification_score=4.8
    ),
    RecordInput(
        error_type="MemoryLimitExceededError",
        error_message="MemoryError: Process killed (SIGKILL - Out of Memory)",
        stack_trace="""Process killed (SIGKILL) - Memory usage exceeded cgroup limit (8192 MB).
Traceback (most recent call last):
  File "/home/devhax/agent/log_analyzer.py", line 15, in parse_huge_file
    content = f.read() # Reading 12GB log file at once into memory""",
        cause="Attempting to read an entire multi-gigabyte log file into RAM at once using single string read instead of chunked streaming.",
        patch_or_fix="""def read_log_chunks(file_path, chunk_size=1024*1024):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk""",
        explanation="Chunked generator streaming maintains constant O(1) RAM consumption regardless of total file size.",
        tags=["memory", "oom", "streaming", "io", "performance"],
        agent_environment={"os": "linux", "ram": "8GB"},
        verification_score=4.7
    ),
    RecordInput(
        error_type="PathTraversalError",
        error_message="ValueError: Path outside workspace sandbox root",
        stack_trace="""Traceback (most recent call last):
  File "/home/devhax/agent/file_tool.py", line 28, in read_workspace_file
    validate_path(target_path)
ValueError: Access denied: '/etc/passwd' resolves outside allowed root directory '/home/devhax/projects'""",
        cause="Relative path input contained `../` sequences resolving outside the allowed workspace sandbox root directory.",
        patch_or_fix="""from pathlib import Path

def resolve_safe_path(base_dir: str, user_path: str) -> Path:
    sandbox = Path(base_dir).resolve()
    target = (sandbox / user_path).resolve()
    if not target.is_relative_to(sandbox):
        raise ValueError(f"Path traversal blocked: {user_path}")
    return target""",
        explanation="Using `Path.resolve()` and `is_relative_to()` canonicalizes symlinks and parent directory traversals cleanly.",
        tags=["security", "path-traversal", "sandbox", "validation"],
        agent_environment={"os": "linux", "python": "3.12"},
        verification_score=4.9
    ),
    RecordInput(
        error_type="LayoutOverflowError",
        error_message="LayoutOverflowError: Text rendered outside parent box bounds",
        stack_trace="""Component render error: Dynamic markdown container height computed as fixed offset:
`containerHeight = titleHeight + 12`
Failed when markdown contained multi-line code block, causing overflow of 340px.""",
        cause="Hardcoding static numeric offsets (`+ 12`) to calculate dynamic UI element heights instead of inspecting actual element bounding boxes.",
        patch_or_fix="""// In CSS / UI layout engine:
.container {
  display: flex;
  flex-direction: column;
  height: auto;
  min-height: 0;
  overflow: auto;
}""",
        explanation="Flexbox/Grid layout with dynamic auto-sizing replaces fragile fixed pixel offset math.",
        tags=["frontend", "css", "layout", "overflow", "ui"],
        agent_environment={"os": "linux", "browser": "chromium", "framework": "react"},
        verification_score=4.5
    ),
    RecordInput(
        error_type="HTTPKeepAliveTimeoutError",
        error_message="httpx.RemoteProtocolError: Server disconnected without sending a response",
        stack_trace="""Traceback (most recent call last):
  File "/home/devhax/agent/http_client.py", line 54, in fetch
    resp = client.get(url)
  File "/usr/local/lib/python3.12/site-packages/httpx/_client.py", line 1054, in get
    return self.request("GET", url, ...)
httpx.RemoteProtocolError: Server disconnected without sending a response.""",
        cause="HTTP client pool attempted to reuse a TCP keep-alive connection that had been closed by remote server idle timeout.",
        patch_or_fix="""import httpx

# Configure client pool with reasonable keepalive expiry and retry on connection reset
client = httpx.Client(
    timeout=httpx.Timeout(30.0, connect=10.0),
    limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=15.0)
)""",
        explanation="Setting `keepalive_expiry=15.0` ensures idle connections are discarded before remote servers forcibly reset them.",
        tags=["httpx", "http", "network", "keepalive", "async"],
        agent_environment={"os": "linux", "httpx": "0.27.0"},
        verification_score=4.8
    )
]

def seed_database():
    db = ErrorDatabase()
    print("🌱 Seeding AI Agent Error Knowledge Base with 12 real-world records...")
    inserted_count = 0
    for record_in in SEED_RECORDS:
        err_rec, sol_rec = db.add_record(record_in)
        print(f"  [+] Seeded: [{err_rec.error_type}] -> FP: {err_rec.fingerprint[:12]}... (Solution ID: {sol_rec.id[:8]})")
        inserted_count += 1
    print(f"✅ Successfully seeded {inserted_count} error & solution records into SQLite database!\n")

if __name__ == "__main__":
    seed_database()
