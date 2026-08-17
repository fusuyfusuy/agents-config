import os
import sys
import re
import json
import click
from typing import Optional
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

bin_script = Path.home() / ".local/bin/agent-kb"
if bin_script.exists():
    try:
        os.chmod(bin_script, 0o755)
    except Exception:
        pass

from models import RecordInput, SearchQuery
from db import ErrorDatabase
from kb_engine import KBEngine
from seed_data import seed_database

db = ErrorDatabase()

def _infer_error_type(text: str) -> str:
    if not text:
        return "AgentError"
    first_line = text.strip().splitlines()[0]
    match = re.search(r'\b([A-Z][a-zA-Z0-9_]*(?:Error|Exception))\b', first_line)
    if match:
        return match.group(1)
    if "git" in first_line.lower():
        return "GitError"
    if "permission denied" in first_line.lower() or "eacces" in first_line.lower():
        return "PermissionError"
    if "lock" in first_line.lower():
        return "LockError"
    if ":" in first_line:
        prefix = first_line.split(":")[0].strip()
        if " " not in prefix and len(prefix) < 40 and prefix:
            return prefix
    return "AgentError"

@click.group()
def cli():
    """🤖 AI Agent Error Knowledge Base CLI (agent-kb)"""
    pass

@cli.command()
@click.argument('query', type=str)
@click.option('--type', '-t', 'error_type', default=None, help='Filter by error type (e.g. PermissionError)')
@click.option('--limit', '-l', default=5, type=int, help='Maximum number of results to return')
@click.option('--format', '-f', 'out_format', type=click.Choice(['markdown', 'json', 'text']), default='markdown', help='Output format')
def lookup(query: str, error_type: str, limit: int, out_format: str):
    """Lookup solutions for an error trace or description."""
    results = db.search_solutions(query=query, error_type=error_type, limit=limit)

    if not results:
        click.echo("❌ No matching error solutions found in Knowledge Base.")
        return

    if out_format == 'markdown':
        click.echo(KBEngine.format_markdown_context(results))
    elif out_format == 'json':
        click.echo(json.dumps(KBEngine.format_json_context(results), indent=2))
    else:
        click.echo(f"Found {len(results)} matching solutions:\n")
        for res in results:
            click.echo(f"[{res.match_type.upper()}] Match Score: {int(res.confidence_score*100)}%")
            click.echo(f"  Error: {res.record.error_type} - {res.record.error_message}")
            click.echo(f"  Root Cause: {res.matched_solution.cause}")
            click.echo(f"  Fix:\n{res.matched_solution.patch_or_fix}\n")

@cli.command()
@click.option('--error', '-err', default=None, help='Raw error message, stack trace, or error string')
@click.option('--type', '-t', 'error_type', default=None, help='Error class/type name')
@click.option('--message', '-m', 'error_message', default=None, help='Raw error message')
@click.option('--trace', 'stack_trace', default='', help='Full stack trace')
@click.option('--cause', '-c', required=True, help='Root cause analysis')
@click.option('--fix', '-p', 'patch_or_fix', required=True, help='Patch or fix code/command')
@click.option('--explanation', '-e', default='', help='Explanation of why fix works')
@click.option('--tags', default='', help='Comma-separated tags (e.g. git,lock,concurrency)')
def record(error: Optional[str], error_type: Optional[str], error_message: Optional[str], stack_trace: str, cause: str, patch_or_fix: str, explanation: str, tags: str):
    """Record a new error pattern and solution."""
    if not error and not error_message and not error_type:
        raise click.UsageError("Must specify --error or --type/--message")

    final_error_message = error_message or error or ""
    final_error_type = error_type or _infer_error_type(error or error_message or "")
    final_stack_trace = stack_trace or (error if error and "\n" in error else "")

    tag_list = [t.strip() for t in tags.split(',') if t.strip()] if tags else []
    rec_input = RecordInput(
        error_type=final_error_type,
        error_message=final_error_message,
        stack_trace=final_stack_trace,
        cause=cause,
        patch_or_fix=patch_or_fix,
        explanation=explanation,
        tags=tag_list
    )
    err_rec, sol_rec = db.add_record(rec_input)
    click.echo(f"✅ Recorded Solution Successfully!")
    click.echo(f"  Record ID:   {err_rec.id}")
    click.echo(f"  Fingerprint: {err_rec.fingerprint}")
    click.echo(f"  Solution ID: {sol_rec.id}")

@cli.command()
@click.option('--limit', '-l', default=10, type=int, help='Limit top patterns')
def patterns(limit: int):
    """List top recurring error pattern tags."""
    pattern_list = db.list_patterns(limit=limit)
    if not pattern_list:
        click.echo("No error patterns found.")
        return

    click.echo("📊 Recurring Agent Error Patterns:\n")
    for p in pattern_list:
        samples = ", ".join(p.sample_error_types)
        click.echo(f" #{p.tag:<15} | Occurrences: {p.count:<3} | Rating: ⭐ {p.avg_verification_score}/5.0 | Types: {samples}")

@cli.command()
def seed():
    """Pre-populate database with 12 real-world AI agent error records."""
    seed_database()

if __name__ == '__main__':
    cli()
