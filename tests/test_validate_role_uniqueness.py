#!/usr/bin/env python3
"""Tests for scripts/validate_role_uniqueness.py.

Standard library only: `python3 -m unittest discover -s tests` is the whole
runner, so the check that gates every PR is itself covered without adding a
test dependency to a repository that otherwise holds only configs.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_role_uniqueness.py"


def _load_script():
    """Import the script by path, since `scripts/` is not an importable package."""
    spec = importlib.util.spec_from_file_location("validate_role_uniqueness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_script()


def run_validator(*argv) -> tuple[int, str]:
    """Return the exit code and the combined stdout/stderr of one run."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = validator.main(list(argv))
    return code, stdout.getvalue() + stderr.getvalue()


class RoleUniquenessTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # Point the module at the fixture tree instead of the real configs.
        self._real_config_root = validator.CONFIG_ROOT
        self._real_repo_root = validator.REPO_ROOT
        validator.CONFIG_ROOT = self.root / "configs"
        validator.REPO_ROOT = self.root
        self.addCleanup(self._restore_roots)

    def _restore_roots(self):
        validator.CONFIG_ROOT = self._real_config_root
        validator.REPO_ROOT = self._real_repo_root

    def write_file(self, environment: str, filename: str, content: str) -> Path:
        roles_dir = self.root / "configs" / environment / "roles"
        roles_dir.mkdir(parents=True, exist_ok=True)
        path = roles_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def write_roles(self, environment: str, filename: str, roles) -> Path:
        return self.write_file(environment, filename, json.dumps({"roles": roles}))

    def test_unique_roles_pass(self):
        self.write_roles("stage", "a.json", [{"name": "a-admin", "display_name": "A admin"}])
        self.write_roles("stage", "b.json", [{"name": "b-admin", "display_name": "B admin"}])

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 0)
        self.assertIn("are unique", output)

    def test_duplicate_name_across_files_is_reported(self):
        self.write_roles("stage", "a.json", [{"name": "shared", "display_name": "First"}])
        self.write_roles("stage", "b.json", [{"name": "shared", "display_name": "Second"}])

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn('name "shared" is used by 2 roles', output)
        # Every participant is listed, not just the second occurrence.
        self.assertIn("configs/stage/roles/a.json: role #1", output)
        self.assertIn("configs/stage/roles/b.json: role #1", output)

    def test_duplicate_name_within_one_file_is_reported(self):
        self.write_roles(
            "stage",
            "a.json",
            [{"name": "shared", "display_name": "X"}, {"name": "shared", "display_name": "Y"}],
        )

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("role #1", output)
        self.assertIn("role #2", output)

    def test_display_name_compared_case_insensitively_and_stripped(self):
        self.write_roles("stage", "a.json", [{"name": "a-admin", "display_name": "Cost admin"}])
        self.write_roles("stage", "b.json", [{"name": "b-admin", "display_name": "  cost ADMIN "}])

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("display_name is used by 2 roles", output)
        # The reported value is the stripped original, not the casefolded key.
        self.assertIn('display_name "cost ADMIN"', output)

    def test_missing_display_name_falls_back_to_name(self):
        # Mirrors the real configs: a human-readable `name` and no `display_name`
        # still occupies that label in the UI, so an explicit match collides.
        self.write_roles("stage", "a.json", [{"name": "Inventory administrator"}])
        self.write_roles(
            "stage", "b.json", [{"name": "inv-admin", "display_name": "inventory administrator"}]
        )

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("display_name is used by 2 roles", output)

    def test_blank_display_name_falls_back_to_name(self):
        self.write_roles("stage", "a.json", [{"name": "same-label", "display_name": "   "}])
        self.write_roles("stage", "b.json", [{"name": "other", "display_name": "same-label"}])

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("display_name is used by 2 roles", output)

    def test_name_and_display_name_of_the_same_role_do_not_collide(self):
        self.write_roles("stage", "a.json", [{"name": "label", "display_name": "label"}])

        code, _ = run_validator("--environment", "stage")

        self.assertEqual(code, 0)

    def test_name_and_display_name_are_independent_namespaces(self):
        # Role A's `name` matching Role B's `display_name` is not a collision --
        # the two namespaces are indexed separately.
        self.write_roles("stage", "a.json", [{"name": "shared-label", "display_name": "A label"}])
        self.write_roles("stage", "b.json", [{"name": "b-admin", "display_name": "shared-label"}])

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 0, output)

    def test_same_name_in_both_environments_is_not_a_duplicate(self):
        role = [{"name": "shared", "display_name": "Shared"}]
        self.write_roles("stage", "a.json", role)
        self.write_roles("prod", "a.json", role)

        code, output = run_validator()

        self.assertEqual(code, 0)
        self.assertIn("stage:", output)
        self.assertIn("prod:", output)

    def test_both_environments_reported_before_exiting(self):
        dupes = [{"name": "shared"}, {"name": "shared"}]
        self.write_roles("stage", "a.json", dupes)
        self.write_roles("prod", "a.json", dupes)

        code, output = run_validator()

        self.assertEqual(code, 1)
        self.assertIn("configs/stage/roles/a.json", output)
        self.assertIn("configs/prod/roles/a.json", output)

    def test_file_without_roles_is_skipped(self):
        # An empty `roles` array is legitimate. A file with no `roles` key at
        # all is already rejected by schemas/roles.schema, so this check only
        # has to avoid crashing on it.
        self.write_file("stage", "empty.json", '{"roles": []}')
        self.write_file("stage", "no-roles-key.json", "{}")

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 0, output)
        self.assertIn("are unique", output)

    def test_unreadable_file_names_the_file(self):
        # A directory shaped like a role file is the portable way to make the
        # read fail (chmod is a no-op for a root CI runner).
        roles_dir = self.root / "configs" / "stage" / "roles"
        roles_dir.mkdir(parents=True, exist_ok=True)
        (roles_dir / "a-directory.json").mkdir()

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("configs/stage/roles/a-directory.json: cannot be read", output)

    def test_malformed_json_names_the_file(self):
        self.write_file("stage", "broken.json", "{not json")

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("configs/stage/roles/broken.json: is not valid JSON", output)

    def test_non_object_top_level_is_reported(self):
        self.write_file("stage", "list.json", "[]")

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("top-level value is not a JSON object", output)

    def test_roles_not_an_array_is_reported(self):
        self.write_file("stage", "object.json", '{"roles": {}}')

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("`roles` is not an array", output)

    def test_role_without_name_is_reported(self):
        self.write_roles("stage", "a.json", [{"display_name": "No name"}])

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("role #1 is missing a `name`", output)

    def test_non_string_display_name_is_reported(self):
        self.write_roles("stage", "a.json", [{"name": "a-admin", "display_name": 7}])

        code, output = run_validator("--environment", "stage")

        self.assertEqual(code, 1)
        self.assertIn("has a non-string `display_name`", output)

    def test_missing_environment_directory_fails(self):
        code, output = run_validator("--environment", "nope")

        self.assertEqual(code, 1)
        self.assertIn("configs/nope/roles: no such directory", output)


class RepoAnchoringTest(unittest.TestCase):
    """The check must read the committed configs from any working directory."""

    def test_runs_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            previous = Path.cwd()
            os.chdir(elsewhere)
            try:
                code, output = run_validator()
            finally:
                os.chdir(previous)

        self.assertEqual(code, 0, output)
        # Paths stay repo-relative rather than leaking the checkout location.
        self.assertIn("configs/stage/roles", output)
        self.assertNotIn(str(REPO_ROOT), output)


if __name__ == "__main__":
    unittest.main()
