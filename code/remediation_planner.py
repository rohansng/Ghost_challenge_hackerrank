"""
Remediation Planner & Step Ordering Engine
Constructs ordered remediation and verification steps strictly adhering to challenge contracts.
"""

from typing import List, Dict, Any, Tuple
from code.models import Step, Phase, Operation, DeletionStatus


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


class RemediationPlanner:
    def __init__(self):
        pass

    def build_plan(
        self,
        case_id: str,
        is_deletion_authorized: bool,
        evaluated_resources: List[Dict[str, Any]],
    ) -> Tuple[DeletionStatus, List[Step]]:
        """
        Builds the canonical, deterministic step list for a single deletion case.
        """
        # 1. Non-deletion requests
        if not is_deletion_authorized:
            return DeletionStatus.NOT_APPLICABLE, []

        findings: List[Step] = []
        remediations: List[Step] = []
        verifications: List[Step] = []

        # Deduplicate resources
        seen_res = set()

        for res_eval in evaluated_resources:
            f = res_eval.get("finding")
            r = res_eval.get("remediation")
            v = res_eval.get("verification")

            if f and f.resource_id not in seen_res:
                findings.append(f)
            if r:
                remediations.append(r)
            if v:
                verifications.append(v)
            if f:
                seen_res.add(f.resource_id)

        # 2. Complete vs Incomplete
        if not findings:
            status = DeletionStatus.COMPLETE
            raw_steps = verifications
            # For COMPLETE, retain evidence_id
        else:
            status = DeletionStatus.INCOMPLETE
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
                for r in remediations
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
                for v in verifications
            ]
            raw_steps = findings + cleaned_remediations + cleaned_verifications

        # 3. Sort steps deterministically
        def sort_key(s: Step):
            p_order = PHASE_PRIORITY.get(s.phase, 99)
            op_order = OP_PRIORITY.get(s.phase, {}).get(s.operation, 99)
            return (p_order, op_order, s.system_id, s.resource_id)

        sorted_steps = sorted(raw_steps, key=sort_key)

        # 4. Renumber steps consecutively from 1
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
            final_steps.append(renumbered)

        return status, final_steps
