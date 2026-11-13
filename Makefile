.PHONY: install check lint type test

install:
	pip install -e ".[gdrive,dev]"

lint:
	python3 -m ruff check core_lib

type:
	python3 -m mypy core_lib

test:
	python3 -m pytest --tb=short

check: lint type test
