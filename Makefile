.PHONY: install check lint lint-fix type test

install:
	python3 -m pip install -e ".[gdrive,dev]"

lint:
	python3 -m ruff check core_lib

lint-fix:
	python3 -m ruff check core_lib --fix

type:
	python3 -m mypy core_lib

test:
	python3 -m pytest --tb=short

check: lint type test
