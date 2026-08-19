import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from models import RecordInput
from db import ErrorDatabase
import cli as cli_module
from cli import cli

class TestAgentErrorKB(unittest.TestCase):
    """Uses an isolated temp DB per test — never touches the real ~/.agent-kb/kb.db."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = ErrorDatabase(db_path=Path(self.tmpdir) / "kb.db")
        self.runner = CliRunner()
        self._db_patch = patch.object(cli_module, "db", self.db)
        self._db_patch.start()

    def tearDown(self):
        self._db_patch.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_01_lookup_error_solution(self):
        results = self.db.search_solutions(query="fatal: Unable to create '.git/index.lock': File exists", limit=3)
        self.assertTrue(len(results) > 0)
        top_match = results[0]
        self.assertEqual(top_match.record.error_type, "GitLockError")

    def test_02_record_error_solution(self):
        rec_input = RecordInput(
            error_type="UnitTestError",
            error_message="AssertionError: Expected 200 OK got 500",
            stack_trace="Traceback: test_backend.py line 42",
            cause="Mock backend returned unhandled 500 internal server error",
            patch_or_fix="app.add_exception_handler(Exception, generic_handler)",
            explanation="Global exception handler catches unhandled exceptions cleanly",
            tags=["unittest", "testing"],
            agent_environment={"os": "linux", "python": "3.12"}
        )
        err_rec, sol_rec = self.db.add_record(rec_input)
        self.assertEqual(err_rec.error_type, "UnitTestError")
        self.assertEqual(sol_rec.cause, rec_input.cause)

        # Verification upvote
        updated_sol = self.db.verify_solution(sol_rec.id)
        self.assertIsNotNone(updated_sol)
        self.assertEqual(updated_sol.verified_count, 2)

    def test_03_list_patterns(self):
        patterns = self.db.list_patterns(limit=10)
        self.assertTrue(len(patterns) > 0)

    def test_04_cli_lookup(self):
        result = self.runner.invoke(cli, ['lookup', 'git lock'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("GitLockError", result.output)

    def test_05_cli_record_with_error(self):
        result = self.runner.invoke(cli, [
            'record',
            '--error', 'fatal: test lock error',
            '--cause', 'Stale lockfile',
            '--fix', 'rm lockfile',
            '--tags', 'test,lock'
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Recorded Solution Successfully!", result.output)

    def test_06_no_mcp_command(self):
        """Regression: the MCP server mode was dropped (broken against the installed mcp SDK) and must stay gone."""
        self.assertNotIn("mcp", cli.commands)

if __name__ == "__main__":
    unittest.main()
