# Integration Guidelines for rbac-config

## Repository Architecture

This repository defines RBAC (Role-Based Access Control) permissions and roles for Red Hat Hybrid Cloud Console services. It feeds two downstream systems: the **RBAC service** (insights-rbac) for V1 permission enforcement, and **Kessel/SpiceDB** for V2 relationship-based authorization.

**Key directories:**
- `configs/(stage|prod)/permissions/` -- permission definitions per application
- `configs/(stage|prod)/roles/` -- role definitions per application (including external roles)
- `configs/(stage|prod)/schemas/` -- Kessel schema files (KSL source + generated SpiceDB ZED)
- `_private/configmaps/(stage|prod|fedramp-stage|fedramp-prod)/` -- auto-generated ConfigMaps (never edit manually)
- `schemas/` -- JSON Schema files for validating permissions and roles

## Deployment Pipeline and Promotion Schedule

- **Stage**: Changes promoted every Tuesday
- **Prod**: Changes promoted every Thursday
- Reviews happen the same day as promotions

### Merge-to-Deploy Flow

1. A contributor opens a PR against `master` with changes to `configs/`
2. The **PR workflow** (`.github/workflows/pr.yml`) validates JSON schemas and SpiceDB schemas
3. After merge to `master`, the **master workflow** (`.github/workflows/master.yml`) automatically:
   - Generates V1-only permissions data from KSL schemas
   - Converts configs into Kubernetes ConfigMap templates via `project-kessel/rbac-config-actions/convert-config`
   - Validates generated SpiceDB schemas with `authzed/action-spicedb-validate`
   - Creates an automated PR on the `configmaps-schema` branch with the title `[GitHub] - Automated ConfigMap & Schema Generation`
4. Once the ConfigMap PR is merged, a separate MR must be created in the **app-interface** GitLab repo to bump the `ref` in the `resourceTemplate` for the target namespace, which triggers actual deployment

### Critical Rule: Never Edit Generated Files

The files under `_private/configmaps/` are generated artifacts. The `convert-config` action produces four environment variants (stage, prod, fedramp-stage, fedramp-prod) from the two source directories (stage, prod). FedRAMP configmaps use empty templates with `qontract.recycle: "true"` annotations. All edits must be made in `configs/` source files.

## Permission Configuration

### File Naming and Structure

Each application gets one JSON file in `configs/<env>/permissions/` named `<application>.json`. The filename determines the application name in the `<application>:<resource>:<action>` permission triple.

### Permission Schema Rules

- Each top-level key is a **resource type** name
- Each resource contains an array of verb objects
- Allowed verbs: `*`, `read`, `write`, `create`, `update`, `upload`, `delete`, `list`, `link`, `unlink`, `order`, `execute`, `view`, `grant`, `revoke`
- Every permission file must have at least one resource with at least one verb
- Include a wildcard resource `"*"` with verb `"*"` to allow full-access roles to reference `<app>:*:*`

### Permission Dependencies

Use the `requires` field to enforce that one verb requires another for the same resource:
```json
{ "verb": "create", "requires": ["read"] }
```
This causes the RBAC API to reject custom role creation with `app:resource:create` unless `app:resource:read` is also included. The `requires` array may only reference verbs that exist for the same app/resource.

### Permission Descriptions

Add optional `description` fields to verbs for UI display purposes. Rarely used in practice, but when present this documents what a permission means to end users.

## Role Configuration

### Role Schema Rules

Every role requires: `name`, `description`, `system` (boolean), and `version` (integer). A role must have either `access` (with permissions) or `external` (for external tenant mapping), but not both -- enforced by the JSON Schema's `oneOf` constraint.

### Version Bumping

**Always increment the `version` number** when modifying a role. The RBAC service uses the version to detect changes and trigger re-seeding. New roles should start at version 2 (version 1 may not trigger seeding in some edge cases per convention).

### Role Flags

- `platform_default: true` -- role is automatically assigned to the platform default group (all users get these permissions)
- `admin_default: true` -- role is automatically assigned to org admins only
- Both flags default to false if omitted
- `display_name` -- the UI-visible name; if omitted, `name` is used. Use `display_name` when renaming a role to avoid breaking the database key

### Deleting Roles

Removing a role from config does **not** delete it from the database. Contact the RBAC team for actual deletion.

## External Role Integration (OCM Pattern)

External roles bridge RBAC with external tenant systems. They are defined in role files without `access` and instead use the `external` object:
```json
{
  "external": { "id": "ClusterEditor", "tenant": "ocm" }
}
```

- The `tenant` field identifies the external system (currently only `ocm` is used)
- The `id` field is the identifier the external tenant uses to map back to this RBAC role
- External roles can still use `platform_default` and `display_name`
- The OCM roles in `configs/<env>/roles/ocm.json` define seven roles covering cluster editing, provisioning, viewing, org admin, IDP editing, machine pool editing, and autoscaler editing

