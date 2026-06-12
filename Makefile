# Check if go is installed
ifeq ($(shell command -v go 2> /dev/null),)
$(error "go is not installed. Please install Go from https://golang.org/dl/")
endif

GOBIN := $(shell go env GOPATH)/bin

.PHONY: init check-go-tools ksl-schema-stage ksl-test-schema-stage ksl-schema-prod ksl-test-schema-prod

init:
	@HASH=$$(git ls-remote https://github.com/project-kessel/ksl-schema-language.git HEAD | cut -f1) && \
	go install github.com/project-kessel/ksl-schema-language/cmd/ksl@$$HASH

	@HASH=$$(git ls-remote https://github.com/project-kessel/rbac-config-actions.git HEAD | cut -f1) && \
	go install github.com/project-kessel/rbac-config-actions/generate-v1-only-permissions/cmd/generate-v1-only-permissions@$$HASH

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