.PHONY: test list-tools smoke live-component-check live-closed-loop live-ingest-loop live-ingest-loop-resume serve-api serve-dev clean

PYTHON ?= python3

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

list-tools:
	PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake PSKA_REVIEW_DB=:memory: PYTHONPATH=src $(PYTHON) -m pska_essential --list-tools

smoke:
	PYTHONPATH=src $(PYTHON) -c 'from pska_essential.workflow import build_fake_service; print(build_fake_service().eval_run("smoke"))'

live-component-check:
	PYTHONPATH=src $(PYTHON) -m pska_essential.component_check

live-closed-loop:
	PYTHONPATH=src $(PYTHON) -m pska_essential.live_closed_loop

live-ingest-loop:
	PYTHONPATH=src $(PYTHON) -m pska_essential.ingest_loop

live-ingest-loop-resume:
	PYTHONPATH=src $(PYTHON) -m pska_essential.ingest_loop_resume

serve-api:
	PYTHONPATH=src $(PYTHON) -m pska_essential.product_api

serve-dev:
	PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake PSKA_REVIEW_DB=.pska-essential/dev.sqlite3 PYTHONPATH=src $(PYTHON) -m pska_essential.product_api

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
