"""Verify init installs only explicitly pinned Go tools without resolving HEAD."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class MakeInitTest(unittest.TestCase):
    def test_init_installs_pinned_commits_without_git(self):
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory)
            go = bin_dir / "go"
            go.write_text(
                '#!/bin/sh\nif [ "$1" = env ]; then echo /tmp; '
                'else printf "%s\\n" "$*"; fi\n', encoding="utf-8"
            )
            go.chmod(0o755)
            git = bin_dir / "git"
            git.write_text(
                '#!/bin/sh\necho "unexpected git call" >&2\nexit 1\n', encoding="utf-8"
            )
            git.chmod(0o755)
            result = subprocess.run(
                ["make", "--silent", "init"], cwd=ROOT,
                env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
                text=True, capture_output=True, check=True,
            )

        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(
            lines[0], r"^install github\.com/project-kessel/ksl-schema-language/cmd/ksl@[0-9a-f]{40}$"
        )
        self.assertRegex(
            lines[1], r"^install github\.com/project-kessel/rbac-config-actions/"
            r"generate-v1-only-permissions/cmd/generate-v1-only-permissions@[0-9a-f]{40}$"
        )
        self.assertNotIn("unexpected git call", result.stderr)


if __name__ == "__main__":
    unittest.main()
