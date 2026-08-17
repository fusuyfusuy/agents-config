# Repository Map

38 files · 3634 lines of parsed code · ranked by import in-degree + 90d churn + entry points

## Entry points

- `status/status.py`
- `setup.sh`
- `bin/agent-kb/backend/cli.py`
- `bin/agent-ctx`
- `claude/statusline-command.sh`
- `status/agy-quota-cache.py`
- `status/statusline.sh`

## Core modules

`bin/agent-kb/backend/models.py` · 57 ln · ← cli, db, kb_engine, seed_data, +1 · 1 commit/90d
  :4    class Solution
  :14   class ErrorRecord
  :27   class RecordInput
  :38   class SearchQuery
  :45   class SearchResult
  :52   class ErrorPattern

`bin/agent-kb/backend/db.py` · 441 ln · ← cli, seed_data, test_backend, verify_kb · 1 commit/90d
  :13   class ErrorDatabase
  :19     __init__(db_path: Optional[Path]=None)
  :26     get_connection() -> sqlite3.Connection
  :87     add_record(record_input: RecordInput) -> Tuple[ErrorRecord, Solution]
  :139    get_error_record_with_solution(error_id: str, solution_id: str) -> Tuple[ErrorRecord, S…
  :192    search_solutions(query: str, error_type: Optional[str]=None, tags: Optional[List[str]]=…
  :334    list_patterns(limit: int=10) -> List[ErrorPattern]
  :391    verify_solution(solution_id: str, increment: int=1) -> Optional[Solution]
  :424    get_all_records(limit: int=50, offset: int=0) -> List[ErrorRecord]
  :436    get_record_by_id(record_id: str) -> Optional[ErrorRecord]

`status/status.py` · 675 ln · 7 commits/90d · entry point
  "Antigravity IDE — Status Line Script"
  :64   format_tokens(n: int) -> str
  :72   context_color(pct: float) -> str
  :81   normalize_model_name(name: str) -> str
  :85   shorten_model_name(name: str) -> str
  :128  quota_color(pct: float) -> str
  :136  format_reset_time(reset_time: str) -> str
  :155  extract_arg(command_line: str, name: str) -> str
  :162  find_server_candidates() -> list[dict]
  :202  get_listening_ports(pid: int) -> list[int]
  :280  request_user_status(port: int, csrf_token: str, use_https: bool) -> dict
  :312  parse_user_status_quota(response: dict) -> dict
  :347  fetch_live_quota_cache(expected_email: str='') -> dict
  ... +11 more symbols

`bin/agent-kb/backend/cli.py` · 130 ln · ← test_backend · 1 commit/90d · entry point
  :26   _infer_error_type(text: str) -> str
  :46   cli()
  :55   lookup(query: str, error_type: str, limit: int, out_format: str)
  :84   record(error: Optional[str], error_type: Optional[str], error_message: Optional[str], s…
  :111  patterns(limit: int)
  :124  seed()

`bin/agent-ctx` · 1252 ln · 3 commits/90d · entry point
  "agent-ctx: Zero-daemon Agent Context, Memory, Repo Mapping & Activity Tracking CLI."
  :86   find_repo_root(start: Optional[Path]=None) -> Path
  :94   run_git(root: Path, *args: str, timeout: int=5) -> Optional[str]
  :108  get_git_branch(root: Path) -> Optional[str]
  :124  should_ignore(rel_path: Path) -> bool
  :128  list_files(root: Path) -> List[str]
  :151  get_churn(root: Path, days: int=CHURN_DAYS) -> Dict[str, int]
  :165  get_working_state(root: Path) -> Optional[str]
  :196  class FileInfo
  :199    __init__(path: str, size: int)
  :212    in_degree() -> int
  :216    score() -> int
  :220  _elide(text: str, limit: int) -> str
  ... +43 more symbols

`bin/agent-kb/backend/kb_engine.py` · 168 ln · ← cli, db · 1 commit/90d
  :8    class KBEngine
  :14     normalize_error(text: str) -> str
  :57     compute_fingerprint(normalized_trace: str, error_type: str='') -> str
  :65     tokenize(text: str) -> List[str]
  :73     calculate_token_similarity(text1: str, text2: str) -> float
  :110    format_markdown_context(results: List[SearchResult]) -> str
  :146    format_json_context(results: List[SearchResult]) -> Dict[str, Any]

`bin/agent-kb/backend/seed_data.py` · 262 ln · ← cli, db · 1 commit/90d
  :250  seed_database()

`status/agy-quota-cache.py` · 128 ln · 1 commit/90d · entry point
  "Cache Antigravity `/usage` model quota output for the status line."
  :24   normalize_model_name(name: str) -> str
  :28   parse_usage(text: str) -> dict
  :69   load_existing_cache() -> dict
  :79   load_status_scope() -> dict
  :92   main() -> int

## Supporting files

`bin/agent-kb/tests/test_backend.py` · 83 ln · 2 commits/90d · :17 class TestAgentErrorKB

`bin/agent-kb/tests/verify_kb.py` · 55 ln · 2 commits/90d · :11 main

`tmux/plugins/tmux-agent-quotas/scripts/fetch_quotas.py` · 383 ln · 1 commit/90d · :33 format_reset_time · :54 format_epoch_reset · :70 extract_arg · :77 find_server_candidates · :115 get_listening_ports · :171 request_user_status

## Other files

- `.` — 5 files ((no ext), .md, .sh)
- `.agents/` — 4 files (.jsonl, .md)
- `antigravity-cli/` — `settings.json`, `keybindings.json`
- `bin/agent-kb/` — 4 files ((no ext), .lock, .md, .toml)
- `claude/` — `statusline-command.sh`, `settings.json`
- `claude/skills/agent-context/` — `SKILL.md`
- `claude/skills/agent-error-kb/` — `SKILL.md`
- `claude/skills/agent-processes/` — `SKILL.md`
- `config/` — `mcp_config.json`, `config.json`
- `status/` — `statusline.sh`
- `tmux/plugins/tmux-agent-quotas/` — `README.md`, `tmux-agent-quotas.tmux`
- `tmux/plugins/tmux-agent-quotas/scripts/` — `helpers.sh`, `render_status.sh`

_Detailed 11 of 38 files; 27 collapsed above._