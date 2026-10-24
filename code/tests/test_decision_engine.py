"""
test_decision_engine.py - Synthetic Decision Engine & Proof Checklist Verification Suite.
Validates the 11-point proof checklist and causal failure explanations under adversarial conditions.
"""

import unittest
from datetime import datetime, timezone
from code.models import (
    DeletionRequestRecord,
    DeletionStatus,
    Step,
    Phase,
    Operation,
    UserIdentityRecord,
    AuditLogRecord,
)
from code.evidence_models import (
    EvidenceObservation,
    ResourceStateSnapshot,
    ObservedState,
)
from code.identity_engine import IdentityEngine, IdentityResolutionResult
from code.decision_models import ChecklistItem, IncompleteReason, CaseProof
from code.decision_engine import DecisionEngine


class TestDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.decision_engine = DecisionEngine()
        self.audit_at = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        self.before_audit = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
        self.after_audit = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)

    def _create_mock_identity(self, user_id="user_100", email="alice@example.com", hist_emails=None, ambiguous=False):
        identities = {
            user_id: UserIdentityRecord(
                user_id=user_id,
                name="Alice Test",
                email=email,
                phone="+1 555 0100",
                email_hash="hash_alice",
                updated_at=self.before_audit,
            )
        }
        audit_logs = []
        if hist_emails:
            for idx, he in enumerate(hist_emails):
                audit_logs.append(
                    AuditLogRecord(
                        audit_id=f"audit_{idx}",
                        user_id=user_id,
                        event_time=self.before_audit,
                        field_name="email",
                        old_value=he,
                        new_value=email,
                    )
                )
        engine = IdentityEngine(identities, audit_logs)
        res = engine.resolve_identity(email)
        if ambiguous:
            res.ambiguities = ["Ambiguous match to multiple candidates"]
        return res

    def test_clean_complete_case(self):
        """1. Clean complete case: All 11 checklist conditions pass -> COMPLETE."""
        req = DeletionRequestRecord("case_01", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Please delete my account")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        obs = [
            EvidenceObservation("obs_1", "ev_01", "f.json", "loc", "json", self.before_audit, self.before_audit, "account_service", "account_100", "USER_PROFILE", ObservedState.ABSENT, "user_100", "alice@example.com")
        ]
        snapshots = {
            "account_100": ResourceStateSnapshot("account_service", "account_100", "USER_PROFILE", ObservedState.ABSENT, self.audit_at, "ev_01", is_compliant=True)
        }
        steps = [
            Step(1, Phase.VERIFICATION, "account_service", "account_100", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "ev_01")
        ]

        proof: CaseProof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=obs,
            snapshots=snapshots,
            evaluated_resources=[],
            steps=steps,
        )

        self.assertEqual(proof.final_decision, DeletionStatus.COMPLETE)
        self.assertEqual(len(proof.decision_reasons), 0)
        self.assertTrue(all(proof.checklist.values()))

    def test_data_remaining(self):
        """2. Data remaining: Record proven PRESENT at audit_at -> INCOMPLETE (DATA_REMAINS)."""
        req = DeletionRequestRecord("case_02", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Please erase my data")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        obs = [
            EvidenceObservation("obs_1", "ev_01", "f.json", "loc", "json", self.before_audit, self.before_audit, "account_service", "account_100", "USER_PROFILE", ObservedState.PRESENT, "user_100", "alice@example.com")
        ]
        snapshots = {
            "account_100": ResourceStateSnapshot("account_service", "account_100", "USER_PROFILE", ObservedState.PRESENT, self.audit_at, "ev_01", is_compliant=False)
        }
        steps = [
            Step(1, Phase.FINDING, "account_service", "account_100", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "ev_01"),
            Step(2, Phase.REMEDIATION, "account_service", "account_100", Operation.DELETE_RECORD, ObservedState.ABSENT, ""),
            Step(3, Phase.VERIFICATION, "account_service", "account_100", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, ""),
        ]

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=obs,
            snapshots=snapshots,
            evaluated_resources=[{"finding": steps[0]}],
            steps=steps,
        )

        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)
        self.assertIn(IncompleteReason.DATA_REMAINS, proof.decision_reasons)
        self.assertFalse(proof.checklist[ChecklistItem.NO_PROHIBITED_DATA_REMAINS.value])

    def test_active_recreation(self):
        """3. Active recreation: Live connector active -> INCOMPLETE (ACTIVE_SYNC)."""
        req = DeletionRequestRecord("case_03", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Delete my data")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        snapshots = {
            "data_flow_1": ResourceStateSnapshot("integration_service", "data_flow_1", "CONNECTOR_SUBSCRIPTION", ObservedState.ACTIVE, self.audit_at, "ev_01", is_compliant=False)
        }
        finding_step = Step(1, Phase.FINDING, "integration_service", "data_flow_1", Operation.REPORT_ACTIVE_DATA_FLOW, ObservedState.ACTIVE, "ev_01")
        steps = [
            finding_step,
            Step(2, Phase.REMEDIATION, "integration_service", "data_flow_1", Operation.DISABLE_DATA_FLOW, ObservedState.DISABLED, ""),
            Step(3, Phase.VERIFICATION, "integration_service", "data_flow_1", Operation.VERIFY_DATA_FLOW_DISABLED, ObservedState.DISABLED, ""),
        ]

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=[],
            snapshots=snapshots,
            evaluated_resources=[{"finding": finding_step}],
            steps=steps,
        )

        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)
        self.assertIn(IncompleteReason.ACTIVE_SYNC, proof.decision_reasons)
        self.assertFalse(proof.checklist[ChecklistItem.NO_ACTIVE_RECREATION_OR_RESTORE_PATH.value])

    def test_retained_legal_record(self):
        """4. Retained legal record: Policy-required retention correctly preserved -> COMPLETE."""
        req = DeletionRequestRecord("case_04", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Delete my data")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        snapshots = {
            "audit_rec_1": ResourceStateSnapshot("security_service", "audit_rec_1", "SECURITY_AUDIT_LOG", ObservedState.PRESENT, self.audit_at, "ev_01", is_compliant=True)
        }
        steps = [
            Step(1, Phase.VERIFICATION, "security_service", "audit_rec_1", Operation.VERIFY_RECORD_PRESENT, ObservedState.PRESENT, "ev_01")
        ]

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=[],
            snapshots=snapshots,
            evaluated_resources=[],
            steps=steps,
        )

        self.assertEqual(proof.final_decision, DeletionStatus.COMPLETE)
        self.assertTrue(proof.checklist[ChecklistItem.REQUIRED_RETAINED_RECORDS_REMAIN.value])

    def test_historical_identifier(self):
        """5. Historical identifier: Historical email found exposed in surviving record -> INCOMPLETE."""
        req = DeletionRequestRecord("case_05", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Delete my profile")
        id_res = self._create_mock_identity("user_100", "alice@example.com", hist_emails=["alice.old@example.com"])
        
        snapshots = {
            "profile_old": ResourceStateSnapshot("account_service", "profile_old", "USER_PROFILE", ObservedState.PRESENT, self.audit_at, "ev_01", is_compliant=False)
        }
        finding_step = Step(1, Phase.FINDING, "account_service", "profile_old", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "ev_01")

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=[],
            snapshots=snapshots,
            evaluated_resources=[{"finding": finding_step}],
            steps=[finding_step],
        )

        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)
        self.assertIn(IncompleteReason.DATA_REMAINS, proof.decision_reasons)

    def test_contradictory_evidence(self):
        """6. Contradictory evidence: Observations flagged as contradictory -> INCOMPLETE."""
        req = DeletionRequestRecord("case_06", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Erase all records")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        obs = [
            EvidenceObservation("obs_1", "ev_01", "f.log", "loc", "log", self.before_audit, self.before_audit, "account_service", "acc_1", "USER_PROFILE", "USER_PROFILE", ObservedState.ABSENT, is_contradictory=True)
        ]
        snapshots = {
            "acc_1": ResourceStateSnapshot("account_service", "acc_1", "USER_PROFILE", ObservedState.ABSENT, self.audit_at, "ev_01", is_compliant=True)
        }
        steps = [
            Step(1, Phase.VERIFICATION, "account_service", "acc_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "ev_01")
        ]

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=obs,
            snapshots=snapshots,
            evaluated_resources=[],
            steps=steps,
        )

        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)
        self.assertIn(IncompleteReason.CONTRADICTORY_EVIDENCE, proof.decision_reasons)
        self.assertFalse(proof.checklist[ChecklistItem.NO_UNRESOLVED_CONTRADICTIONS.value])

    def test_missing_evidence(self):
        """7. Missing evidence: Verification step missing evidence_id in a complete case -> INCOMPLETE."""
        req = DeletionRequestRecord("case_07", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Delete me")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        snapshots = {
            "acc_1": ResourceStateSnapshot("account_service", "acc_1", "USER_PROFILE", ObservedState.ABSENT, self.audit_at, "", is_compliant=True)
        }
        # Step with empty evidence_id claiming complete
        steps = [
            Step(1, Phase.VERIFICATION, "account_service", "acc_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "")
        ]

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=[],
            snapshots=snapshots,
            evaluated_resources=[],
            steps=steps,
        )

        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)
        self.assertIn(IncompleteReason.MISSING_VERIFICATION, proof.decision_reasons)

    def test_no_deletion_request(self):
        """8. No deletion request: Export/Access request -> NOT_APPLICABLE with steps = []."""
        req = DeletionRequestRecord("case_08", "alice@example.com", self.before_audit, "NOT_STARTED", self.before_audit, self.audit_at, "Please export all my account data for backup")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=False,
            identity_res=id_res,
            all_observations=[],
            snapshots={},
            evaluated_resources=[],
            steps=[],
        )

        self.assertEqual(proof.final_decision, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(proof.steps, [])
        self.assertIn(IncompleteReason.NO_DELETION_REQUESTED, proof.decision_reasons)

    def test_deletion_after_audit_at(self):
        """9. Deletion after audit_at: Mutation occurring after audit cutoff must NOT prove deletion -> INCOMPLETE."""
        req = DeletionRequestRecord("case_09", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Delete my account")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        # Observation before audit shows PRESENT, deletion occurs after audit
        obs = [
            EvidenceObservation("obs_1", "ev_01", "f.json", "loc", "json", self.before_audit, self.before_audit, "account_service", "acc_1", "USER_PROFILE", "USER_PROFILE", ObservedState.PRESENT),
            EvidenceObservation("obs_2", "ev_02", "f.json", "loc", "json", self.after_audit, self.after_audit, "account_service", "acc_1", "USER_PROFILE", "USER_PROFILE", ObservedState.ABSENT),
        ]
        # At audit_at, proven state is PRESENT
        snapshots = {
            "acc_1": ResourceStateSnapshot("account_service", "acc_1", "USER_PROFILE", ObservedState.PRESENT, self.audit_at, "ev_01", is_compliant=False)
        }
        finding_step = Step(1, Phase.FINDING, "account_service", "acc_1", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "ev_01")

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=obs,
            snapshots=snapshots,
            evaluated_resources=[{"finding": finding_step}],
            steps=[finding_step],
        )

        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)
        self.assertIn(IncompleteReason.DATA_REMAINS, proof.decision_reasons)

    def test_recreation_after_audit_at(self):
        """10. Recreation after audit_at: Mutation occurring after audit cutoff must NOT invalidate complete status at audit_at -> COMPLETE."""
        req = DeletionRequestRecord("case_10", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Delete my account")
        id_res = self._create_mock_identity("user_100", "alice@example.com")
        
        # Observation before audit shows ABSENT, post-audit observation shows recreated
        obs = [
            EvidenceObservation("obs_1", "ev_01", "f.json", "loc", "json", self.before_audit, self.before_audit, "account_service", "acc_1", "USER_PROFILE", "USER_PROFILE", ObservedState.ABSENT),
            EvidenceObservation("obs_2", "ev_02", "f.json", "loc", "json", self.after_audit, self.after_audit, "account_service", "acc_1", "USER_PROFILE", "USER_PROFILE", ObservedState.PRESENT),
        ]
        # Snapshot strictly at audit_at is ABSENT
        snapshots = {
            "acc_1": ResourceStateSnapshot("account_service", "acc_1", "USER_PROFILE", ObservedState.ABSENT, self.audit_at, "ev_01", is_compliant=True)
        }
        steps = [
            Step(1, Phase.VERIFICATION, "account_service", "acc_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "ev_01")
        ]

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=obs,
            snapshots=snapshots,
            evaluated_resources=[],
            steps=steps,
        )

        self.assertEqual(proof.final_decision, DeletionStatus.COMPLETE)
        self.assertEqual(proof.temporal_proofs.post_audit_observations_excluded, 1)

    def test_ambiguous_identity(self):
        """11. Ambiguous identity: Identity resolution collision -> INCOMPLETE (UNRESOLVED_IDENTITY)."""
        req = DeletionRequestRecord("case_11", "alice@example.com", self.before_audit, "COMPLETE", self.before_audit, self.audit_at, "Delete my account")
        id_res = self._create_mock_identity("user_100", "alice@example.com", ambiguous=True)

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=True,
            identity_res=id_res,
            all_observations=[],
            snapshots={},
            evaluated_resources=[],
            steps=[],
        )

        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)
        self.assertIn(IncompleteReason.UNRESOLVED_IDENTITY, proof.decision_reasons)
        self.assertFalse(proof.checklist[ChecklistItem.CORRECT_IDENTITY_RESOLVED.value])


if __name__ == "__main__":
    unittest.main()
