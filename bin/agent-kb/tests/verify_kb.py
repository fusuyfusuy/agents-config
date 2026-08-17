import os
import sys
import subprocess
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from db import ErrorDatabase

def main():
    print("=== 1. Checking Database Path & Auto-Creation ===")
    db = ErrorDatabase()
    print(f"Database path: {db.db_path}")
    assert db.db_path.exists(), "DB file does not exist!"
    print("DB file exists and loaded successfully.")

    print("\n=== 2. Testing CLI: agent-kb lookup 'git lock' ===")
    cli_path = str(Path.home() / ".local/bin/agent-kb")
    res = subprocess.run([cli_path, "lookup", "git lock"], capture_output=True, text=True)
    print("Returncode:", res.returncode)
    print("Stdout snippet:\n", res.stdout[:300])
    assert res.returncode == 0, f"Lookup failed: {res.stderr}"
    assert "GitLockError" in res.stdout or "git" in res.stdout.lower(), "Lookup did not return expected Git result!"

    print("\n=== 3. Testing CLI: agent-kb record ... ===")
    rec_cmd = [
        cli_path, "record",
        "--error", "test_verification_error: database is locked",
        "--cause", "Concurrent database writes during automated verification test",
        "--fix", "PRAGMA journal_mode=WAL;",
        "--tags", "verification,test"
    ]
    res_rec = subprocess.run(rec_cmd, capture_output=True, text=True)
    print("Returncode:", res_rec.returncode)
    print("Stdout:\n", res_rec.stdout)
    assert res_rec.returncode == 0, f"Record failed: {res_rec.stderr}"
    assert "Recorded Solution Successfully!" in res_rec.stdout, "Record command failed output assertion!"

    print("\n✅ ALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
