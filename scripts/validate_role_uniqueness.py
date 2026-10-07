#!/usr/bin/env python3
"""Fail when two roles in the same environment share a name or a display_name.

The RBAC service keys roles on `name`, so a duplicate quietly produces an
ambiguous record, and a duplicate `display_name` makes two distinct roles
indistinguishable in the User Access UI. JSON Schema cannot express uniqueness
across separate files, so it is checked here instead.

Each environment is indexed on its own: `configs/stage/` and `configs/prod/`
seed separate deployments, and the stage-first convention guarantees the same
role name exists in both during a normal promotion.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

# Anchored to the script's own location so the check reads the same configs
# whatever directory it is invoked from: `make`, CI, and an ad-hoc run from a
# subdirectory all have to agree.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_ROOT = REPO_ROOT / "configs"
DEFAULT_ENVIRONMENTS = ("stage", "prod")


def repo_relative(path: Path) -> Path:
    """Repo-relative form of `path`, so messages do not leak the checkout path."""
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


class RoleRef(NamedTuple):
    """Where a role lives and the two values it must hold uniquely."""

    file: Path
    index: int
    name: str
    display_name: str


# Role references grouped by the value they must hold uniquely.
RoleIndex = dict[str, list[RoleRef]]


def load_roles(path: Path) -> list:
    """Return the `roles` array of one role file.

    Raises ValueError with the offending path when the file cannot be read or
    does not have the expected shape. Schema validation runs ahead of this
    check in CI, so reaching that state means something unexpected.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{repo_relative(path)}: cannot be read ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{repo_relative(path)}: is not valid JSON ({exc})") from exc

    if not isinstance(document, dict):
        raise ValueError(f"{repo_relative(path)}: top-level value is not a JSON object")

    roles = document.get("roles", [])
    if not isinstance(roles, list):
        raise ValueError(f"{repo_relative(path)}: `roles` is not an array")
    return roles


def collect_roles(roles_dir: Path) -> tuple[RoleIndex, RoleIndex, list[str]]:
    """Index every role under one environment by name and by display_name.

    `display_name` defaults to `name` when absent, empty, or whitespace-only,
    and is keyed case-insensitively so labels differing only in case or padding
    collide. `name` is keyed verbatim because it is the database primary key.
    """
    by_name: RoleIndex = defaultdict(list)
    by_display_name: RoleIndex = defaultdict(list)
    errors: list[str] = []

    for path in sorted(roles_dir.glob("*.json")):
        try:
            roles = load_roles(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        relative = repo_relative(path)
        for index, role in enumerate(roles, start=1):
            location = f"{relative}: role #{index}"
            if not isinstance(role, dict):
                errors.append(f"{location} is not a JSON object")
                continue

            name = role.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{location} is missing a `name`")
                continue

            display_name = role.get("display_name")
            if display_name is not None and not isinstance(display_name, str):
                errors.append(f'{location} ("{name}") has a non-string `display_name`')
                continue

            ref = RoleRef(relative, index, name, (display_name or "").strip() or name)
            by_name[name].append(ref)
            by_display_name[ref.display_name.casefold()].append(ref)

    return by_name, by_display_name, errors


def report_duplicate_names(by_name: RoleIndex) -> list[str]:
    lines = []
    for name, refs in sorted(by_name.items()):
        if len(refs) > 1:
            lines.append(f'  name "{name}" is used by {len(refs)} roles:')
            lines.extend(f"    - {ref.file}: role #{ref.index}" for ref in refs)
    return lines


def report_duplicate_display_names(by_display_name: RoleIndex) -> list[str]:
    lines = []
    for _, refs in sorted(by_display_name.items()):
        if len(refs) > 1:
            lines.append(
                f"  display_name is used by {len(refs)} roles "
                "(compared case-insensitively, ignoring surrounding whitespace):"
            )
            lines.extend(
                f'    - {ref.file}: role #{ref.index} "{ref.name}"'
                f' (display_name "{ref.display_name}")'
                for ref in refs
            )
    return lines


def check_environment(roles_dir: Path) -> list[str]:
    """Return every problem found in one environment, empty when it is clean."""
    by_name, by_display_name, errors = collect_roles(roles_dir)
    return (
        [f"  {error}" for error in errors]
        + report_duplicate_names(by_name)
        + report_duplicate_display_names(by_display_name)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that role names and display names are unique per environment."
    )
    parser.add_argument(
        "--environment",
        action="append",
        dest="environments",
        metavar="NAME",
        help="Environment to check; repeatable (default: stage and prod)",
    )
    args = parser.parse_args(argv)
    environments = args.environments or DEFAULT_ENVIRONMENTS

    # Every environment is reported before exiting so one CI log shows the
    # full picture rather than only the first failing environment.
    failures: list[str] = []
    for environment in environments:
        roles_dir = CONFIG_ROOT / environment / "roles"
        if roles_dir.is_dir():
            problems = check_environment(roles_dir)
        else:
            problems = [f"  {repo_relative(roles_dir)}: no such directory"]

        if problems:
            failures.append(f"{environment}:")
            failures.extend(problems)
        else:
            print(
                f"{environment}: role names and display names in "
                f"{repo_relative(roles_dir)} are unique"
            )

    if failures:
        print("Role uniqueness check failed.", file=sys.stderr)
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
