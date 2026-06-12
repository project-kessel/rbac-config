# Contributing to rbac-config

Thank you for your interest in contributing to the Red Hat Hybrid Cloud Console RBAC configuration repository.

## Code of Conduct

This project follows the [Red Hat Code of Conduct](https://www.redhat.com/en/about/code-of-conduct). By participating, you are expected to uphold this standard.

## Getting Started

### Prerequisites

- **Go 1.22+** ([download](https://golang.org/dl/))
- **Git** for version control
- **GitHub account** with access to project-kessel

### Local Setup

```sh
git clone https://github.com/project-kessel/rbac-config.git
cd rbac-config
make init                    # Install ksl and generate-v1-only-permissions tools
make check-go-tools          # Verify installation
```

### Testing Your Changes

Before submitting a PR, validate your changes locally:

```sh
make ksl-test-schema-stage   # Build and validate stage schema
make ksl-test-schema-prod    # Build and validate prod schema
```

**Important:** Never use `make ksl-schema-*` targets locally -- they overwrite committed files. Always use the `ksl-test-schema-*` test targets.

## Contribution Workflow

### 1. Create Your Changes

- **Stage first:** All changes go to `configs/stage/` before `configs/prod/`
- **Permissions:** Add/modify files in `configs/<env>/permissions/<app>.json`
- **Roles:** Add/modify files in `configs/<env>/roles/<app>.json`
- **Schemas:** Edit `.ksl` source files in `configs/<env>/schemas/src/` (never edit `schema.zed` directly)

### 2. Follow Key Conventions

- **Bump version:** Always increment the `version` field when modifying roles
- **Never rename `name`:** Use `display_name` to change UI labels
- **Add permissions explicitly:** Include all permissions in `configs/<env>/permissions/` even if only referenced in roles
- **JSON formatting:** 4-space indentation for permissions, 2-space for roles

See [AGENTS.md](AGENTS.md) for complete conventions and common pitfalls.

### 3. Pre-Submission Checklist

Before opening a PR, verify:

- [ ] Role `version` field incremented for all modified roles
- [ ] Permission dependencies (`requires`) reference valid verbs
- [ ] `make ksl-test-schema-stage` succeeds (if stage changed)
- [ ] `make ksl-test-schema-prod` succeeds (if prod changed)
- [ ] JSON files follow formatting conventions
- [ ] Changes tested in stage before promoting to prod

### 4. Open a Pull Request

- **Target branch:** `master`
- **PR title:** Brief description of the change (e.g., "Add advisor recommendations read permission")
- **PR description:** Include:
  - What changed and why
  - Which environment(s) are affected (stage/prod)
  - Any related issues or tickets

### 5. CI Validation

Your PR will automatically run validation checks:

1. JSON Schema validation (permissions and roles)
2. Permission dependency validation
3. KSL-to-SpiceDB schema generation
4. SpiceDB schema validation

All checks must pass before merge. See [Testing Guidelines](docs/testing-guidelines.md) for details.

## Review Process

- Reviews and deployments happen on the same day
- **Stage:** Reviews on Tuesdays
- **Prod:** Reviews on Thursdays
- Expect feedback within 1-2 business days
- Address review comments and push updates to your branch

## Post-Merge Deployment

After your PR is merged:

1. An automated PR generates ConfigMaps on the `configmaps-schema` branch
2. The automated PR must be merged
3. A separate MR in `app-interface` (GitLab) is required to trigger actual deployment

See [Integration Guidelines](docs/integration-guidelines.md) for the complete deployment pipeline.

## Documentation

Detailed guidance is available in dedicated files:

| Document | Description |
|----------|-------------|
| [AGENTS.md](AGENTS.md) | Repository layout, conventions, common pitfalls, PR workflow |
| [Security Guidelines](docs/security-guidelines.md) | Permission format, role flags, privilege escalation risks |
| [API Contracts Guidelines](docs/api-contracts-guidelines.md) | JSON schema contracts, field specifications |
| [Database Guidelines](docs/database-guidelines.md) | How configs seed into databases, version updates |
| [Testing Guidelines](docs/testing-guidelines.md) | CI pipeline, local validation, pre-PR checklist |
| [Integration Guidelines](docs/integration-guidelines.md) | Deployment pipeline, ConfigMap generation |

## Questions?

- **Technical questions:** Open a GitHub issue
- **RBAC service questions:** Consult the [RBAC Platform Docs](https://consoledot.pages.redhat.com/docs/dev/services/rbac.html)
- **Service repository:** [insights-rbac](https://github.com/project-kessel/insights-rbac)

Thank you for contributing!
