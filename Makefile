.PHONY: install test lint typecheck validate benchmark serve

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check arena tests
	ruff format --check arena tests

typecheck:
	mypy arena

validate:
	arena validate benchmark_sets/v1
	arena validate benchmark_sets/audit_v1

benchmark:
	arena run benchmark_sets/v1 --reviewer mock:perfect_patch --mode full --allow-local-execution

serve:
	arena serve --host 0.0.0.0 --port 8000
