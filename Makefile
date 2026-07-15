.PHONY: test list-tools smoke eval workspace-status live-component-check live-closed-loop live-ingest-loop live-ingest-loop-resume serve-api serve-dev clean

PYTHON ?= python3
ENV_FILE ?=
ENV_FILE_ARG = $(if $(ENV_FILE),--env-file $(ENV_FILE),)

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

list-tools:
	PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake PSKA_REVIEW_DB=:memory: PYTHONPATH=src $(PYTHON) -m pska_essential --list-tools

smoke:
	PYTHONPATH=src $(PYTHON) -c 'from pska_essential.workflow import build_fake_service; print(build_fake_service().eval_run("smoke"))'

eval:
	PYTHONPATH=src $(PYTHON) -m pska_essential.eval $(ENV_FILE_ARG) $(or $(PSKA_EVAL_SUITE),product_acceptance)

workspace-status:
	@PYTHONPATH=src $(PYTHON) -m pska_essential.workspace_status_cli $(ENV_FILE_ARG)

live-component-check:
	PYTHONPATH=src $(PYTHON) -m pska_essential.component_check $(ENV_FILE_ARG)

live-closed-loop:
	PYTHONPATH=src $(PYTHON) -m pska_essential.live_closed_loop $(ENV_FILE_ARG)

live-ingest-loop:
	PYTHONPATH=src $(PYTHON) -m pska_essential.ingest_loop $(ENV_FILE_ARG)

live-ingest-loop-resume:
	PYTHONPATH=src $(PYTHON) -m pska_essential.ingest_loop_resume $(ENV_FILE_ARG)

serve-api:
	PYTHONPATH=src $(PYTHON) -m pska_essential.product_api $(ENV_FILE_ARG)

serve-dev:
	PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake PSKA_REVIEW_DB=.pska-essential/dev.sqlite3 PYTHONPATH=src $(PYTHON) -m pska_essential.product_api

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
