# RBAC Config

Declarative JSON configurations for roles and permissions in the [Red Hat Hybrid Cloud Console](https://console.redhat.com) RBAC service. These configs are seeded into every tenant/account. The repository also contains Kessel Schema Language (KSL) files that compile to SpiceDB authorization schemas for the V2 authorization model.

There is no application code here -- only JSON configs, KSL schemas, and CI automation.

| Resource | Link |
|----------|------|
| RBAC Service | https://github.com/project-kessel/insights-rbac |
| RBAC Platform Docs | https://consoledot.pages.redhat.com/docs/dev/services/rbac.html |

## Deployment Schedule

| Environment | Day |
|-------------|-----|
| Stage | Every Tuesday |
| Production | Every Thursday |

Reviews and deployments happen on the same day. All changes go to stage first.

## Documentation

Detailed guidance lives in dedicated files -- the README covers only getting started and high-level reference.

| Document | Description |
|----------|-------------|
| [AGENTS.md](AGENTS.md) | Repository layout, conventions, common pitfalls, and PR workflow -- the primary reference for both humans and AI agents |
| [Security Guidelines](docs/security-guidelines.md) | Permission format, role flags, privilege escalation risks, CI security checks |
| [API Contracts Guidelines](docs/api-contracts-guidelines.md) | JSON schema contracts, field specifications, naming conventions |
| [Database Guidelines](docs/database-guidelines.md) | How configs seed into tenant databases, version-triggered updates, Kessel/SpiceDB model |
| [Testing Guidelines](docs/testing-guidelines.md) | CI pipeline steps, local schema build commands, pre-PR validation checklist |
| [Integration Guidelines](docs/integration-guidelines.md) | Deployment pipeline, ConfigMap generation, GitHub Actions, merge-to-deploy flow |

## Tech Stack

- **Configuration format:** JSON (permissions and roles), KSL (Kessel Schema Language for SpiceDB)
- **Validation:** JSON Schema (`schemas/permissions.schema`, `schemas/roles.schema`)
- **Build tooling:** GNU Make, Go 1.22+ (for `ksl` compiler and `generate-v1-only-permissions`)
- **CI/CD:** GitHub Actions (`.github/workflows/pr.yml`, `.github/workflows/master.yml`)
- **Authorization backend:** SpiceDB (via compiled `.zed` schemas)

## Repository Layout

```
configs/
  stage/                    # Stage environment (deploys Tuesdays)
  prod/                     # Production environment (deploys Thursdays)
    permissions/<app>.json  # One file per app; filename = app namespace
    roles/<app>.json        # One file per app; contains a "roles" array
    schemas/
      src/*.ksl             # KSL source files for Kessel/SpiceDB
      migrated_apps.lst     # Apps using V2 authorization
      schema.zed            # GENERATED -- never edit manually
schemas/
  permissions.schema        # JSON Schema for permission files
  roles.schema              # JSON Schema for role files
_private/                   # Generated artifacts -- never edit
```

## Local Development

### Prerequisites

- Go 1.22+ ([download](https://golang.org/dl/))

### Setup and build

```sh
make init                    # Install ksl and generate-v1-only-permissions tools
make check-go-tools          # Verify the tools are installed
make ksl-test-schema-stage   # Build and validate stage schema
make ksl-test-schema-prod    # Build and validate prod schema
```

Test schemas are written to `_private/test-schema/stage-schema.zed` and `_private/test-schema/prod-schema.zed`.

**Important:** Do not run `make ksl-schema-stage` or `make ksl-schema-prod` locally -- those targets overwrite committed files. Always use the `ksl-test-schema-*` targets.

After you clone the RBAC service repo, you can replace the contents in `insights-rbac/rbac/management/role/(definitions|permissions)` with the JSON files from the `configs` folders here.

## Contributing

Configs are namespaced per environment in `configs/(stage|prod)/`. Make changes in the appropriate environment based on when you need them promoted.

### Key rules

- **Bump `version`** on every role change -- this is the only trigger for re-seeding. New roles start at version 2+.
- **Never rename `name`** -- it is the database primary key. Use `display_name` to change what users see.
- **Add permissions explicitly** -- add them in `configs/<env>/permissions/` even if referenced in roles. Unadded permissions are candidates for future removal.
- **Stage first** -- all changes go to `configs/stage/` before `configs/prod/`.

See [AGENTS.md](AGENTS.md) for the full conventions and common pitfalls list.

### Permission format

Permissions follow the format `<application>:<resource>:<action>`. The permission filename (minus `.json`) is the application namespace. There are no restrictions on resource or action values -- app teams define their own semantics.

### Add new permissions

In the permissions directory, each JSON file defines supported permissions for an app. For example, `approval.json` containing `"requests": [{"verb": "create"}]` creates the permission `approval:requests:create`.

Adding a description:
```json
{
  "requests": [
    {
      "verb": "create",
      "description": "Describing the permission"
    }
  ]
}
```

Defining permission dependencies with `requires`:
```json
{
  "requests": [
    {
      "verb": "create",
      "requires": ["read"]
    },
    {
      "verb": "read"
    }
  ]
}
```

This ensures that when a custom role is created with `app:requests:create`, the `app:requests:read` permission must also be included, or the API returns a 400. The `requires` array is restricted to verbs that exist for the same app/resource type.

### Canned roles

**Add:** Follow existing examples. Include name, description, `system` flag, and access with permissions. Set `version` to 2 or higher. Set `platform_default: true` if the role should be in the platform default group.

**Update:** Increment the `version` number. To rename, add or update `display_name` (never change `name`).

**Delete:** Removing a role file does not delete it from the database. Contact the RBAC team for deletion.

### Admin default roles

The `admin_default` flag assigns roles to org admins automatically (similar to `platform_default`). Defaults to `false`.

```json
{
  "roles": [
    {
      "name": "Service administrator",
      "description": "Perform any available operation against any Service resource.",
      "system": true,
      "platform_default": false,
      "admin_default": true,
      "version": 1,
      "access": [{ "permission": "service:*:*" }]
    }
  ]
}
```

### External roles

External roles are defined without access/permissions and include an `external` object with `id` and `tenant` fields:

```json
{
  "roles": [
    {
      "name": "OCM Cluster Owner",
      "description": "This role provides cluster owner permission.",
      "system": true,
      "version": 2,
      "external": { "id": "ClusterOwner", "tenant": "ocm" }
    }
  ]
}
```

After seeding, the role can be assigned to users through groups. The external tenant team uses the external `id` to map it to their own roles.

## Deployment

Once your PR is merged:

1. An automated PR is created with your changes applied as a ConfigMap in `_private/configmaps/(stage|prod)/`.
2. That automated PR must be merged.
3. An MR must be created in [`app-interface`](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/rbac/deploy.yml) to bump the `ref` in the corresponding `resourceTemplate`(s) and namespace(s), which triggers deployment.

See [Integration Guidelines](docs/integration-guidelines.md) for the full pipeline details.