## Kessel Schema (KSL) Integration

### Schema Source Files

KSL (Kessel Schema Language) source files live in `configs/<env>/schemas/src/*.ksl`. They define relationship-based authorization schemas that compile into SpiceDB-compatible `.zed` files.

### App Migration Lists

- `migrated_apps.lst` -- apps fully migrated to Kessel V2 authorization (notifications, integrations, rbac, inventory, etc.)
- `hostsonly_apps.lst` -- apps migrated only for host-level permissions (currently empty in both stage and prod)

These lists are consumed by the `generate-v1-only-permissions` tool to determine which app permissions need V1 compatibility shims.

### Permission Mapping Patterns in KSL

Three extension macros from `rbac.ksl` control how permissions are exposed:

1. **`add_v1_based_permission`** -- Maps a V1 permission (`app:resource:verb`) to a V2 permission name. Used when the V2 name differs from V1 naming.
2. **`add_unified_permission`** -- Used when V1 and V2 share the same `app_resource_verb` name. Avoids template conflicts.
3. **`add_contingent_permission`** -- Creates a permission that requires two other permissions to both be granted (intersection). Used for host-scoped permissions that require both inventory access and the specific app permission.

### Stage vs. Prod Schema Parity

Stage may include additional KSL files not yet in prod (e.g., `subscriptions.ksl` exists in stage but not prod). The `migrated_apps.lst` may also differ between environments. Always check both when adding a new app's schema.

## GitHub Action Integrations

### PR Validation Pipeline (`.github/workflows/pr.yml`)

Runs on every PR to `master` with these sequential checks:
1. **JSON Schema validation** via `walbo/validate-json` -- validates all `configs/*/permissions/*.json` against `schemas/permissions.schema` and all `configs/*/roles/*.json` against `schemas/roles.schema` (roles use `strict: false`)
2. **Permission dependency validation** via `project-kessel/rbac-config-actions/validate-permission-dependencies` -- checks `requires` field integrity
3. **V1-only permissions generation** via `project-kessel/rbac-config-actions/generate-v1-only-permissions` -- for both stage and prod
4. **Schema generation and validation** via `project-kessel/rbac-config-actions/validate-schema`
5. **SpiceDB schema validation** via `authzed/action-spicedb-validate` -- validates the generated `.zed` files for both environments

### Master Merge Pipeline (`.github/workflows/master.yml`)

Runs on push to `master`:
1. Generates V1-only permissions for both environments
2. Converts configs to ConfigMaps and generates schemas via `project-kessel/rbac-config-actions/convert-config` (pushes to `configmaps-schema` branch)
3. Validates generated SpiceDB schemas
4. Creates a PR from `configmaps-schema` to `master` using `gh pr create` if changes exist

### External Actions Used

| Action | Purpose |
|--------|---------|
| `project-kessel/rbac-config-actions/validate-permission-dependencies@main` | Validates `requires` field references |
| `project-kessel/rbac-config-actions/generate-v1-only-permissions@main` | Generates V1 compatibility data from KSL |
| `project-kessel/rbac-config-actions/validate-schema@main` | Generates and validates KSL schemas |
| `project-kessel/rbac-config-actions/convert-config@main` | Converts JSON configs to K8s ConfigMaps |
| `authzed/action-spicedb-validate@v1` | Validates SpiceDB `.zed` schema files |
| `walbo/validate-json@v1.1.0` | Validates JSON against JSON Schema |

## Integrations and Notifications as Application Configs

The `integrations` and `notifications` applications are tightly coupled but separately configured:

- `integrations.json` (permissions) defines `endpoints` resource with `read`/`write` verbs
- `notifications.json` (permissions) defines `notifications` (read/write) and `events` (read-only) resources
- The `notifications.json` (roles) bundles both apps: the Notifications administrator gets `notifications:*:*` and `integrations:*:*`, while the viewer gets `notifications:notifications:read` and `integrations:endpoints:read`
- In KSL, both apps share the `notifications` namespace in `notifications.ksl`

## Local Development with Makefile

Run `make init` to install Go-based tools (`ksl` and `generate-v1-only-permissions`). Use `make ksl-test-schema-stage` or `make ksl-test-schema-prod` to build test schemas locally before pushing. The generated `rbac_v1_permissions.json` files are gitignored.

## Environment Consistency Rules

1. Permission and role files should generally be kept in sync between `stage` and `prod` unless intentionally staging a change
2. Stage serves as the testing ground -- deploy to stage first, then promote to prod
3. FedRAMP environments (`fedramp-stage`, `fedramp-prod`) use separate ConfigMap templates but derive from the same `stage`/`prod` source configs
4. When adding a new application: create both the permissions file and roles file in the same environment, update `migrated_apps.lst` if the app uses Kessel V2, and add a `.ksl` file if schema-level authorization is needed
