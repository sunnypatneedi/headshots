# headshots - see README.md
.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python

help:  ## show this
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t22

dev: $(VENV)  ## install for development, with the test tools
	$(VENV)/bin/pip install -q -e ".[dev]"

$(VENV):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip

test: dev  ## run the tests (no photos, no models, no network needed)
	$(VENV)/bin/pytest

lint: dev  ## check style
	$(VENV)/bin/ruff check src tests

app:  ## build Headshots.app into dist/ (macOS only)
	./scripts/build-app.sh

dmg: app  ## build the .dmg
	./scripts/make-dmg.sh

clean:  ## remove build output
	rm -rf build dist *.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: help dev test lint app dmg clean
