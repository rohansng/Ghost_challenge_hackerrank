"""
models.py - Canonical Data Models for Ghost Data Still Exists.
Provides explicit schemas, typed representations, and the core CaseContext model.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any


class Phase(str, Enum):
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


class Operation(str, Enum):
    # Findings
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"
    
    # Remediation
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"
    
    # Verification
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


class ResourceState(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"


class DeletionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RequestType(str, Enum):
    DELETION = "DELETION"
    ACCESS_REQUEST = "ACCESS_REQUEST"
    PORTABILITY_REQUEST = "PORTABILITY_REQUEST"
    RECTIFICATION_REQUEST = "RECTIFICATION_REQUEST"
    MARKETING_OPT_OUT = "MARKETING_OPT_OUT"
    ACCOUNT_ASSISTANCE = "ACCOUNT_ASSISTANCE"
    UNKNOWN = "UNKNOWN"


class MatchRelationship(str, Enum):
    USER_ID = "USER_ID"
    CURRENT_EMAIL = "CURRENT_EMAIL"
    HISTORICAL_EMAIL = "HISTORICAL_EMAIL"
    CURRENT_PHONE = "CURRENT_PHONE"
    HISTORICAL_PHONE = "HISTORICAL_PHONE"
    EMAIL_HASH = "EMAIL_HASH"
    HISTORICAL_HASH = "HISTORICAL_HASH"
    NAME = "NAME"
    RESOURCE_ID = "RESOURCE_ID"


@dataclass(frozen=True)
class Step:
    step_no: int
    phase: Phase
    system_id: str
    resource_id: str
    operation: Operation
    state: ResourceState
    evidence_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_no": self.step_no,
            "phase": self.phase.value,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation.value,
            "state": self.state.value,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True)
class UserIdentityRecord:
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime


@dataclass(frozen=True)
class AuditLogRecord:
    audit_id: str
    user_id: str
    event_time: datetime
    field_name: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class SystemActivityRecord:
    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


@dataclass(frozen=True)
class DeletionRuleRecord:
    rule_id: str
    data_category: str
    condition: str
    required_action: str


@dataclass(frozen=True)
class EvidenceFileRecord:
    file_id: str
    file_path: str
    origin: str
    captured_at: datetime


@dataclass(frozen=True)
class DeletionRequestRecord:
    case_id: str
    email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str


@dataclass
class IdentifierInterval:
    field_name: str
    value: str
    valid_from: Optional[datetime]
    valid_to: Optional[datetime]
    source_audit_id: Optional[str] = None


@dataclass
class IdentityNode:
    canonical_user_id: str
    current_name: str
    current_email: str
    current_phone: str
    current_email_hash: str
    updated_at: datetime
    
    # Historical interval tracking
    all_emails: Set[str] = field(default_factory=set)
    all_phones: Set[str] = field(default_factory=set)
    all_hashes: Set[str] = field(default_factory=set)
    all_names: Set[str] = field(default_factory=set)
    
    email_intervals: List[IdentifierInterval] = field(default_factory=list)
    phone_intervals: List[IdentifierInterval] = field(default_factory=list)
    hash_intervals: List[IdentifierInterval] = field(default_factory=list)
    
    def get_identity_at(self, at_time: datetime) -> Dict[str, str]:
        """Reconstruct the user's active identity fields at timestamp at_time."""
        active_email = self.current_email
        for interval in self.email_intervals:
            from_ok = interval.valid_from is None or interval.valid_from <= at_time
            to_ok = interval.valid_to is None or at_time < interval.valid_to
            if from_ok and to_ok:
                active_email = interval.value
                break
                
        active_phone = self.current_phone
        for interval in self.phone_intervals:
            from_ok = interval.valid_from is None or interval.valid_from <= at_time
            to_ok = interval.valid_to is None or at_time < interval.valid_to
            if from_ok and to_ok:
                active_phone = interval.value
                break
                
        active_hash = self.current_email_hash
        for interval in self.hash_intervals:
            from_ok = interval.valid_from is None or interval.valid_from <= at_time
            to_ok = interval.valid_to is None or at_time < interval.valid_to
            if from_ok and to_ok:
                active_hash = interval.value
                break

        return {
            "user_id": self.canonical_user_id,
            "name": self.current_name,
            "email": active_email,
            "phone": active_phone,
            "email_hash": active_hash,
            "as_of": at_time.isoformat()
        }


@dataclass
class IdentifierMatch:
    matched_value: str
    relationship: MatchRelationship
    confidence: float
    source: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    evidence_reference: Optional[str] = None


@dataclass
class CaseContext:
    case_id: str
    requested_email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str

    # Intent analysis
    is_deletion_authorized: bool = True
    request_type: RequestType = RequestType.DELETION
    intent_reason: str = ""

    # Identity Resolution
    canonical_user_id: Optional[str] = None
    identity_node: Optional[IdentityNode] = None
    active_identity_at_audit: Dict[str, str] = field(default_factory=dict)
    matched_identifiers: List[IdentifierMatch] = field(default_factory=list)
    identity_ambiguities: List[str] = field(default_factory=list)

    # Discovered system resources
    matched_resources: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    candidate_activity_ids: Set[str] = field(default_factory=set)

    # Deletion State & Findings
    findings: List[Step] = field(default_factory=list)
    remediations: List[Step] = field(default_factory=list)
    verifications: List[Step] = field(default_factory=list)

    # Final verdict
    deletion_status: Optional[DeletionStatus] = None
    steps: List[Step] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
