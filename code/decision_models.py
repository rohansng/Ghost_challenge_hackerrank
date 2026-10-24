"""
decision_models.py - Canonical CaseProof & Decision Data Models for Ghost Data Still Exists.
Provides structured, explainable proof models and explicit 11-point decision checklists.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from code.models import DeletionStatus, Step, Phase, Operation
from code.evidence_models import ObservedState


class ChecklistItem(Enum):
    CORRECT_IDENTITY_RESOLVED = "1. Correct identity resolved"
    HISTORICAL_IDENTIFIERS_CONSIDERED = "2. Correct historical identifiers considered"
    ALL_RELEVANT_RESOURCES_IDENTIFIED = "3. All relevant copies/resources identified"
    EVERY_RESOURCE_RECEIVED_REQUIRED_TREATMENT = "4. Every applicable resource received required treatment"
    REQUIRED_RETAINED_RECORDS_REMAIN = "5. Required retained records remain"
    RETAINED_RECORDS_CONTAIN_ONLY_PERMITTED_DATA = "6. Retained records contain only permitted identifiers/data"
    NO_PROHIBITED_DATA_REMAINS = "7. No relevant prohibited data remains"
    NO_ACTIVE_RECREATION_OR_RESTORE_PATH = "8. No active sync/import/restore path can recreate prohibited data"
    REQUIRED_VERIFICATION_EVIDENCE_EXISTS = "9. Required verification evidence exists"
    EVIDENCE_WITHIN_TEMPORAL_BOUNDARY = "10. Evidence is valid and within permitted temporal boundary"
    NO_UNRESOLVED_CONTRADICTIONS = "11. No unresolved contradiction invalidates the proof"


class IncompleteReason(Enum):
    DATA_REMAINS = "DATA_REMAINS"
    HISTORICAL_IDENTIFIER_REMAINS = "HISTORICAL_IDENTIFIER_REMAINS"
    RESOURCE_NOT_TREATED = "RESOURCE_NOT_TREATED"
    PROHIBITED_RETAINED_IDENTIFIER = "PROHIBITED_RETAINED_IDENTIFIER"
    ACTIVE_SYNC = "ACTIVE_SYNC"
    RESTORE_RISK = "RESTORE_RISK"
    MISSING_VERIFICATION = "MISSING_VERIFICATION"
    UNRESOLVED_IDENTITY = "UNRESOLVED_IDENTITY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    POST_AUDIT_ACTIVITY = "POST_AUDIT_ACTIVITY"
    NO_DELETION_REQUESTED = "NO_DELETION_REQUESTED"


@dataclass
class IdentityProof:
    user_id: Optional[str]
    matched_identifiers: List[str]
    historical_emails: List[str]
    phones: List[str]
    hashes: List[str]
    is_resolved: bool
    ambiguities: List[str] = field(default_factory=list)


@dataclass
class ResourceProof:
    resource_id: str
    system_id: str
    data_category: str
    proven_state: ObservedState
    cited_evidence_id: str
    is_compliant: bool
    has_prohibited_pii: bool = False
    failure_reason: Optional[str] = None


@dataclass
class PolicyProofSummary:
    total_resources_evaluated: int
    compliant_resources: int
    violations: List[str] = field(default_factory=list)


@dataclass
class TemporalProof:
    audit_at: datetime
    latest_observation_time: Optional[datetime]
    is_strictly_bounded: bool
    post_audit_observations_excluded: int
    contradictions_detected: int


@dataclass
class RecreationProofSummary:
    active_sync_flows_count: int
    active_restore_risks_count: int
    disabled_flows_count: int
    blocked_restores_count: int
    recreation_threat_details: List[str] = field(default_factory=list)


@dataclass
class RetentionProof:
    has_required_retention: bool
    retained_resources: List[str]
    tombstones_evaluated: List[str]
    prohibited_identifiers_in_retained: List[str] = field(default_factory=list)
    is_retention_compliant: bool = True


@dataclass
class VerificationProof:
    total_verifications: int
    verified_absent: List[str] = field(default_factory=list)
    verified_present: List[str] = field(default_factory=list)
    verified_redacted: List[str] = field(default_factory=list)
    verified_anonymized: List[str] = field(default_factory=list)
    verified_disabled: List[str] = field(default_factory=list)
    verified_blocked: List[str] = field(default_factory=list)
    missing_evidence_resources: List[str] = field(default_factory=list)


@dataclass
class CaseProof:
    """Canonical explainable proof contract for each evaluation case."""
    case_id: str
    requested_email: str
    audit_at: datetime
    is_deletion_authorized: bool
    final_decision: DeletionStatus
    decision_reasons: List[IncompleteReason] = field(default_factory=list)
    checklist: Dict[str, bool] = field(default_factory=dict)
    
    # Sub-proofs
    identity_proof: Optional[IdentityProof] = None
    resource_proofs: List[ResourceProof] = field(default_factory=list)
    policy_proofs: Optional[PolicyProofSummary] = None
    temporal_proofs: Optional[TemporalProof] = None
    recreation_proofs: Optional[RecreationProofSummary] = None
    retention_proofs: Optional[RetentionProof] = None
    verification_proofs: Optional[VerificationProof] = None
    steps: List[Step] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "requested_email": self.requested_email,
            "audit_at": self.audit_at.isoformat() if self.audit_at else None,
            "is_deletion_authorized": self.is_deletion_authorized,
            "final_decision": self.final_decision.value,
            "decision_reasons": [r.value for r in self.decision_reasons],
            "checklist": self.checklist,
            "steps_count": len(self.steps),
            "findings_count": sum(1 for s in self.steps if s.phase == Phase.FINDING),
            "remediations_count": sum(1 for s in self.steps if s.phase == Phase.REMEDIATION),
            "verifications_count": sum(1 for s in self.steps if s.phase == Phase.VERIFICATION),
        }
