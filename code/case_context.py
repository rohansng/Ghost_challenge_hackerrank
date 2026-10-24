"""
case_context.py - Canonical Case Context Builder for Ghost Data Still Exists.
Initializes the central CaseContext contract connecting intent, temporal identity,
discovered candidate activities, and audit horizons.
"""

from typing import List, Dict, Set, Optional, Any
from code.models import (
    CaseContext,
    DeletionRequestRecord,
    DeletionStatus,
    RequestType,
    SystemActivityRecord,
)
from code.intent_classifier import IntentClassifier
from code.identity_engine import IdentityEngine, IdentityResolutionResult


class CaseContextBuilder:
    """Constructs enriched CaseContext models from raw requests and domain state."""

    def __init__(self, identity_engine: IdentityEngine, activities: Optional[List[SystemActivityRecord]] = None):
        self.identity_engine = identity_engine
        self.activities = activities or []
        
        # Build inverted index of activities by resource and text for rapid candidate discovery
        self._activity_by_resource: Dict[str, List[SystemActivityRecord]] = {}
        for act in self.activities:
            self._activity_by_resource.setdefault(act.resource_id, []).append(act)

    def build_case_context(self, request: DeletionRequestRecord) -> CaseContext:
        """Constructs an enriched, fully resolved CaseContext for an evaluation request."""
        # 1. Intent classification
        is_del, req_type, intent_reason = IntentClassifier.classify(request.request_text)

        context = CaseContext(
            case_id=request.case_id,
            requested_email=request.email,
            requested_at=request.requested_at,
            reported_status=request.reported_status,
            reported_at=request.reported_at,
            audit_at=request.audit_at,
            request_text=request.request_text,
            is_deletion_authorized=is_del,
            request_type=req_type,
            intent_reason=intent_reason,
        )

        # If not authorized, mark NOT_APPLICABLE immediately
        if not is_del:
            context.deletion_status = DeletionStatus.NOT_APPLICABLE
            context.steps = []
            return context

        # 2. Identity Resolution
        res: IdentityResolutionResult = self.identity_engine.resolve_identity(request.email)
        if res.is_resolved and res.identity_node:
            context.canonical_user_id = res.canonical_user_id
            context.identity_node = res.identity_node
            context.matched_identifiers = res.matched_identifiers
            context.active_identity_at_audit = res.identity_node.get_identity_at(request.audit_at)
        else:
            context.identity_ambiguities = res.ambiguities

        return context
