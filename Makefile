.PHONY: lint format check test all

# Run ruff linter
lint:
	uv run ruff check .

# Auto-fix lint issues
lint-fix:
	uv run ruff check . --fix

# Check formatting (no changes)
format-check:
	uv run ruff format --check .

# Apply formatting
format:
	uv run ruff format .

# Lint + format check (CI-friendly, no modifications)
check: lint format-check

# Run all tests
test:
	uv run pytest

# Fix lint + format + test
all: lint-fix format test
