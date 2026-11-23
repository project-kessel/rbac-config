# Security Guidelines for rbac-config

## 1. Permission Format and Allowed Verbs

All permissions follow the strict format `<application>:<resource>:<action>`. The action (verb) must be one of the schema-enforced values: `*`, `read`, `write`, `create`, `update`, `upload`, `delete`, `list`, `link`, `unlink`, `order`, `execute`, `view`, `grant`, `revoke`. Any other verb will fail CI validation against `schemas/permissions.schema`.

The `*` wildcard is valid for both resource and action segments (e.g., `inventory:*:*`, `advisor:*:read`). It grants broad access and must be used deliberately -- reserve wildcard permissions for administrator-level roles only.

## 2. Environment Separation: Stage Before Prod

Configurations are namespaced under `configs/stage/` and `configs/prod/`. Stage and prod may intentionally differ -- stage is used to test changes before promotion. Key rules:

- Always apply changes to stage first; prod follows after validation (stage deploys Tuesdays, prod Thursdays).
- Version numbers may differ between environments for the same role -- this is expected and intentional.
- The `migrated_apps.lst` files may list apps in different orders or contain different apps between environments. This reflects the migration state of each environment.
- Never copy a stage file to prod without verifying the version numbers and content are correct for the prod environment.

## 3. Role Definition Rules

Every role in `configs/*/roles/<app>.json` must satisfy these schema requirements (`schemas/roles.schema`):

- **Required fields**: `name`, `description`, `system`, `version`.
- **Mutually exclusive**: a role must have either `access` (with permissions) OR `external` (for external role integration) -- never both, never neither.
- `system` must always be `true` for all roles in this repository (these are platform-managed system roles).
- `version` must be incremented when any change is made to trigger re-seeding in the RBAC service. Setting version to 2 for new roles is the convention to trigger initial seeding.
- `display_name` is optional but controls what appears in the UI. If omitted, `name` is used. Once set, changes to `name` alone will not update the displayed name.

## 4. Platform Default and Admin Default Flags

These flags control automatic role assignment and have significant security impact:

- `platform_default: true`: the role is assigned to ALL users in a tenant via the platform default group. Prefer read-only or universally safe permissions. Write/execute verbs are allowed only when product requirements need every authenticated tenant user to perform those actions without an explicit role assignment; document each exception below.
- `admin_default: true`: the role is automatically assigned to org admins only. Use this for administrative capabilities like `rbac:*:*` or service-wide `*:*:*` access.
- Both flags can be true simultaneously (e.g., `Inventory Hosts Administrator` has both), meaning all users AND admins get the role. Prefer this only when the same grant must cover both populations.
- Omitting a flag is equivalent to `false`, but explicitly setting `false` is preferred for clarity and to show intent.

### Accepted `platform_default` write grants

The following system roles intentionally grant write verbs to every tenant user. Access remains scoped to the caller's own tenant. Do not remove these writes or move them to `admin_default`-only without a product decision that non-admin users no longer need the capability. When adding a new write verb to a `platform_default` role, update this table and use a `display_name` / `description` that reflects the privilege (do not rename immutable `name`).

| Role `name` | File | Write permission(s) | Product justification |
| --- | --- | --- | --- |
| `RHC Viewer` | `configs/*/roles/config-manager.json` | `config-manager:activation_keys:write` | Every user must read RHC configuration and update activation keys. UI label is `display_name: "RHC user"` (immutable `name` kept for DB stability). |
| `Inventory Hosts Administrator` | `configs/*/roles/inventory.json` | `inventory:hosts:write` | Every user must read and update Inventory host records (also `admin_default: true` so org admins retain the same grant). |
| `Remediations user` | `configs/*/roles/remediations.json` | `remediations:remediation:write` | Every user must create, update, and delete remediations as part of standard Insights workflows. |

## 5. Cross-Service Permission References

Roles frequently reference permissions from other applications. This is a deliberate pattern, not a bug:

- Compliance roles include `remediations:remediation:read/write` for remediation workflows.
- Config-manager and remediations roles include `playbook-dispatcher:run:read` with `resourceDefinitions` filters.
- Inventory workspace roles include `rbac:role_binding:view/grant/revoke` for binding management.
- Composite roles like RHEL viewer/operator/admin aggregate permissions across many application namespaces.

When adding cross-service permissions, ensure the referenced permission exists in the corresponding app's permission file under `configs/*/permissions/`. The CI pipeline validates permission dependencies.

## 6. Resource Definitions for Scoped Access

