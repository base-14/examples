.PHONY: check run clean

# This example is a single script with no lint/type/test tooling configured.
# The verify gate is a byte-compile of the source (Python has no build step).
check:
	python3 -m py_compile main.py

run:
	python3 main.py

clean:
	rm -rf __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

.DEFAULT_GOAL := check
