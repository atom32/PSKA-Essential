from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


DURABLE_PROPOSAL_KINDS = {"memory_patch"}
MANUAL_REVIEW = "manual_review"
AUTO_ACCEPT = "auto_accept"
AUTO_APPLY = "auto_apply"
VALID_DURABLE_MODES = {MANUAL_REVIEW, AUTO_ACCEPT, AUTO_APPLY}


@dataclass(frozen=True, slots=True)
class WorkspaceGovernancePolicy:
    """Workspace policy for durable knowledge changes.

    This is intentionally product-level language. Backends and agents may differ,
    but PSKA owns the decision about how transient outputs become durable
    workspace knowledge.
    """

    durable_memory: str = MANUAL_REVIEW

    def action_for(self, proposal_kind: str, *, force_review: bool = False) -> str:
        normalized = proposal_kind.strip().lower()
        if normalized in DURABLE_PROPOSAL_KINDS:
            return self.durable_memory
        if force_review:
            return MANUAL_REVIEW
        return "skip"

    def to_dict(self) -> dict[str, Any]:
        return {
            "durable_memory": self.durable_memory,
            "durable_modes": sorted(VALID_DURABLE_MODES),
        }


def build_workspace_policy_from_env() -> WorkspaceGovernancePolicy:
    durable_memory = os.getenv("PSKA_GOVERNANCE_DURABLE_MEMORY", MANUAL_REVIEW).strip().lower()
    if durable_memory not in VALID_DURABLE_MODES:
        raise ValueError(
            "PSKA_GOVERNANCE_DURABLE_MEMORY must be one of: "
            + ", ".join(sorted(VALID_DURABLE_MODES))
        )
    return WorkspaceGovernancePolicy(durable_memory=durable_memory)
