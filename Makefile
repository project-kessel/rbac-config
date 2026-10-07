# Check if go is installed
ifeq ($(shell command -v go 2> /dev/null),)
$(error "go is not installed. Please install Go from https://golang.org/dl/")
endif

GOBIN := $(shell go env GOPATH)/bin

SCHEMA_REPO ?= project-kessel/starlark-unified-schema
KSIL_SCHEMA_VERSION=v20260910.1

.PHONY: init check check-go-tools test validate-roles invariants ksl-schema-stage ksl-test-schema-stage ksl-schema-prod ksl-test-schema-prod update-schemas

init:
	@HASH=$$(git ls-remote https://github.com/project-kessel/ksl-schema-language.git HEAD | cut -f1) && \
	go install github.com/project-kessel/ksl-schema-language/cmd/ksl@$$HASH

	@HASH=$$(git ls-remote https://github.com/project-kessel/rbac-config-actions.git HEAD | cut -f1) && \
	go install github.com/project-kessel/rbac-config-actions/generate-v1-only-permissions/cmd/generate-v1-only-permissions@$$HASH

# Everything a contributor can verify locally before opening a PR: the
# validation scripts' own tests, role uniqueness, and a KSL compile of both
# environments into _private/test-schema. The remaining PR checks (JSON Schema
# validation, permission dependencies, SpiceDB schema validation) run only as
# GitHub Actions.
check: test validate-roles invariants ksl-test-schema-stage ksl-test-schema-prod
	@echo "All local checks passed."

check-go-tools:
	@echo "Checking required Go tools..."
	@if [ -f "$(GOBIN)/generate-v1-only-permissions" ]; then \
		echo "✓ generate-v1-only-permissions: installed"; \
	else \
		echo "✗ generate-v1-only-permissions: NOT installed (run 'make init')"; \
	fi
	@if [ -f "$(GOBIN)/ksl" ]; then \
		echo "✓ ksl: installed"; \
	else \
		echo "✗ ksl: NOT installed (run 'make init')"; \
	fi

# Tests for the scripts under scripts/. Standard library unittest only, so no
# Python dependencies to install.
test:
	python3 -m unittest discover -s tests

# Role name and display_name uniqueness, checked per environment. Mirrors the
# "Validate Role Name Uniqueness" step in .github/workflows/pr.yml.
validate-roles:
	python3 scripts/validate_role_uniqueness.py

# Guards against AI-generated artifacts: AI co-author trailers, emojis, and
# " -- " prose separators. Mirrors .github/workflows/invariants.yml.
invariants:
	bash scripts/check-invariants.sh master

# Stage environment targets
configs/stage/schemas/src/rbac_v1_permissions.json: configs/stage/permissions/*.json configs/stage/schemas/*.lst
	$(GOBIN)/generate-v1-only-permissions -ksl configs/stage/schemas -rbac-permissions-json configs/stage/permissions

configs/stage/schemas/schema.zed: configs/stage/schemas/src/*.ksl configs/stage/schemas/src/rbac_v1_permissions.json
	$(GOBIN)/ksl -o configs/stage/schemas/schema.zed configs/stage/schemas/src/*.ksl configs/stage/schemas/src/*.json

ksl-schema-stage: configs/stage/schemas/schema.zed

ksl-test-schema-stage: configs/stage/schemas/src/*.ksl configs/stage/schemas/src/rbac_v1_permissions.json
	@mkdir -p _private/test-schema
	$(GOBIN)/ksl -o _private/test-schema/stage-schema.zed configs/stage/schemas/src/*.ksl configs/stage/schemas/src/*.json

# Prod environment targets
configs/prod/schemas/src/rbac_v1_permissions.json: configs/prod/permissions/*.json configs/prod/schemas/*.lst
	$(GOBIN)/generate-v1-only-permissions -ksl configs/prod/schemas -rbac-permissions-json configs/prod/permissions

configs/prod/schemas/schema.zed: configs/prod/schemas/src/*.ksl configs/prod/schemas/src/rbac_v1_permissions.json
	$(GOBIN)/ksl -o configs/prod/schemas/schema.zed configs/prod/schemas/src/*.ksl configs/prod/schemas/src/*.json

ksl-schema-prod: configs/prod/schemas/schema.zed

ksl-test-schema-prod: configs/prod/schemas/src/*.ksl configs/prod/schemas/src/rbac_v1_permissions.json
	@mkdir -p _private/test-schema
	$(GOBIN)/ksl -o _private/test-schema/prod-schema.zed configs/prod/schemas/src/*.ksl configs/prod/schemas/src/*.json

# Download starlark KSIL release and overlay JSON into stage only (additive;
# does not delete). Tarball is features.json only, so hand-authored .ksl files
# are not overwritten. Does not compile KSL or regenerate schema.zed.
# Prod is a later copy of named JSON (e.g. features.json) when an SP is ready.
update-schemas:
	@test -n "$(KSIL_SCHEMA_VERSION)" || { echo "KSIL_SCHEMA_VERSION is required"; exit 1; }
	gh release download "$(KSIL_SCHEMA_VERSION)" \
		--repo "$(SCHEMA_REPO)" \
		--pattern 'ksl.tar.gz' \
		--clobber
	tar xzf ksl.tar.gz -C configs/stage/schemas/src
	rm -f ksl.tar.gz
