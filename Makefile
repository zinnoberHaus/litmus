.PHONY: install dev setup demo doctor test test-cov lint format check clean build verify-examples

# Most users do NOT need this Makefile. End-user install is one line:
#     pipx install litmus-data
#
# This file is for development on Litmus itself.

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

# Dev bootstrap: venv + editable install + doctor + .env scaffold.
setup:
	@./scripts/setup.sh

# Load + run the sample e-commerce pipeline end-to-end. Five-minute demo.
demo:
	@litmus demo
	@echo ""
	@echo "Demo loaded. Open the dashboard:"
	@echo "  litmus dashboard"

# Verify environment + integrations.
doctor:
	@litmus doctor

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --tb=short --cov=litmus --cov-report=term-missing

lint:
	ruff check litmus/ tests/
	mypy litmus/

format:
	ruff format litmus/ tests/
	ruff check --fix litmus/ tests/

check: lint test

# Run the Examples smoke test locally (same as .github/workflows/examples.yml).
verify-examples:
	@./scripts/verify-examples.sh

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

build: clean
	python -m build
