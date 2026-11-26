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

    def test_documented_pin_update_rebuilds_both_permissions_files(self):
        docs = (ROOT / "docs/testing-guidelines.md").read_text(encoding="utf-8")
        section = docs.split("### Validating Tool Pin Updates\n", 1)[1]
        commands = section.split("```sh\n", 1)[1].split("```", 1)[0]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Makefile").write_text((ROOT / "Makefile").read_text(), encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            scripts = {
                "go": f'#!/bin/sh\nif [ "$1" = env ]; then printf "%s\\n" "{root}"; fi\n',
                "generate-v1-only-permissions": (
                    '#!/bin/sh\nprintf "new\\n" > "$2/src/rbac_v1_permissions.json"\n'
                ),
                "ksl": (
                    '#!/bin/sh\nout="$2"\n'
                    'for arg in "$@"; do\n'
                    '  case "$arg" in */rbac_v1_permissions.json) cat "$arg" > "$out";; esac\n'
                    'done\n'
                ),
            }
            for name, content in scripts.items():
                script = bin_dir / name
                script.write_text(content, encoding="utf-8")
                script.chmod(0o755)
            for env_name in ("stage", "prod"):
                config = root / "configs" / env_name
                (config / "permissions").mkdir(parents=True)
                (config / "schemas/src").mkdir(parents=True)
                (config / "permissions/app.json").write_text("{}", encoding="utf-8")
                (config / "schemas/apps.lst").write_text("", encoding="utf-8")
                (config / "schemas/src/app.ksl").write_text("", encoding="utf-8")
                (config / "schemas/src/rbac_v1_permissions.json").write_text("stale\n", encoding="utf-8")
            env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
            subprocess.run(
                ["make", "ksl-test-schema-stage", "ksl-test-schema-prod"],
                cwd=root, env=env, capture_output=True, text=True, check=True,
            )
            for env_name in ("stage", "prod"):
                output = root / "_private/test-schema" / f"{env_name}-schema.zed"
                self.assertEqual(output.read_text(encoding="utf-8"), "stale\n")

            subprocess.run(
                ["sh", "-e", "-c", commands], cwd=root, env=env,
                capture_output=True, text=True, check=True,
            )
            for env_name in ("stage", "prod"):
                output = root / "_private/test-schema" / f"{env_name}-schema.zed"
                self.assertEqual(output.read_text(encoding="utf-8"), "new\n")


if __name__ == "__main__":
    unittest.main()
