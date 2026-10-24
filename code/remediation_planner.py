"""
remediation_planner.py - Deterministic Output Step Planner & Step Validator.
Constructs ordered remediation and verification steps strictly adhering to challenge contracts:
1. Strict Phase Order: FINDING -> REMEDIATION -> VERIFICATION.
2. Canonical Operation Priority within each phase.
3. Deterministic tie-breaking on system_id, resource_id, operation, state, evidence_id.
4. Consecutive step numbering from 1.
5. Strict evidence_id rules:
   - COMPLETE: Non-empty evidence_id citing participant-visible evidence.
   - INCOMPLETE: Findings cite participant-visible evidence; remediations and future verifications use evidence_id="".
   - NOT_APPLICABLE: steps_json = [].
"""

import re
from typing import List, Dict, Any, Tuple, Optional, Set
from code.models import Step, Phase, Operation, DeletionStatus
from code.evidence_models import ObservedState


PHASE_PRIORITY = {
    Phase.FINDING: 1,
    Phase.REMEDIATION: 2,
    Phase.VERIFICATION: 3,
}

OP_PRIORITY = {
    Phase.FINDING: {
        Operation.REPORT_REMAINING_RECORD: 1,
        Operation.REPORT_EXPOSED_PII: 2,
        Operation.REPORT_ACTIVE_DATA_FLOW: 3,
        Operation.REPORT_RESTORE_RISK: 4,
    },
    Phase.REMEDIATION: {
        Operation.DISABLE_DATA_FLOW: 1,
        Operation.BLOCK_RESTORE: 2,
        Operation.DELETE_RECORD: 3,
        Operation.REDACT_RECORD: 4,
        Operation.ANONYMIZE_RECORD: 5,
    },
    Phase.VERIFICATION: {
        Operation.VERIFY_RECORD_ABSENT: 1,
        Operation.VERIFY_RECORD_PRESENT: 2,
        Operation.VERIFY_RECORD_REDACTED: 3,
        Operation.VERIFY_RECORD_ANONYMIZED: 4,
        Operation.VERIFY_DATA_FLOW_DISABLED: 5,
        Operation.VERIFY_RESTORE_BLOCKED: 6,
    },
}

ALLOWED_OPERATION_PHASES = {
    Operation.REPORT_REMAINING_RECORD: Phase.FINDING,
    Operation.REPORT_EXPOSED_PII: Phase.FINDING,
    Operation.REPORT_ACTIVE_DATA_FLOW: Phase.FINDING,
    Operation.REPORT_RESTORE_RISK: Phase.FINDING,
    Operation.DISABLE_DATA_FLOW: Phase.REMEDIATION,
    Operation.BLOCK_RESTORE: Phase.REMEDIATION,
    Operation.DELETE_RECORD: Phase.REMEDIATION,
    Operation.REDACT_RECORD: Phase.REMEDIATION,
    Operation.ANONYMIZE_RECORD: Phase.REMEDIATION,
    Operation.VERIFY_RECORD_ABSENT: Phase.VERIFICATION,
    Operation.VERIFY_RECORD_PRESENT: Phase.VERIFICATION,
    Operation.VERIFY_RECORD_REDACTED: Phase.VERIFICATION,
    Operation.VERIFY_RECORD_ANONYMIZED: Phase.VERIFICATION,
    Operation.VERIFY_DATA_FLOW_DISABLED: Phase.VERIFICATION,
    Operation.VERIFY_RESTORE_BLOCKED: Phase.VERIFICATION,
}

ALLOWED_OPERATION_STATES = {
    Operation.REPORT_REMAINING_RECORD: ObservedState.PRESENT,
    Operation.REPORT_EXPOSED_PII: ObservedState.PRESENT,
    Operation.REPORT_ACTIVE_DATA_FLOW: ObservedState.ACTIVE,
    Operation.REPORT_RESTORE_RISK: ObservedState.ACTIVE,
    Operation.DISABLE_DATA_FLOW: ObservedState.DISABLED,
    Operation.BLOCK_RESTORE: ObservedState.BLOCKED,
    Operation.DELETE_RECORD: ObservedState.ABSENT,
    Operation.REDACT_RECORD: ObservedState.REDACTED,
    Operation.ANONYMIZE_RECORD: ObservedState.ANONYMIZED,
    Operation.VERIFY_RECORD_ABSENT: ObservedState.ABSENT,
    Operation.VERIFY_RECORD_PRESENT: ObservedState.PRESENT,
    Operation.VERIFY_RECORD_REDACTED: ObservedState.REDACTED,
    Operation.VERIFY_RECORD_ANONYMIZED: ObservedState.ANONYMIZED,
    Operation.VERIFY_DATA_FLOW_DISABLED: ObservedState.DISABLED,
    Operation.VERIFY_RESTORE_BLOCKED: ObservedState.BLOCKED,
}


