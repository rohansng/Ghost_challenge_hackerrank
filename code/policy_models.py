"""
Phase 3 Policy Models
Structured policy rule representation, action enums, and explainable policy proofs.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime

from code.evidence_models import ObservedState
from code.models import Operation, ResourceState, Phase, Step


class PolicyAction(str, Enum):
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    RETAIN = "RETAIN"
    TOMBSTONE = "TOMBSTONE"


class ConditionType(str, Enum):
    ALWAYS = "ALWAYS"
    SHARED_CONTEXT = "SHARED_CONTEXT"
    SUBJECT_ATTACHMENT = "SUBJECT_ATTACHMENT"
    ATTRIBUTABLE_TO_USER = "ATTRIBUTABLE_TO_USER"
    CONTAINS_EMAIL = "CONTAINS_EMAIL"
    WITHIN_RETENTION = "WITHIN_RETENTION"
    LEGAL_HOLD_ACTIVE = "LEGAL_HOLD_ACTIVE"
    RESTORE_BLOCKED = "RESTORE_BLOCKED"
    ACCOUNT_TOMBSTONE = "ACCOUNT_TOMBSTONE"
    CONNECTOR_ACTIVE = "CONNECTOR_ACTIVE"
    UNKNOWN = "UNKNOWN"


class RuleScope(str, Enum):
    DATA_CATEGORY = "DATA_CATEGORY"
    CONDITIONAL = "CONDITIONAL"
    FIELD = "FIELD"
    RESOURCE = "RESOURCE"
    OPERATION = "OPERATION"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    data_category: str
    condition_text: str
    condition_type: ConditionType
    required_action: PolicyAction
    scope: RuleScope = RuleScope.DATA_CATEGORY
    applies_to_system: Optional[str] = None
    retained_permitted_fields: List[str] = field(default_factory=list)
    prohibited_fields: List[str] = field(default_factory=list)
    allows_retention: bool = False
    requires_redaction: bool = False
    requires_anonymization: bool = False
    requires_tombstone: bool = False
    requires_restore_block: bool = False


@dataclass
class PolicyProof:
    """Canonical explainable decision model for every resource policy evaluation."""
    resource_id: str
    system_id: str
    data_category: str
    rule_id: str
    condition_text: str
    condition_met: bool
    required_action: PolicyAction
    actual_state: ObservedState
    is_compliant: bool
    has_prohibited_pii: bool
    is_retention_permitted: bool
    recreation_risk: Optional[str] = None
    failure_reason: Optional[str] = None
    evidence_proof_id: str = ""
    finding_step: Optional[Step] = None
    remediation_step: Optional[Step] = None
    verification_step: Optional[Step] = None

    @property
    def policy_condition(self) -> str:
        return self.condition_text

    @property
    def proof(self) -> str:
        return self.evidence_proof_id

    def __getitem__(self, item: str) -> Any:
        if item == "finding":
            return self.finding_step
        elif item == "remediation":
            return self.remediation_step
        elif item == "verification":
            return self.verification_step
        elif item == "is_compliant":
            return self.is_compliant
        elif item == "proof":
            return self.proof
        elif hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "system_id": self.system_id,
            "data_category": self.data_category,
            "rule_id": self.rule_id,
            "policy_condition": self.condition_text,
            "condition_met": self.condition_met,
            "required_action": self.required_action.value,
            "actual_state": self.actual_state.value,
            "is_compliant": self.is_compliant,
            "has_prohibited_pii": self.has_prohibited_pii,
            "is_retention_permitted": self.is_retention_permitted,
            "recreation_risk": self.recreation_risk,
            "failure_reason": self.failure_reason,
            "proof": self.evidence_proof_id,
            "evidence_proof_id": self.evidence_proof_id,
        }

