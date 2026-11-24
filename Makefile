VENV := .venv
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip
STAMP := $(VENV)/.installed

.PHONY: venv install check lint lint-fix type test quality-eval-agent gdrive-bot clean-venv validate-audit

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

venv: $(VENV)/bin/activate

$(STAMP): pyproject.toml $(VENV)/bin/activate
	$(PIP) install -e ".[gdrive,dev]"
	touch $(STAMP)

install: $(STAMP)

check: lint type test validate-audit

lint: install
	$(PYTHON) -m ruff check core_lib

lint-fix: install
	$(PYTHON) -m ruff check core_lib --fix

type: install
	$(PYTHON) -m mypy core_lib

test: install
	$(PYTHON) -m pytest --tb=short

validate-audit: install
	$(PYTHON) scripts/validate_audit_sync.py

quality-eval-agent: install
	@test -f .env || (echo "Error: .env file not found. Copy .env.example to .env and fill required values." >&2; exit 1)
	$(PYTHON) scripts/quality_eval_agent.py

gdrive-bot:
	@command -v act >/dev/null 2>&1 || (echo "Error: 'act' is not installed or not in PATH." >&2; exit 1)
	@test -f .env || (echo "Error: .env file not found. Copy .env.example to .env and fill required values." >&2; exit 1)
	act workflow_dispatch \
		-W .github/workflows/gdrive_bot.yml \
		--secret-file .env \
		--verbose

clean-venv:
	rm -rf $(VENV)
