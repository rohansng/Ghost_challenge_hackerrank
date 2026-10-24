"""
Deletion Policy Engine
Applies deletion_rules.csv rules (rule_01 to rule_15) to proven resource snapshots.
"""

from typing import List, Dict, Any, Optional, Tuple
from code.evidence_models import ResourceStateSnapshot, ObservedState
from code.models import Operation, ResourceState, Phase, Step


class PolicyEngine:
    """Evaluates resource states against deletion policy rules and generates finding/remediation/verification actions."""

    def __init__(self):
        pass

    def evaluate_resource_policy(
        self,
        snapshot: ResourceStateSnapshot,
    ) -> Dict[str, Any]:
        """
        Determines compliance and required operations for a single resource.
        Returns dict with:
          - is_compliant: bool
          - finding: Optional Step
          - remediation: Optional Step
          - verification: Step
        """
        cat = snapshot.data_category.upper()
        state = snapshot.proven_state
        sys_id = snapshot.system_id
        res_id = snapshot.resource_id
        ev_id = snapshot.cited_evidence_id

        # Rule 01, 02, 03, 04, 06, 09, 10: DELETE required
        if any(k in cat for k in ("USER_PROFILE", "SECONDARY_IDENTIFIER", "SEARCH_INDEX_ENTRY", "CACHE_ENTRY", "SUPPORT_ATTACHMENT", "USER_EXPORT", "MARKETING_PROFILE")):
            if state in (ObservedState.PRESENT, ObservedState.ACTIVE, ObservedState.UNKNOWN):
                # Non-compliant: still exists
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_REMAINING_RECORD,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.DELETE_RECORD,
                    state=ResourceState.ABSENT,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ABSENT,
                    state=ResourceState.ABSENT,
                    evidence_id="",
                )
                return {
                    "is_compliant": False,
                    "finding": finding,
                    "remediation": remediation,
                    "verification": verification,
                }
            else:
                # Compliant: already absent
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ABSENT,
                    state=ResourceState.ABSENT,
                    evidence_id=ev_id,
                )
                return {
                    "is_compliant": True,
                    "finding": None,
                    "remediation": None,
                    "verification": verification,
                }

        # Rule 07, 08: ANALYTICS_PROFILE / PRODUCT_TELEMETRY -> ANONYMIZE required
        elif any(k in cat for k in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY", "ANALYTICS")):
            if state in (ObservedState.PRESENT, ObservedState.ACTIVE, ObservedState.UNKNOWN):
                # Non-compliant: still contains PII
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_EXPOSED_PII,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.ANONYMIZE_RECORD,
                    state=ResourceState.ANONYMIZED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ANONYMIZED,
                    state=ResourceState.ANONYMIZED,
                    evidence_id="",
                )
                return {
                    "is_compliant": False,
                    "finding": finding,
                    "remediation": remediation,
                    "verification": verification,
                }
            else:
                # Compliant: anonymized
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ANONYMIZED,
                    state=ResourceState.ANONYMIZED,
                    evidence_id=ev_id,
                )
                return {
                    "is_compliant": True,
                    "finding": None,
                    "remediation": None,
                    "verification": verification,
                }

        # Rule 05, 11, 15: SUPPORT_MESSAGE, EMAIL_DELIVERY_LOG, ACCOUNT_TOMBSTONE -> REDACT required
        elif any(k in cat for k in ("SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE", "SUPPORT")):
            if state in (ObservedState.PRESENT, ObservedState.ACTIVE, ObservedState.UNKNOWN):
                # Non-compliant: personal identifiers still exposed
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_EXPOSED_PII,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REDACT_RECORD,
                    state=ResourceState.REDACTED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_REDACTED,
                    state=ResourceState.REDACTED,
                    evidence_id="",
                )
                return {
                    "is_compliant": False,
                    "finding": finding,
                    "remediation": remediation,
                    "verification": verification,
                }
            else:
                # Compliant: redacted or absent
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_REDACTED,
                    state=ResourceState.REDACTED,
                    evidence_id=ev_id,
                )
                return {
                    "is_compliant": True,
                    "finding": None,
                    "remediation": None,
                    "verification": verification,
                }

        # CONNECTOR_SUBSCRIPTION / DATA_FLOW -> DISABLE_DATA_FLOW required
        elif any(k in cat for k in ("CONNECTOR_SUBSCRIPTION", "DATA_FLOW", "CONNECTOR")):
            if state in (ObservedState.ACTIVE, ObservedState.PRESENT, ObservedState.ENABLED):
                # Non-compliant: active sync pipeline can recreate data
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_ACTIVE_DATA_FLOW,
                    state=ResourceState.ACTIVE,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.DISABLE_DATA_FLOW,
                    state=ResourceState.DISABLED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    state=ResourceState.DISABLED,
                    evidence_id="",
                )
                return {
                    "is_compliant": False,
                    "finding": finding,
                    "remediation": remediation,
                    "verification": verification,
                }
            else:
                # Compliant: disabled
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    state=ResourceState.DISABLED,
                    evidence_id=ev_id,
                )
                return {
                    "is_compliant": True,
                    "finding": None,
                    "remediation": None,
                    "verification": verification,
                }

        # Rule 14: BACKUP_ARCHIVE -> BLOCK_RESTORE required
        elif "BACKUP" in cat:
            if state in (ObservedState.ACTIVE, ObservedState.PRESENT, ObservedState.ENABLED):
                # Non-compliant: restore access remains open
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_RESTORE_RISK,
                    state=ResourceState.ACTIVE,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.BLOCK_RESTORE,
                    state=ResourceState.BLOCKED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    state=ResourceState.BLOCKED,
                    evidence_id="",
                )
                return {
                    "is_compliant": False,
                    "finding": finding,
                    "remediation": remediation,
                    "verification": verification,
                }
            else:
                # Compliant: restore blocked
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    state=ResourceState.BLOCKED,
                    evidence_id=ev_id,
                )
                return {
                    "is_compliant": True,
                    "finding": None,
                    "remediation": None,
                    "verification": verification,
                }

        # Rule 12, 13: SECURITY_AUDIT_LOG, LEGAL_HOLD_RECORD -> RETAIN required
        elif any(k in cat for k in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD", "AUDIT", "LEGAL")):
            verification = Step(
                step_no=0,
                phase=Phase.VERIFICATION,
                system_id=sys_id,
                resource_id=res_id,
                operation=Operation.VERIFY_RECORD_PRESENT,
                state=ResourceState.PRESENT,
                evidence_id=ev_id,
            )
            return {
                "is_compliant": True,
                "finding": None,
                "remediation": None,
                "verification": verification,
            }

        # Default fallback
        verification = Step(
            step_no=0,
            phase=Phase.VERIFICATION,
            system_id=sys_id,
            resource_id=res_id,
            operation=Operation.VERIFY_RECORD_ABSENT,
            state=ResourceState.ABSENT,
            evidence_id=ev_id,
        )
        return {
            "is_compliant": True,
            "finding": None,
            "remediation": None,
            "verification": verification,
        }
