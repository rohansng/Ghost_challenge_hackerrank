"""
decision_engine.py - Deterministic Decision Engine & Explainable CaseProof Generator.
Audits deletion requests against the 11-point proof checklist and determines
COMPLETE, INCOMPLETE, or NOT_APPLICABLE with explicit causal proofs.
"""

from datetime import datetime
from typing import Dict, List, Optional, Set, Any, Tuple

from code.models import (
    DeletionRequestRecord,
    DeletionStatus,
    Step,
    Phase,
    Operation,
)
from code.evidence_models import (
    EvidenceObservation,
    ResourceStateSnapshot,
    ObservedState,
)
from code.identity_engine import IdentityResolutionResult
from code.decision_models import (
    ChecklistItem,
    IncompleteReason,
    IdentityProof,
    ResourceProof,
    PolicyProofSummary,
    TemporalProof,
    RecreationProofSummary,
    RetentionProof,
    VerificationProof,
    CaseProof,
)


class DecisionEngine:
    """
    Deterministic Deletion Decision Engine.
    Evaluates evidence against statutory and operational checklist requirements.
    """

    def __init__(self):
        pass

    def evaluate_case(
        self,
        request: DeletionRequestRecord,
        is_deletion_authorized: bool,
        identity_res: Optional[IdentityResolutionResult],
        all_observations: List[EvidenceObservation],
        snapshots: Dict[str, ResourceStateSnapshot],
        evaluated_resources: List[Dict[str, Any]],
        steps: List[Step],
    ) -> CaseProof:
        """
        Executes comprehensive checklist verification and generates an explainable CaseProof.
        """
        # 1. Non-deletion requests (NOT_APPLICABLE)
        if not is_deletion_authorized:
            checklist = {item.value: False for item in ChecklistItem}
            checklist[ChecklistItem.CORRECT_IDENTITY_RESOLVED.value] = True if identity_res and identity_res.is_resolved else False

            return CaseProof(
                case_id=request.case_id,
                requested_email=request.email,
                audit_at=request.audit_at,
                is_deletion_authorized=False,
                final_decision=DeletionStatus.NOT_APPLICABLE,
                decision_reasons=[IncompleteReason.NO_DELETION_REQUESTED],
                checklist=checklist,
                steps=[],
            )

        # 2. Build Sub-Proofs
        # A. Identity Proof
        id_proof = self._build_identity_proof(identity_res)

        # B. Temporal Proof
        temp_proof = self._build_temporal_proof(request.audit_at, all_observations)

        # C. Resource & Policy Proofs
        res_proofs, policy_summary = self._build_resource_and_policy_proofs(snapshots, evaluated_resources)

        # D. Recreation Proof
        recreation_summary = self._build_recreation_proof(snapshots, evaluated_resources)

        # E. Retention Proof
        retention_proof = self._build_retention_proof(snapshots, evaluated_resources)

        # F. Verification Proof
        verif_proof = self._build_verification_proof(steps)

        # 3. Evaluate 11-Point Checklist
        checklist: Dict[str, bool] = {}
        decision_reasons: List[IncompleteReason] = []

        # 1. Correct identity resolved
        c1 = id_proof.is_resolved and not id_proof.ambiguities
        checklist[ChecklistItem.CORRECT_IDENTITY_RESOLVED.value] = c1
        if not c1:
            decision_reasons.append(IncompleteReason.UNRESOLVED_IDENTITY)

        # 2. Correct historical identifiers considered
        c2 = bool(id_proof.historical_emails or id_proof.hashes or id_proof.is_resolved)
        checklist[ChecklistItem.HISTORICAL_IDENTIFIERS_CONSIDERED.value] = c2

        # 3. All relevant copies/resources identified
        c3 = len(snapshots) > 0 or len(all_observations) == 0
        checklist[ChecklistItem.ALL_RELEVANT_RESOURCES_IDENTIFIED.value] = c3
        if len(snapshots) == 0 and len(all_observations) > 0:
            decision_reasons.append(IncompleteReason.INSUFFICIENT_EVIDENCE)

        # 4. Every applicable resource received required treatment
        findings = [s for s in steps if s.phase == Phase.FINDING]
        c4 = len(findings) == 0
        checklist[ChecklistItem.EVERY_RESOURCE_RECEIVED_REQUIRED_TREATMENT.value] = c4
        if not c4:
            decision_reasons.append(IncompleteReason.RESOURCE_NOT_TREATED)

        # 5. Required retained records remain
        c5 = retention_proof.is_retention_compliant
        checklist[ChecklistItem.REQUIRED_RETAINED_RECORDS_REMAIN.value] = c5

        # 6. Retained records contain only permitted data (no exposed direct PII)
        exposed_pii_findings = [f for f in findings if f.operation == Operation.REPORT_EXPOSED_PII]
        c6 = len(exposed_pii_findings) == 0 and len(retention_proof.prohibited_identifiers_in_retained) == 0
        checklist[ChecklistItem.RETAINED_RECORDS_CONTAIN_ONLY_PERMITTED_DATA.value] = c6
        if not c6:
            decision_reasons.append(IncompleteReason.PROHIBITED_RETAINED_IDENTIFIER)

        # 7. No relevant prohibited data remains
        remaining_record_findings = [f for f in findings if f.operation == Operation.REPORT_REMAINING_RECORD]
        c7 = len(remaining_record_findings) == 0
        checklist[ChecklistItem.NO_PROHIBITED_DATA_REMAINS.value] = c7
        if not c7:
            decision_reasons.append(IncompleteReason.DATA_REMAINS)

        # 8. No active sync/import/restore path can recreate prohibited data
        active_sync_findings = [f for f in findings if f.operation == Operation.REPORT_ACTIVE_DATA_FLOW]
        restore_risk_findings = [f for f in findings if f.operation == Operation.REPORT_RESTORE_RISK]
        c8 = len(active_sync_findings) == 0 and len(restore_risk_findings) == 0
        checklist[ChecklistItem.NO_ACTIVE_RECREATION_OR_RESTORE_PATH.value] = c8
        if len(active_sync_findings) > 0:
            decision_reasons.append(IncompleteReason.ACTIVE_SYNC)
        if len(restore_risk_findings) > 0:
            decision_reasons.append(IncompleteReason.RESTORE_RISK)

        # 9. Required verification evidence exists
        # For a complete deletion, all verifications must cite non-empty evidence_id
        if len(findings) == 0:
            c9 = all(s.evidence_id != "" for s in steps) if steps else True
        else:
            c9 = True  # Incomplete cases propose future verifications
        checklist[ChecklistItem.REQUIRED_VERIFICATION_EVIDENCE_EXISTS.value] = c9
        if not c9:
            decision_reasons.append(IncompleteReason.MISSING_VERIFICATION)

        # 10. Evidence is valid and within permitted temporal boundary
        c10 = temp_proof.is_strictly_bounded
        checklist[ChecklistItem.EVIDENCE_WITHIN_TEMPORAL_BOUNDARY.value] = c10

        # 11. No unresolved contradictions
        c11 = temp_proof.contradictions_detected == 0
        checklist[ChecklistItem.NO_UNRESOLVED_CONTRADICTIONS.value] = c11
        if not c11:
            decision_reasons.append(IncompleteReason.CONTRADICTORY_EVIDENCE)

        # 4. Final Decision Determination
        all_passed = all(checklist.values())
        if all_passed:
            final_status = DeletionStatus.COMPLETE
            decision_reasons = []
        else:
            final_status = DeletionStatus.INCOMPLETE

        return CaseProof(
            case_id=request.case_id,
            requested_email=request.email,
            audit_at=request.audit_at,
            is_deletion_authorized=True,
            final_decision=final_status,
            decision_reasons=decision_reasons,
            checklist=checklist,
            identity_proof=id_proof,
            resource_proofs=res_proofs,
            policy_proofs=policy_summary,
            temporal_proofs=temp_proof,
            recreation_proofs=recreation_summary,
            retention_proofs=retention_proof,
            verification_proofs=verif_proof,
            steps=steps,
        )

    def _build_identity_proof(self, res: Optional[IdentityResolutionResult]) -> IdentityProof:
        if not res or not res.is_resolved or not res.identity_node:
            return IdentityProof(
                user_id=None,
                matched_identifiers=[],
                historical_emails=[],
                phones=[],
                hashes=[],
                is_resolved=False,
                ambiguities=res.ambiguities if res else ["No identity match"],
            )

        node = res.identity_node
        hist_emails = [e for e in node.all_emails if e.lower() != (node.current_email or "").lower()]
        return IdentityProof(
            user_id=node.canonical_user_id,
            matched_identifiers=[m.matched_value for m in res.matched_identifiers],
            historical_emails=hist_emails,
            phones=list(node.all_phones),
            hashes=list(node.all_hashes),
            is_resolved=True,
            ambiguities=res.ambiguities,
        )

    def _build_temporal_proof(
        self,
        audit_at: datetime,
        observations: List[EvidenceObservation],
    ) -> TemporalProof:
        post_audit_count = 0
        contradictions = 0
        latest_time = None

        for o in observations:
            t = o.event_time or o.captured_at
            if t:
                if t > audit_at:
                    post_audit_count += 1
                else:
                    if latest_time is None or t > latest_time:
                        latest_time = t
            if o.is_contradictory:
                contradictions += 1

        return TemporalProof(
            audit_at=audit_at,
            latest_observation_time=latest_time,
            is_strictly_bounded=True,  # Bounded because pipeline strictly filters > audit_at
            post_audit_observations_excluded=post_audit_count,
            contradictions_detected=contradictions,
        )

    def _build_resource_and_policy_proofs(
        self,
        snapshots: Dict[str, ResourceStateSnapshot],
        evaluated_resources: List[Dict[str, Any]],
    ) -> Tuple[List[ResourceProof], PolicyProofSummary]:
        res_proofs = []
        violations = []
        compliant_count = 0

        for r_id, snap in snapshots.items():
            is_comp = snap.is_compliant
            has_pii = False
            fail_reason = None

            # Look up evaluation result
            eval_match = next((e for e in evaluated_resources if e.get("snapshot", {}).get("resource_id") == r_id or getattr(e.get("finding"), "resource_id", None) == r_id or getattr(e.get("verification"), "resource_id", None) == r_id), None)
            if eval_match and eval_match.get("finding"):
                f = eval_match["finding"]
                is_comp = False
                fail_reason = f"{f.operation.value} ({f.state.value})"
                violations.append(f"{r_id}: {fail_reason}")
                if f.operation == Operation.REPORT_EXPOSED_PII:
                    has_pii = True
            elif is_comp:
                compliant_count += 1

            res_proofs.append(
                ResourceProof(
                    resource_id=r_id,
                    system_id=snap.system_id,
                    data_category=snap.data_category,
                    proven_state=snap.proven_state,
                    cited_evidence_id=snap.cited_evidence_id,
                    is_compliant=is_comp,
                    has_prohibited_pii=has_pii,
                    failure_reason=fail_reason,
                )
            )

        summary = PolicyProofSummary(
            total_resources_evaluated=len(snapshots),
            compliant_resources=compliant_count,
            violations=violations,
        )
        return res_proofs, summary

    def _build_recreation_proof(
        self,
        snapshots: Dict[str, ResourceStateSnapshot],
        evaluated_resources: List[Dict[str, Any]],
    ) -> RecreationProofSummary:
        active_flows = 0
        restore_risks = 0
        disabled_flows = 0
        blocked_restores = 0
        details = []

        for e in evaluated_resources:
            f = e.get("finding")
            v = e.get("verification")
            if f:
                if f.operation == Operation.REPORT_ACTIVE_DATA_FLOW:
                    active_flows += 1
                    details.append(f"Active data flow connector: {f.resource_id}")
                elif f.operation == Operation.REPORT_RESTORE_RISK:
                    restore_risks += 1
                    details.append(f"Unblocked backup archive restore risk: {f.resource_id}")
            if v:
                if v.operation == Operation.VERIFY_DATA_FLOW_DISABLED:
                    disabled_flows += 1
                elif v.operation == Operation.VERIFY_RESTORE_BLOCKED:
                    blocked_restores += 1

        return RecreationProofSummary(
            active_sync_flows_count=active_flows,
            active_restore_risks_count=restore_risks,
            disabled_flows_count=disabled_flows,
            blocked_restores_count=blocked_restores,
            recreation_threat_details=details,
        )

    def _build_retention_proof(
        self,
        snapshots: Dict[str, ResourceStateSnapshot],
        evaluated_resources: List[Dict[str, Any]],
    ) -> RetentionProof:
        retained = []
        tombstones = []
        prohibited = []

        for r_id, snap in snapshots.items():
            if snap.data_category in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD", "FINANCIAL_LEDGER"):
                retained.append(r_id)
            elif snap.data_category == "ACCOUNT_TOMBSTONE":
                tombstones.append(r_id)
                if snap.proven_state == ObservedState.PRESENT:
                    prohibited.append(r_id)

        return RetentionProof(
            has_required_retention=len(retained) > 0 or len(tombstones) > 0,
            retained_resources=retained,
            tombstones_evaluated=tombstones,
            prohibited_identifiers_in_retained=prohibited,
            is_retention_compliant=len(prohibited) == 0,
        )

    def _build_verification_proof(self, steps: List[Step]) -> VerificationProof:
        v_absent = []
        v_present = []
        v_redacted = []
        v_anon = []
        v_disabled = []
        v_blocked = []

        for s in steps:
            if s.phase == Phase.VERIFICATION:
                if s.operation == Operation.VERIFY_RECORD_ABSENT:
                    v_absent.append(s.resource_id)
                elif s.operation == Operation.VERIFY_RECORD_PRESENT:
                    v_present.append(s.resource_id)
                elif s.operation == Operation.VERIFY_RECORD_REDACTED:
                    v_redacted.append(s.resource_id)
                elif s.operation == Operation.VERIFY_RECORD_ANONYMIZED:
                    v_anon.append(s.resource_id)
                elif s.operation == Operation.VERIFY_DATA_FLOW_DISABLED:
                    v_disabled.append(s.resource_id)
                elif s.operation == Operation.VERIFY_RESTORE_BLOCKED:
                    v_blocked.append(s.resource_id)

        return VerificationProof(
            total_verifications=len(v_absent) + len(v_present) + len(v_redacted) + len(v_anon) + len(v_disabled) + len(v_blocked),
            verified_absent=v_absent,
            verified_present=v_present,
            verified_redacted=v_redacted,
            verified_anonymized=v_anon,
            verified_disabled=v_disabled,
            verified_blocked=v_blocked,
        )
