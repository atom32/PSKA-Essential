from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


DURABLE_PROPOSAL_KINDS = {"memory_delete", "memory_patch", "memory_update"}
MANUAL_REVIEW = "manual_review"
AUTO_ACCEPT = "auto_accept"
AUTO_APPLY = "auto_apply"
VALID_DURABLE_MODES = {MANUAL_REVIEW, AUTO_ACCEPT, AUTO_APPLY}
CONVERSATION_ORIGIN = "conversation"
DIGEST_ORIGIN = "digest"
DURABLE_ORIGIN = "durable"
REVIEW_QUEUE_ROLE = "exception_inbox"
MEMORY_PRIMARY_USER_PATH = "conversation"


@dataclass(frozen=True, slots=True)
class WorkspaceGovernancePolicy:
    """Workspace policy for durable knowledge changes.

    This is intentionally product-level language. Backends and agents may differ,
    but PSKA owns the decision about how transient outputs become durable
    workspace knowledge.
    """

    durable_memory: str = MANUAL_REVIEW
    conversation_memory: str = AUTO_APPLY
    digest_memory: str = MANUAL_REVIEW

    def action_for(
        self,
        proposal_kind: str,
        *,
        force_review: bool = False,
        origin: str = DURABLE_ORIGIN,
    ) -> str:
        normalized = proposal_kind.strip().lower()
        if force_review:
            return MANUAL_REVIEW
        if normalized in DURABLE_PROPOSAL_KINDS:
            normalized_origin = origin.strip().lower()
            if normalized_origin == CONVERSATION_ORIGIN:
                return self.conversation_memory
            if normalized_origin == DIGEST_ORIGIN:
                return self.digest_memory
            return self.durable_memory
        return "skip"

    def to_dict(self) -> dict[str, Any]:
        return {
            "durable_memory": self.durable_memory,
            "conversation_memory": self.conversation_memory,
            "digest_memory": self.digest_memory,
            "memory_primary_user_path": MEMORY_PRIMARY_USER_PATH,
            "review_queue_role": REVIEW_QUEUE_ROLE,
            "review_queue_triggers": [
                "uncertain",
                "risky",
                "conflicting",
                "ambiguous_destructive",
                "broad_destructive",
                "batch_derived",
                "force_review",
            ],
            "conversation_memory_guidance": (
                "Normal user-driven remember/correct/forget requests are handled "
                "inside conversation. The agent selects add, update, delete, or "
                "clarify intent, and PSKA governs the resulting conversation-memory "
                "change. Clear conversation deletes or corrections do not become "
                "visible Review items by default. Review is a visible exception "
                "inbox, not the daily memory editor."
            ),
            "visible_memory_editor": "conversation",
            "visible_review_role": "exception_only",
            "internal_governance_records": [
                "proposal",
                "decision",
                "memory_apply",
                "audit",
            ],
            "durable_modes": sorted(VALID_DURABLE_MODES),
            "durable_proposal_kinds": sorted(DURABLE_PROPOSAL_KINDS),
            "actions": {
                proposal_kind: self.action_for(proposal_kind)
                for proposal_kind in sorted(DURABLE_PROPOSAL_KINDS)
            },
            "conversation_actions": {
                proposal_kind: self.action_for(proposal_kind, origin=CONVERSATION_ORIGIN)
                for proposal_kind in sorted(DURABLE_PROPOSAL_KINDS)
            },
            "digest_actions": {
                proposal_kind: self.action_for(proposal_kind, origin=DIGEST_ORIGIN)
                for proposal_kind in sorted(DURABLE_PROPOSAL_KINDS)
            },
            "transient_results": "skip",
        }


def build_workspace_policy_from_env() -> WorkspaceGovernancePolicy:
    durable_memory = os.getenv("PSKA_GOVERNANCE_DURABLE_MEMORY", MANUAL_REVIEW).strip().lower()
    conversation_memory = os.getenv("PSKA_GOVERNANCE_CONVERSATION_MEMORY", AUTO_APPLY).strip().lower()
    digest_memory = os.getenv("PSKA_GOVERNANCE_DIGEST_MEMORY", MANUAL_REVIEW).strip().lower()
    _validate_mode("PSKA_GOVERNANCE_DURABLE_MEMORY", durable_memory)
    _validate_mode("PSKA_GOVERNANCE_CONVERSATION_MEMORY", conversation_memory)
    _validate_mode("PSKA_GOVERNANCE_DIGEST_MEMORY", digest_memory)
    return WorkspaceGovernancePolicy(
        durable_memory=durable_memory,
        conversation_memory=conversation_memory,
        digest_memory=digest_memory,
    )


def _validate_mode(env_name: str, value: str) -> None:
    if value in VALID_DURABLE_MODES:
        return
    raise ValueError(f"{env_name} must be one of: " + ", ".join(sorted(VALID_DURABLE_MODES)))
