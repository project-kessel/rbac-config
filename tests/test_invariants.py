#!/usr/bin/env python3
"""Tests for the scripts under scripts/invariants/.

Each test builds a throwaway git repository whose `origin/master` ref points at
an initial commit, adds commits on top, and runs the real shell script.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVARIANTS = REPO_ROOT / "scripts" / "invariants"
CHECK_ALL = REPO_ROOT / "scripts" / "check-invariants.sh"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


class InvariantTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-q", "-b", "master")
        (self.repo / "README.md").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.git("update-ref", "refs/remotes/origin/master", "HEAD")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, env=GIT_ENV, check=True)

    def commit(self, message, path="file.txt", content="change\n"):
        target = self.repo / path
        target.write_text(target.read_text() + content if target.exists() else content)
        self.git("add", ".")
        self.git("commit", "-q", "-m", message)

    def run_script(self, script) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(script), str(self.repo), "master"],
            env=GIT_ENV,
            capture_output=True,
            text=True,
        )


class NoAiCoauthorTest(InvariantTestCase):
    script = INVARIANTS / "no-ai-coauthor.sh"

    def assert_flagged(self, trailer):
        self.commit(f"feat: change\n\n{trailer}")
        result = self.run_script(self.script)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def assert_allowed(self, trailer):
        self.commit(f"feat: change\n\n{trailer}")
        result = self.run_script(self.script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_claude_coauthor_is_flagged(self):
        self.assert_flagged("Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")

    def test_copilot_coauthor_is_flagged_by_email(self):
        self.assert_flagged(
            "Co-authored-by: GitHub Copilot <175728472+Copilot@users.noreply.github.com>"
        )

    def test_cursor_agent_coauthor_is_flagged(self):
        self.assert_flagged("Co-authored-by: Cursor Agent <cursoragent@cursor.com>")

    def test_ai_branding_is_flagged(self):
        self.assert_flagged("Generated with Claude Code")

    def test_human_named_devin_is_allowed(self):
        self.assert_allowed("Co-authored-by: Devin Lee <dlee@redhat.com>")

    def test_human_with_tool_word_in_surname_is_allowed(self):
        self.assert_allowed("Co-authored-by: Ana Cursore <acursore@redhat.com>")

    def test_no_commits_passes(self):
        result = self.run_script(self.script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class MissingBaseRefTest(InvariantTestCase):
    def setUp(self):
        super().setUp()
        self.git("update-ref", "-d", "refs/remotes/origin/master")

    def test_each_invariant_fails_without_base_ref(self):
        for script in sorted(INVARIANTS.glob("*.sh")):
            with self.subTest(script=script.name):
                self.assertNotEqual(self.run_script(script).returncode, 0)

    def test_check_all_reports_missing_base_ref(self):
        result = subprocess.run(
            ["bash", str(CHECK_ALL), "no-such-branch"],
            env=GIT_ENV,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("origin/no-such-branch not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
