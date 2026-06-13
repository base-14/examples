.PHONY: check build vet

# Pinned legacy project (Go 1.19) — check is build + vet only, no upgrades.
check:
	go vet ./...
	go build ./...

build:
	go build ./...

vet:
	go vet ./...

.DEFAULT_GOAL := check
