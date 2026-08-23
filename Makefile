.PHONY: test list-tools smoke eval workspace-status product-boundary-contract live-product-boundary-contract alpha-acceptance alpha-acceptance-webui alpha-acceptance-demo dogfood-init dogfood-init-dry-run dogfood-init-register live-connectivity-check live-component-check live-closed-loop live-markitdown-smoke live-docling-smoke live-watchdog-smoke live-fclones-smoke live-czkawka-smoke live-ingest-loop live-ingest-loop-resume webui-extension-contract webui-extension-visual webui-extension-turn-bridge webui-extension-llm-proof demo-browser-verify demo-browser-verify-videos demo-browser-customer-package demo-browser-package serve-api serve-dev start-workspace alpha-compose-up alpha-compose-ps alpha-compose-down full-compose-preflight full-compose-init full-compose-embedding-up full-compose-ragflow-up full-compose-up full-compose-status full-compose-down clean

PYTHON ?= python3
ENV_FILE ?=
START_WORKSPACE_ARGS ?=
DOGFOOD_ROOT ?= $(HOME)/PSKA-Dogfood
PSKA_API_BASE_URL ?= http://127.0.0.1:8765
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

product-boundary-contract:
	$(PYTHON) scripts/verify_product_boundaries.py

live-product-boundary-contract:
	$(PYTHON) scripts/verify_product_boundaries.py \
	  --live-hermes-config "$${HERMES_CONFIG_PATH:-$${HOME}/.hermes/config.yaml}" \
	  --live-webui-extension-manifest "$${HERMES_WEBUI_EXTENSION_MANIFEST_PATH:-$${HERMES_WEBUI_EXTENSION_DIR:-$${HOME}/.hermes/webui-local-extensions}/$${HERMES_WEBUI_EXTENSION_MANIFEST:-extensions.json}}" \
	  --live-webui-extension-overrides "$${HERMES_WEBUI_EXTENSION_OVERRIDES_PATH:-$${HERMES_WEBUI_STATE_DIR:-$${HOME}/.hermes/webui}/extension-overrides.json}"

alpha-acceptance:
	PYTHONPATH=src $(PYTHON) scripts/run_alpha_acceptance.py $(ENV_FILE_ARG)

alpha-acceptance-webui:
	PYTHONPATH=src $(PYTHON) scripts/run_alpha_acceptance.py $(ENV_FILE_ARG) --include-live-product-boundary-contract --include-webui-contract --include-webui-visual --include-webui-turn-bridge --include-recovery-boundary

alpha-acceptance-demo:
	PYTHONPATH=src $(PYTHON) scripts/run_alpha_acceptance.py $(ENV_FILE_ARG) --include-live-product-boundary-contract --include-webui-contract --include-webui-visual --include-webui-turn-bridge --include-recovery-boundary --include-demo-videos --include-eidolia-bridge --timeout $${PSKA_ALPHA_DEMO_TIMEOUT:-240}

dogfood-init:
	$(PYTHON) scripts/init_dogfood_workspace.py --root "$(DOGFOOD_ROOT)"

dogfood-init-dry-run:
	$(PYTHON) scripts/init_dogfood_workspace.py --root "$(DOGFOOD_ROOT)" --dry-run

dogfood-init-register:
	$(PYTHON) scripts/init_dogfood_workspace.py --root "$(DOGFOOD_ROOT)" --register --scan --api-base-url "$(PSKA_API_BASE_URL)"

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

webui-extension-turn-bridge:
	node scripts/test_pska_webui_turn_bridge.cjs

webui-extension-llm-proof:
	node scripts/test_pska_webui_llm_proof.cjs

demo-browser-verify:
	$(PYTHON) scripts/verify_hermes_extension_demo_pack.py

demo-browser-verify-videos:
	$(PYTHON) scripts/verify_hermes_extension_demo_pack.py --all-videos --require-video --require-delivery-pack

demo-browser-customer-package:
	$(PYTHON) scripts/build_customer_demo_video.py
	$(PYTHON) scripts/package_customer_demo_assets.py
	$(PYTHON) scripts/verify_hermes_extension_demo_pack.py --all-videos --require-video --require-delivery-pack

demo-browser-package:
	@echo "Legacy diagnostic-page demo packaging is disabled."
	@echo "Use make demo-browser-customer-package for the Hermes WebUI customer walkthrough delivery pack."

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
