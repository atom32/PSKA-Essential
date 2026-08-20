.PHONY: test list-tools smoke eval workspace-status live-connectivity-check live-component-check live-closed-loop live-markitdown-smoke live-docling-smoke live-watchdog-smoke live-fclones-smoke live-czkawka-smoke live-ingest-loop live-ingest-loop-resume webui-extension-contract webui-extension-visual demo-browser-verify demo-browser-package serve-api serve-dev start-workspace alpha-compose-up alpha-compose-ps alpha-compose-down full-compose-preflight full-compose-init full-compose-embedding-up full-compose-ragflow-up full-compose-up full-compose-status full-compose-down clean

PYTHON ?= python3
ENV_FILE ?=
START_WORKSPACE_ARGS ?=
ENV_FILE_ARG = $(if $(ENV_FILE),--env-file $(ENV_FILE),)

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

list-tools:
	PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake PSKA_REVIEW_DB=:memory: PYTHONPATH=src $(PYTHON) -m pska_essential --list-tools

smoke:
	PYTHONPATH=src $(PYTHON) -c 'from pska_essential.workflow import build_fake_service; print(build_fake_service().eval_run("smoke"))'

eval:
	PYTHONPATH=src $(PYTHON) -m pska_essential.eval $(ENV_FILE_ARG) $(or $(PSKA_EVAL_SUITE),product_acceptance)

workspace-status:
	@PYTHONPATH=src $(PYTHON) -m pska_essential.workspace_status_cli $(ENV_FILE_ARG)

live-component-check:
	PYTHONPATH=src $(PYTHON) -m pska_essential.component_check $(ENV_FILE_ARG)

live-connectivity-check:
	PSKA_COMPONENT_CONNECTIVITY_ONLY=1 PYTHONPATH=src $(PYTHON) -m pska_essential.component_check $(ENV_FILE_ARG)

live-closed-loop:
	PYTHONPATH=src $(PYTHON) -m pska_essential.live_closed_loop $(ENV_FILE_ARG)

live-markitdown-smoke:
	PYTHONPATH=src $(PYTHON) scripts/markitdown_smoke.py

live-docling-smoke:
	@PYTHONPATH=src $(PYTHON) scripts/docling_smoke.py; code=$$?; \
	if [ "$$code" = "77" ]; then \
		echo "docling optional extra unavailable; install with: $(PYTHON) -m pip install '.[extract-docling]'"; \
		exit 0; \
	fi; \
	exit "$$code"

live-watchdog-smoke:
	PYTHONPATH=src $(PYTHON) scripts/watchdog_smoke.py

live-fclones-smoke:
	@PYTHONPATH=src $(PYTHON) scripts/fclones_smoke.py; code=$$?; \
	if [ "$$code" = "77" ]; then \
		echo "fclones optional CLI unavailable; set PSKA_FCLONES_BIN or add fclones to PATH."; \
		exit 0; \
	fi; \
	exit "$$code"

live-czkawka-smoke:
	@PYTHONPATH=src $(PYTHON) scripts/czkawka_smoke.py; code=$$?; \
	if [ "$$code" = "77" ]; then \
		echo "Czkawka optional CLI unavailable; set PSKA_CZKAWKA_BIN or add czkawka_cli to PATH."; \
		exit 0; \
	fi; \
	exit "$$code"

live-ingest-loop:
	PYTHONPATH=src $(PYTHON) -m pska_essential.ingest_loop $(ENV_FILE_ARG)

live-ingest-loop-resume:
	PYTHONPATH=src $(PYTHON) -m pska_essential.ingest_loop_resume $(ENV_FILE_ARG)

webui-extension-contract:
	node scripts/test_pska_webui_extension.mjs

webui-extension-visual:
	node scripts/test_pska_webui_visual.cjs

demo-browser-verify:
	$(PYTHON) scripts/verify_hermes_extension_demo_pack.py

demo-browser-package:
	@echo "Legacy diagnostic-page demo packaging is disabled."
	@echo "Use node scripts/record_hermes_pska_extension_demo.cjs, then python3 scripts/verify_hermes_extension_demo_pack.py --require-video."

serve-api:
	PYTHONPATH=src $(PYTHON) -m pska_essential.product_api $(ENV_FILE_ARG)

serve-dev:
	PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake PSKA_REVIEW_DB=.pska-essential/dev.sqlite3 PYTHONPATH=src $(PYTHON) -m pska_essential.product_api

start-workspace:
	scripts/start_pska_workspace.sh $(START_WORKSPACE_ARGS)

alpha-compose-up:
	cd deploy/alpha-compose && docker compose up -d --build

alpha-compose-ps:
	cd deploy/alpha-compose && docker compose ps

alpha-compose-down:
	cd deploy/alpha-compose && docker compose down

full-compose-preflight:
	cd deploy/full-compose && ./bootstrap.sh preflight

full-compose-init:
	cd deploy/full-compose && ./bootstrap.sh init

full-compose-embedding-up:
	cd deploy/full-compose && ./bootstrap.sh embedding-up

full-compose-ragflow-up:
	cd deploy/full-compose && ./bootstrap.sh ragflow-up

full-compose-up:
	cd deploy/full-compose && ./bootstrap.sh up

full-compose-status:
	cd deploy/full-compose && ./bootstrap.sh status

full-compose-down:
	cd deploy/full-compose && ./bootstrap.sh down

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
