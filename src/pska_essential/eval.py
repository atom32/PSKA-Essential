from __future__ import annotations

from pska_essential.workflow import WorkflowService


def run_smoke_eval(service: WorkflowService) -> dict:
    return service.eval_run("smoke")
