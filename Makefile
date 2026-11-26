# AWAGO developer tasks (macOS/Linux; on Windows use `python run.py ...`).
.PHONY: help install install-ml lint format typecheck test test-fast coverage run run-full seed train clean

PY := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "make install      - install runtime + dev dependencies"
	@echo "make install-ml   - install optional ML extras (PyTorch etc.)"
	@echo "make lint         - ruff check"
	@echo "make format       - ruff format"
	@echo "make typecheck    - mypy"
	@echo "make test         - full pytest suite with coverage"
	@echo "make test-fast    - pytest without coverage"
	@echo "make run          - launcher (lite profile)"
	@echo "make run-full     - launcher (full profile)"
	@echo "make seed         - seed demo data"
	@echo "make train        - train models (quick)"
	@echo "make clean        - remove caches and build artifacts"

install:
	$(PIP) install -r requirements.txt -r requirements-dev.txt

install-ml: install
	$(PIP) install -r requirements-ml.txt

lint:
	$(PY) -m ruff check app scripts tests
	$(PY) -m ruff format --check app scripts tests

format:
	$(PY) -m ruff format app scripts tests
	$(PY) -m ruff check --fix app scripts tests

typecheck:
	$(PY) -m mypy

test:
	$(PY) -m pytest tests/ --cov --cov-report=term-missing

test-fast:
	$(PY) -m pytest tests/

run:
	$(PY) run.py --profile lite

run-full:
	$(PY) run.py --profile full

seed:
	$(PY) scripts/seed_demo.py

train:
	$(PY) scripts/train_models.py --quick

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
