.PHONY: install dev test lint format check clean build

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

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

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

build: clean
	python -m build