class StepValidator:
    """Validates structural and semantic invariants of remediation and verification steps."""

    VALID_EVIDENCE_PATTERN = re.compile(r'^(evidence_\d+|activity_\d+|audit_\d+|ev_\d+)$')

    @classmethod
    def is_valid_evidence_id(cls, evidence_id: str) -> bool:
        if not evidence_id:
            return False
        return bool(cls.VALID_EVIDENCE_PATTERN.match(evidence_id.strip()))

    @classmethod
    def validate_step(cls, step: Step, status: DeletionStatus) -> Tuple[bool, Optional[str]]:
        # Phase check
        expected_phase = ALLOWED_OPERATION_PHASES.get(step.operation)
        if expected_phase != step.phase:
            return False, f"Operation {step.operation} cannot belong to phase {step.phase} (expected {expected_phase})"

        # State check
        expected_state = ALLOWED_OPERATION_STATES.get(step.operation)
        step_state_val = step.state.value if hasattr(step.state, "value") else str(step.state)
        expected_state_val = expected_state.value if hasattr(expected_state, "value") else str(expected_state)
        if expected_state_val != step_state_val:
            return False, f"Operation {step.operation} cannot have state {step.state} (expected {expected_state})"

        # Non-empty identifiers
        if not step.system_id or not step.resource_id:
            return False, "system_id and resource_id must be non-empty"

        # Evidence ID rules
        if status == DeletionStatus.COMPLETE:
            if not step.evidence_id:
                return False, f"COMPLETE case step #{step.step_no} must cite non-empty evidence_id"
            if not cls.is_valid_evidence_id(step.evidence_id):
                return False, f"Invalid evidence_id format: '{step.evidence_id}'"
        elif status == DeletionStatus.INCOMPLETE:
            if step.phase == Phase.FINDING:
                if not step.evidence_id:
                    return False, f"FINDING step #{step.step_no} must cite non-empty evidence_id"
                if not cls.is_valid_evidence_id(step.evidence_id):
                    return False, f"Invalid evidence_id format: '{step.evidence_id}'"
            else:
                if step.evidence_id != "":
                    return False, f"{step.phase.value} step #{step.step_no} in INCOMPLETE case must use empty evidence_id, got '{step.evidence_id}'"

        return True, None


class RemediationPlanner:
    """
    Deterministic Step Planner and Ordering Engine.
    Converts evaluated resource outcomes into compliant, canonical execution steps.
    """

    def __init__(self, valid_evidence_ids: Optional[Set[str]] = None):
        self.valid_evidence_ids = valid_evidence_ids or set()

    def build_plan(
        self,
        case_id: str,
        is_deletion_authorized: bool,
        evaluated_resources: List[Dict[str, Any]],
    ) -> Tuple[DeletionStatus, List[Step]]:
        """
        Builds the canonical, deterministic step list for a single deletion case.
        """
        # 1. Non-deletion requests -> NOT_APPLICABLE with steps = []
        if not is_deletion_authorized:
            return DeletionStatus.NOT_APPLICABLE, []

        raw_findings: List[Step] = []
        raw_remediations: List[Step] = []
        raw_verifications: List[Step] = []

        seen_findings = set()
        seen_remediations = set()
        seen_verifications = set()

        for res_eval in evaluated_resources:
            f = res_eval.get("finding")
            r = res_eval.get("remediation")
            v = res_eval.get("verification")

            if f:
                f_key = (f.phase, f.operation, f.system_id, f.resource_id, f.state)
                if f_key not in seen_findings:
                    seen_findings.add(f_key)
                    raw_findings.append(f)

            if r:
                r_key = (r.phase, r.operation, r.system_id, r.resource_id, r.state)
                if r_key not in seen_remediations:
                    seen_remediations.add(r_key)
                    raw_remediations.append(r)

            if v:
                v_key = (v.phase, v.operation, v.system_id, v.resource_id, v.state)
                if v_key not in seen_verifications:
                    seen_verifications.add(v_key)
                    raw_verifications.append(v)

        # 2. Determine COMPLETE vs INCOMPLETE
        if not raw_findings:
            status = DeletionStatus.COMPLETE
            # For COMPLETE, keep evidence-backed verifications
            candidate_steps = raw_verifications
        else:
            status = DeletionStatus.INCOMPLETE
            # For INCOMPLETE, remediations and future verifications MUST have empty evidence_id
            cleaned_remediations = [
                Step(
                    step_no=0,
                    phase=r.phase,
                    system_id=r.system_id,
                    resource_id=r.resource_id,
                    operation=r.operation,
                    state=r.state,
                    evidence_id="",
                )
                for r in raw_remediations
            ]
            cleaned_verifications = [
                Step(
                    step_no=0,
                    phase=v.phase,
                    system_id=v.system_id,
                    resource_id=v.resource_id,
                    operation=v.operation,
                    state=v.state,
                    evidence_id="",
                )
                for v in raw_verifications
            ]
            candidate_steps = raw_findings + cleaned_remediations + cleaned_verifications

        # 3. Canonical deterministic sorting
        def sort_key(s: Step):
            p_order = PHASE_PRIORITY.get(s.phase, 99)
            op_order = OP_PRIORITY.get(s.phase, {}).get(s.operation, 99)
            return (
                p_order,
                op_order,
                s.system_id,
                s.resource_id,
                s.operation.value,
                s.state.value,
                s.evidence_id,
            )

        sorted_steps = sorted(candidate_steps, key=sort_key)

        # 4. Deterministic consecutive step numbering starting from 1
        final_steps: List[Step] = []
        for idx, s in enumerate(sorted_steps, start=1):
            renumbered = Step(
                step_no=idx,
                phase=s.phase,
                system_id=s.system_id,
                resource_id=s.resource_id,
                operation=s.operation,
                state=s.state,
                evidence_id=s.evidence_id,
            )
            # Validate invariant
            valid, err = StepValidator.validate_step(renumbered, status)
            if not valid:
                raise ValueError(f"Step validation failed for case {case_id}: {err}")
            final_steps.append(renumbered)

        return status, final_steps