The `resourceDefinitions` array with `attributeFilter` restricts a permission to a specific scope. The filter supports `equal` and `in` operations only. This pattern is used to limit `playbook-dispatcher:run:read` to specific services:

```json
"resourceDefinitions": [{
  "attributeFilter": {
    "key": "service",
    "operation": "equal",
    "value": "remediations"
  }
}]
```

This is a security boundary -- it prevents a role from accessing playbook runs belonging to other services. Always scope playbook-dispatcher permissions to the relevant service value.

## 7. External Role Definitions

External roles (e.g., OCM roles) bridge RBAC with external authorization systems. They have `external.id` and `external.tenant` instead of `access`. Rules:

- External roles must NOT have an `access` array (enforced by schema `oneOf` constraint).
- The `external.tenant` identifies the external system (e.g., `ocm`). The external team uses `external.id` to map back to their roles.
- External roles can still have `platform_default: true` (e.g., `OCM Cluster Provisioner`), meaning all tenant users are assigned the external role.
- Version bumps are still required for external roles to trigger re-seeding.

## 8. Permission File Structure and the `requires` Field

Permission files (`configs/*/permissions/<app>.json`) define what verbs are available per resource type. The filename must match the application name used in permission strings.

- Every permission used in a role's `access` must be declared in the corresponding permission file. CI validates this.
- The `requires` field can enforce that when creating custom roles via the API, certain permissions must be paired together. For example, if `create` requires `["read"]`, any custom role with `app:resource:create` must also include `app:resource:read`.
- The `requires` array may only reference verbs that exist for the same app/resource type.
- Always include a wildcard entry `"*": [{"verb": "*"}]` in permission files to support administrator-level wildcard grants.

## 9. Kessel Schema (KSL) and SpiceDB

The `configs/*/schemas/src/*.ksl` files define the authorization model for Kessel/SpiceDB. Security-critical patterns:

- `migrated_apps.lst` controls which apps have their permissions managed through the V2 (Kessel) authorization model. Adding an app here changes how its permissions are evaluated.
- `add_v1_based_permission` creates a V2 permission backed by a V1 permission -- used during migration.
- `add_unified_permission` creates permissions where V1 and V2 share the same name -- the `[bool]` box makes the relation directly writable.
- `add_contingent_permission` creates permissions that require two conditions to be met simultaneously (intersection). This is used for host-centric access: e.g., vulnerability results require both `inventory_host_view` AND `vulnerability_vulnerability_results_view_assigned`.
- Schema changes are validated by SpiceDB (`authzed/action-spicedb-validate`) in CI. Invalid schemas will fail the PR.

## 10. CI Validation Pipeline

Every PR runs these security checks (`.github/workflows/pr.yml`):

1. **JSON schema validation** of all permission and role files against `schemas/*.schema`.
2. **Permission dependency validation** -- ensures `requires` references are valid and cross-service permissions exist.
3. **V1-only permissions generation** -- builds the intermediate `rbac_v1_permissions.json` (gitignored).
4. **Schema generation and validation** -- compiles KSL to SpiceDB schema and validates with SpiceDB.

On merge to master, the `master.yml` workflow auto-generates ConfigMaps in `_private/configmaps/` and creates a follow-up PR. Never manually edit files under `_private/configmaps/` -- they are auto-generated.

## 11. Privilege Escalation Prevention

- The User Access administrator role (`rbac:*:*`) explicitly documents that it "Cannot invite new users, assign the Org Admin role or manage any group that contains the User Access Administrator role." This constraint is enforced in the RBAC service, not in this config.
- When creating composite roles (like RHEL admin), carefully audit that the combined permissions do not create unintended privilege paths. A role with `inventory:*:*` plus `rbac:role_binding:grant` effectively allows granting access to any resource in any workspace.
- Avoid granting `*:*:*` (all apps, all resources, all actions) in any role -- this is not used in any existing role and would bypass all authorization boundaries.

## 12. Role Deletion

Removing a role JSON definition from this repo does NOT delete it from the database. Stale roles persist until the RBAC team manually removes them. This means:

- Revoking access by deleting config is insufficient -- contact the RBAC team.
- Renaming a role `name` field creates a new role while the old one persists.
- Use `display_name` for UI label changes instead of modifying `name`.

## 13. Version Discipline

The `version` field is the sole trigger for RBAC service to re-seed a role. Forgetting to increment it means your security-relevant changes will NOT take effect. Always increment version when changing:

- Permissions in the `access` array
- `platform_default` or `admin_default` flags
- `display_name` or `description`
- `external` role mappings
